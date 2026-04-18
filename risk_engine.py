"""
Risk Engine — Builder 3

Computes a composite food-security risk score (0–100) for each community
by pulling from:
  - Builder 1: GET /api/crop-health/{region_id}  (NDVI anomaly + drought)
  - Builder 2: GET /api/disruptions/{region_id}  (weather alerts + FEMA + routes)
  - Local:     supply_corridors.json             (corridor dependency weights)
  - Local:     community_vulnerability_index     (food insecurity rates)

Formula (from spec):
  risk_score = (crop_health_component   × 0.40)
             + (disruption_component    × 0.30)
             + (corridor_dependency     × 0.20)
             + (community_vulnerability × 0.10)

Each component is normalised to [0, 100] before weighting.

Author: Builder 3
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — override via environment variables for deployment
# ---------------------------------------------------------------------------
BUILDER1_BASE = os.getenv("BUILDER1_API", "http://localhost:8000")
BUILDER2_BASE = os.getenv("BUILDER2_API", "http://localhost:8001")
HTTP_TIMEOUT  = int(os.getenv("HTTP_TIMEOUT", "15"))

CORRIDORS_PATH = Path(__file__).parent / "supply_corridors.json"

# Component weights (must sum to 1.0)
W_CROP         = 0.40
W_DISRUPTION   = 0.30
W_CORRIDOR     = 0.20
W_VULNERABILITY= 0.10

# ---------------------------------------------------------------------------
# NDVI deviation → crop health component score (0–100, higher = more risk)
# ---------------------------------------------------------------------------
#  deviation_pct  | component score
#  ≥  0           |  0   (above or at baseline — no crop stress)
#  -10 %          |  20
#  -15 %          |  40  (warning threshold)
#  -20 %          |  60
#  -30 %          |  80  (critical threshold)
#  ≤ -40 %        | 100
_CROP_BREAKPOINTS: list[tuple[float, float]] = [
    (0.0,  0.0),
    (-10.0, 20.0),
    (-15.0, 40.0),
    (-20.0, 60.0),
    (-30.0, 80.0),
    (-40.0, 100.0),
]

# Disruption severity strings → raw score
_DISRUPTION_SEVERITY_SCORES: dict[str, float] = {
    "clear":    0.0,
    "minor":   20.0,
    "moderate":50.0,
    "severe":  80.0,
    "extreme": 95.0,
    "blocked": 100.0,
    "impaired": 55.0,
    "unknown":  30.0,
}

# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ComponentScores:
    crop_health: float        # 0–100
    disruption: float         # 0–100
    corridor_dependency: float# 0–100
    community_vulnerability: float # 0–100
    crop_raw: dict            # raw payload from Builder 1
    disruption_raw: dict      # raw payload from Builder 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskScore:
    community_id: str
    community_name: str
    corridor_id: str
    risk_score: float          # 0–100, weighted composite
    components: ComponentScores
    top_factors: list[str]     # top 3 contributing factor descriptions
    data_quality: str          # "full" | "partial" | "mock"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["components"] = self.components.to_dict()
        return d


# ---------------------------------------------------------------------------
# Corridor / vulnerability data loading
# ---------------------------------------------------------------------------

_corridors_data: dict | None = None

def _load_corridors() -> dict:
    global _corridors_data
    if _corridors_data is None:
        _corridors_data = json.loads(CORRIDORS_PATH.read_text())
    return _corridors_data


def get_all_community_ids() -> list[str]:
    data = _load_corridors()
    ids = []
    for corridor in data["corridors"]:
        for community in corridor["destination_communities"]:
            ids.append(community["community_id"])
    return ids


def _get_corridor_for_community(community_id: str) -> tuple[dict, dict] | None:
    """Return (corridor_dict, community_dict) for a given community_id, or None."""
    data = _load_corridors()
    for corridor in data["corridors"]:
        for community in corridor["destination_communities"]:
            if community["community_id"] == community_id:
                return corridor, community
    return None


def _get_vulnerability(community_id: str) -> float:
    data = _load_corridors()
    return data["community_vulnerability_index"].get(community_id, 0.20)


# ---------------------------------------------------------------------------
# API calls to Builder 1 and Builder 2
# ---------------------------------------------------------------------------

def _fetch_crop_health(region_id: str) -> dict:
    """
    GET /api/crop-health/{region_id} from Builder 1.
    Returns the parsed JSON or a mock payload if the service is unreachable.
    """
    url = f"{BUILDER1_BASE}/api/crop-health/{region_id}"
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT)
        if r.status_code == 404:
            logger.warning("Builder 1: no cached analysis for %s — triggering fresh run", region_id)
            # Attempt to kick off a fast analysis so we have *something*
            requests.post(
                f"{BUILDER1_BASE}/api/analyze",
                json={"region_id": region_id, "fast_mode": True},
                timeout=HTTP_TIMEOUT,
            )
            return {"_mock": True, "summary": {"alert": "data_unavailable",
                                                "ndvi_deviation_pct": None,
                                                "drought_status": None}}
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.warning("Builder 1 unreachable (%s): using mock crop data", e)
        return {"_mock": True, "summary": {"alert": "data_unavailable",
                                            "ndvi_deviation_pct": None,
                                            "drought_status": None}}


def _fetch_disruptions(region_id: str) -> dict:
    """
    GET /api/disruptions/{region_id} from Builder 2.
    Returns parsed JSON or a mock payload if the service is unreachable.
    """
    url = f"{BUILDER2_BASE}/api/disruptions/{region_id}"
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.warning("Builder 2 unreachable (%s): using mock disruption data", e)
        return {"_mock": True, "overall_status": "unknown",
                "weather_alerts": [], "disasters": [], "route_statuses": []}


# ---------------------------------------------------------------------------
# Component score calculations
# ---------------------------------------------------------------------------

def _interp(value: float, breakpoints: list[tuple[float, float]]) -> float:
    """Linear interpolation between (x, y) breakpoints. Clamps at boundaries."""
    xs = [p[0] for p in breakpoints]
    ys = [p[1] for p in breakpoints]

    if value >= xs[0]:
        return ys[0]
    if value <= xs[-1]:
        return ys[-1]

    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        y0, y1 = ys[i], ys[i + 1]
        if x1 <= value <= x0:
            t = (value - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 2)

    return ys[-1]


def _crop_health_score(crop_payload: dict) -> tuple[float, list[str]]:
    """
    Convert Builder 1 payload → component score (0–100) + contributing factors.
    """
    factors: list[str] = []
    summary = crop_payload.get("summary") or {}
    deviation = summary.get("ndvi_deviation_pct")
    drought    = summary.get("drought_status")
    alert      = summary.get("alert", "data_unavailable")

    if deviation is None:
        # Fallback: map alert string to a rough score
        fallback = {"normal": 0.0, "warning": 40.0, "critical": 80.0,
                    "data_unavailable": 30.0}
        score = fallback.get(alert, 30.0)
        factors.append(f"Crop health alert: {alert} (NDVI deviation unavailable)")
    else:
        score = _interp(deviation, _CROP_BREAKPOINTS)
        if deviation < -30:
            factors.append(f"Critical crop stress: NDVI {deviation:.1f}% below baseline")
        elif deviation < -15:
            factors.append(f"Crop stress warning: NDVI {deviation:.1f}% below baseline")
        elif deviation < -5:
            factors.append(f"Mild crop decline: NDVI {deviation:.1f}% below baseline")

    # Drought adds a flat penalty on top (capped at 100)
    drought_bonuses = {
        "exceptional_drought": 20.0,
        "severe_drought":      14.0,
        "moderate_drought":     9.0,
        "abnormally_dry":       5.0,
    }
    bonus = drought_bonuses.get(drought or "", 0.0)
    if bonus:
        score = min(100.0, score + bonus)
        factors.append(f"Drought status: {drought.replace('_', ' ')}")

    return round(score, 2), factors


def _disruption_score(disruption_payload: dict) -> tuple[float, list[str]]:
    """
    Convert Builder 2 payload → component score (0–100) + contributing factors.

    Builder 2 is expected to return a dict with keys:
      overall_status: str (clear | impaired | blocked)
      weather_alerts: list of {alert_type, severity, event, affected_area}
      disasters: list of {type, state, declaration_title}
      route_statuses: list of {corridor_id, status, reason}
    """
    factors: list[str] = []

    overall = disruption_payload.get("overall_status", "unknown").lower()
    score = _DISRUPTION_SEVERITY_SCORES.get(overall, 30.0)

    if overall in ("blocked", "impaired"):
        factors.append(f"Supply route status: {overall}")

    # Weather alerts — add the worst one
    alerts = disruption_payload.get("weather_alerts") or []
    if alerts:
        worst = max(
            alerts,
            key=lambda a: _DISRUPTION_SEVERITY_SCORES.get(
                a.get("severity", "").lower(), 10.0
            ),
        )
        sev = worst.get("severity", "unknown")
        event = worst.get("event", "weather alert")
        score = max(score, _DISRUPTION_SEVERITY_SCORES.get(sev.lower(), 30.0))
        factors.append(f"Active weather alert: {event} ({sev})")

    # FEMA disasters
    disasters = disruption_payload.get("disasters") or []
    if disasters:
        score = min(100.0, score + 10.0 * len(disasters))
        titles = [d.get("type", "disaster") for d in disasters[:2]]
        factors.append(f"FEMA disaster declaration(s): {', '.join(titles)}")

    # Route-specific impairments
    routes = disruption_payload.get("route_statuses") or []
    blocked_routes = [r for r in routes if r.get("status") == "blocked"]
    impaired_routes = [r for r in routes if r.get("status") == "impaired"]
    if blocked_routes:
        score = max(score, 80.0)
        factors.append(f"Blocked routes: {', '.join(r['corridor_id'] for r in blocked_routes[:2])}")
    elif impaired_routes:
        score = max(score, 50.0)
        factors.append(f"Impaired routes: {', '.join(r['corridor_id'] for r in impaired_routes[:2])}")

    return round(min(score, 100.0), 2), factors


def _corridor_dependency_score(community: dict) -> tuple[float, list[str]]:
    """
    dependency_weight (0–1) from corridor seed → component score (0–100).
    High dependency = high exposure when that corridor is disrupted.
    """
    weight = community.get("dependency_weight", 0.5)
    score = round(weight * 100.0, 2)
    factors = []
    if weight >= 0.85:
        factors.append(
            f"Critical corridor dependency: {community['name']} has "
            f"no viable alternative supply source ({weight:.0%} dependency)"
        )
    elif weight >= 0.65:
        factors.append(
            f"High corridor dependency: {community['name']} ({weight:.0%})"
        )
    return score, factors


def _vulnerability_score(community_id: str, community: dict) -> tuple[float, list[str]]:
    """
    food_insecurity_rate (0–1) → component score (0–100).
    """
    rate = _get_vulnerability(community_id)
    score = round(rate * 100.0, 2)
    factors = []
    if rate >= 0.35:
        factors.append(
            f"Very high food insecurity: {community['name']} "
            f"({rate:.0%} of population)"
        )
    elif rate >= 0.25:
        factors.append(
            f"Elevated food insecurity: {community['name']} ({rate:.0%})"
        )
    return score, factors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_risk(community_id: str) -> RiskScore:
    """
    Compute the composite risk score for a single community.

    Fetches live data from Builder 1 and Builder 2; degrades gracefully
    if either service is unreachable (mock data, flagged in `data_quality`).
    """
    lookup = _get_corridor_for_community(community_id)
    if lookup is None:
        raise KeyError(f"Unknown community: {community_id!r}. "
                       f"Check supply_corridors.json.")

    corridor, community = lookup
    region_id = corridor["source_region_id"]

    # ---- Fetch from upstream builders ----
    crop_payload        = _fetch_crop_health(region_id)
    disruption_payload  = _fetch_disruptions(region_id)

    is_mock = crop_payload.get("_mock") or disruption_payload.get("_mock")
    data_quality = "mock" if is_mock else "full"

    # ---- Try LLM scoring first ----
    from gemini_scorer import score_risk_llm

    llm_result = score_risk_llm(
        community_id=community_id,
        community_name=community["name"],
        crop_payload=crop_payload,
        disruption_payload=disruption_payload,
        corridor=corridor,
        community=community,
    )

    if llm_result is not None:
        # LLM succeeded — use its score and factors directly
        composite    = llm_result["risk_score"]
        top_factors  = llm_result["top_factors"]
        data_quality = "mock" if is_mock else "full"
        llm_reasoning = llm_result.get("reasoning", "")
    else:
        # Deterministic fallback (your existing formula)
        crop_score,       crop_factors    = _crop_health_score(crop_payload)
        disruption_score, dis_factors     = _disruption_score(disruption_payload)
        corridor_score,   corr_factors    = _corridor_dependency_score(community)
        vuln_score,       vuln_factors    = _vulnerability_score(community_id, community)

        composite = round(
            crop_score        * W_CROP
            + disruption_score  * W_DISRUPTION
            + corridor_score    * W_CORRIDOR
            + vuln_score        * W_VULNERABILITY,
            2,
        )
        scored_factors = []
        for f in crop_factors:   scored_factors.append((crop_score * W_CROP, f))
        for f in dis_factors:    scored_factors.append((disruption_score * W_DISRUPTION, f))
        for f in corr_factors:   scored_factors.append((corridor_score * W_CORRIDOR, f))
        for f in vuln_factors:   scored_factors.append((vuln_score * W_VULNERABILITY, f))
        scored_factors.sort(key=lambda t: t[0], reverse=True)
        top_factors = [f for _, f in scored_factors[:3]]
        llm_reasoning = ""
        data_quality = "mock" if is_mock else "full"

    # ---- Composite ----
    composite = round(
        crop_score        * W_CROP
        + disruption_score  * W_DISRUPTION
        + corridor_score    * W_CORRIDOR
        + vuln_score        * W_VULNERABILITY,
        2,
    )

    # ---- Top 3 factors by contribution magnitude ----
    scored_factors: list[tuple[float, str]] = []
    for f in crop_factors:
        scored_factors.append((crop_score * W_CROP, f))
    for f in dis_factors:
        scored_factors.append((disruption_score * W_DISRUPTION, f))
    for f in corr_factors:
        scored_factors.append((corridor_score * W_CORRIDOR, f))
    for f in vuln_factors:
        scored_factors.append((vuln_score * W_VULNERABILITY, f))

    scored_factors.sort(key=lambda t: t[0], reverse=True)
    top_factors = [f for _, f in scored_factors[:3]]

    components = ComponentScores(
        crop_health=crop_score,
        disruption=disruption_score,
        corridor_dependency=corridor_score,
        community_vulnerability=vuln_score,
        crop_raw=crop_payload,
        disruption_raw=disruption_payload,
    )

    return RiskScore(
        community_id=community_id,
        community_name=community["name"],
        corridor_id=corridor["id"],
        risk_score=composite,
        components=components,
        top_factors=top_factors,
        data_quality=data_quality,
    )


def compute_all_risks() -> list[RiskScore]:
    """Compute risk scores for every community in supply_corridors.json."""
    results = []
    for cid in get_all_community_ids():
        try:
            results.append(compute_risk(cid))
        except Exception as e:
            logger.error("Failed to score community %s: %s", cid, e)
    results.sort(key=lambda r: r.risk_score, reverse=True)
    return results