"""
gemini_scorer.py — Gemini Flash 2.5 risk scorer, all 50 US states

Two modes:
  score_county_fpi()  — scores a single county; returns risk_score + dynamic weights
  score_state_fpi()   — scores a state aggregate; returns state FPI + weight rationale

Gemini receives RAW component scores and decides the weights itself.
No pre-weighting before the prompt. Gemini returns both risk_score AND
the weights it chose, so the frontend can display why it scored the way it did.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    logger.warning("google-genai not installed. Gemini scoring disabled.")

_client = None


def _get_client():
    global _client
    if _client is None and _GENAI_AVAILABLE:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set — Gemini scoring disabled")
            return None
        _client = genai.Client(api_key=api_key)
    return _client


_cache: dict[str, dict] = {}

DEFAULT_WEIGHTS = {
    "shock_exposure":     0.30,
    "vulnerability":      0.30,
    "supply_capacity":    0.25,
    "response_readiness": 0.15,
}

DEFAULT_SHOCK_WEIGHTS = {
    "alert_count":    0.30,
    "alert_severity": 0.25,
    "fema":           0.20,
    "drought":        0.25,
}


def _hash_inputs(*args) -> str:
    blob = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _deterministic_score(
    shock_score: float,
    vulnerability: float,
    supply_capacity: float,
    response_readiness: float,
    weights: dict = DEFAULT_WEIGHTS,
) -> float:
    return round(min(100.0, max(0.0,
        shock_score        * weights["shock_exposure"] +
        vulnerability      * weights["vulnerability"] +
        supply_capacity    * weights["supply_capacity"] +
        response_readiness * weights["response_readiness"]
    )), 1)


# ---------------------------------------------------------------------------
# County prompt — Gemini receives raw components, decides weights itself
# ---------------------------------------------------------------------------

COUNTY_PROMPT = """\
You are a food security risk analyst for the United States federal government.
Score the FOOD PREPAREDNESS INDEX (FPI) risk for a specific county.

## Location
- State: {state_name} ({state_abbr})
- County: {county_name} (FIPS {county_fips})

## Real-time Data Inputs

### Shock Exposure (weather/disaster signals)
{shock_data}

### Vulnerability (demographic/economic)
- Poverty rate estimate: {poverty_pct}%
- Food insecurity rate estimate: {food_insecurity_pct}%
- No-vehicle households estimate: {no_vehicle_pct}%
- Social Vulnerability Index estimate: {svi_score}/100

### Supply Capacity
- Food access score (0=poor, 100=excellent): {food_access_score}
- Estimated retailer density: {retailer_density}

### Response Readiness
- Estimated food bank stock level: {stock_level}
- Estimated voucher program capacity: {voucher_capacity}

## Your Task
Based on the data above, return ONLY a valid JSON object with this exact schema:
{{
  "risk_score": <number 0-100>,
  "trigger": "<prepared|watch|warning|action|critical>",
  "weights": {{
    "shock_exposure": <decimal 0-1>,
    "vulnerability": <decimal 0-1>,
    "supply_capacity": <decimal 0-1>,
    "response_readiness": <decimal 0-1>
  }},
  "top_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "reasoning": "<2-3 sentence explanation of the score>",
  "weight_rationale": "<1 sentence explaining why you adjusted weights from defaults>"
}}

Rules:
- weights must sum to exactly 1.0
- risk_score thresholds: prepared<40, watch 40-59, warning 60-74, action 75-89, critical 90+
- Adjust weights based on what is MOST RELEVANT for this county right now.
  Example: Gulf Coast county in hurricane season → higher shock_exposure weight.
  Rural Appalachian county, no active weather → higher vulnerability weight.
- Do NOT use any default weights blindly. Read the data and justify your choice.
- Return ONLY JSON. No markdown. No explanation outside the JSON.
"""

# ---------------------------------------------------------------------------
# State prompt — receives raw component scores, not pre-weighted numbers
# ---------------------------------------------------------------------------

STATE_PROMPT = """\
You are a food security risk analyst for the United States federal government.
Score the aggregate state-level FOOD PREPAREDNESS INDEX (FPI) for {state_name} ({state_abbr}).

## Real-time State Data

### Weather & Hazard Conditions
{weather_data}

### County Summary
- Counties analyzed: {county_count}
- Counties at Warning+: {warning_plus_count} ({warning_plus_pct}%)
- Highest county score: {max_county_score}
- Population-weighted avg county score: {weighted_avg}

### Raw Component Scores (unweighted — you decide how much each matters)
- Shock score (weather/disaster exposure, 0-100): {shock_score_raw}
- Vulnerability score (poverty/food insecurity/SVI, 0-100): {vuln_score_raw}
- Supply gap score (0=well-supplied, 100=critical shortage): {supply_gap_raw}
- Readiness gap score (0=fully ready, 100=unprepared): {readiness_gap_raw}

### Infrastructure
- Logistics disruption status: {logistics_status}
- Active FEMA declarations: {fema_count}
- Open community incidents: {incident_count}

## Your Task
Look at the raw component scores above and decide which ones matter most for THIS
state's current situation. A state with high shock but low vulnerability should
weight shock more. A state with no active hazards but chronically high poverty
should weight vulnerability more. Do not use fixed defaults.

Return ONLY a valid JSON object:
{{
  "state_risk_score": <number 0-100>,
  "trigger": "<prepared|watch|warning|action|critical>",
  "dominant_driver": "<shock_exposure|vulnerability|supply_capacity|response_readiness|logistics>",
  "state_weights": {{
    "hotspot_pressure": <decimal>,
    "pct_counties_warning_plus": <decimal>,
    "hazard_burden": <decimal>,
    "logistics_disruption": <decimal>,
    "response_capacity": <decimal>,
    "open_incident_pressure": <decimal>,
    "community_signal_surge": <decimal>
  }},
  "top_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "reasoning": "<2-3 sentences explaining the score and weight choices>",
  "recommended_actions": ["<action 1>", "<action 2>"]
}}

state_weights must sum to 1.0. Return ONLY JSON.
"""


def _call_gemini(prompt: str) -> dict | None:
    client = _get_client()
    if not client:
        return None
    try:
        config_kwargs: dict = {
            "temperature": 0.1,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
        }
        try:
            config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)
        except AttributeError:
            pass

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(**config_kwargs),
        )
        raw = response.text.strip()

        if not raw.startswith("{"):
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if fence_match:
                raw = fence_match.group(1)
            else:
                brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
                if brace_match:
                    raw = brace_match.group(0)

        return json.loads(raw.strip())
    except Exception as e:
        logger.warning("Gemini call failed: %s", e)
        return None


def _normalize_weights(weights: dict, keys: list[str]) -> dict:
    total = sum(float(weights.get(k, 0)) for k in keys)
    if total <= 0:
        return {k: round(1.0 / len(keys), 4) for k in keys}
    return {k: round(float(weights.get(k, 0)) / total, 4) for k in keys}


# ---------------------------------------------------------------------------
# County-level scoring
# ---------------------------------------------------------------------------

def score_county_fpi(
    state_abbr: str,
    state_name: str,
    county_fips: str,
    county_name: str,
    shock_data: dict,
    vulnerability: dict,
    supply: dict,
    readiness: dict,
    force_deterministic: bool = False,
) -> dict[str, Any]:
    cache_key = _hash_inputs(state_abbr, county_fips, shock_data, vulnerability, supply, readiness)
    if cache_key in _cache:
        return _cache[cache_key]

    if not force_deterministic and _get_client():
        prompt = COUNTY_PROMPT.format(
            state_name=state_name,
            state_abbr=state_abbr,
            county_name=county_name,
            county_fips=county_fips,
            shock_data=json.dumps(shock_data, indent=2, default=str),
            poverty_pct=vulnerability.get("poverty_pct", "unknown"),
            food_insecurity_pct=vulnerability.get("food_insecurity_pct", "unknown"),
            no_vehicle_pct=vulnerability.get("no_vehicle_pct", "unknown"),
            svi_score=vulnerability.get("svi_score", "unknown"),
            food_access_score=supply.get("food_access_score", "unknown"),
            retailer_density=supply.get("retailer_density", "unknown"),
            stock_level=readiness.get("stock_level", "unknown"),
            voucher_capacity=readiness.get("voucher_capacity", "unknown"),
        )
        gemini_result = _call_gemini(prompt)
        if gemini_result and "risk_score" in gemini_result:
            gemini_result["risk_score"] = max(0.0, min(100.0, float(gemini_result["risk_score"])))
            w_keys = ["shock_exposure", "vulnerability", "supply_capacity", "response_readiness"]
            gemini_result["weights"] = _normalize_weights(
                gemini_result.get("weights", {}), w_keys
            )
            gemini_result["_source"] = "gemini"
            _cache[cache_key] = gemini_result
            return gemini_result

    # Deterministic fallback
    shock_score    = shock_data.get("shock_score", 30.0)
    vuln_score     = (
        vulnerability.get("poverty_pct", 20)         * 0.25 +
        vulnerability.get("no_vehicle_pct", 10)      * 0.15 +
        vulnerability.get("svi_score", 40)            * 0.25 +
        vulnerability.get("food_insecurity_pct", 15) * 0.35
    )
    supply_score   = 100 - supply.get("food_access_score", 50)
    readiness_score= 100 - readiness.get("stock_level", 50)
    risk           = _deterministic_score(shock_score, vuln_score, supply_score, readiness_score)

    from alert_logic import _level_from_score
    level = _level_from_score(risk) or "prepared"

    result = {
        "risk_score":       risk,
        "trigger":          level.lower(),
        "weights":          DEFAULT_WEIGHTS.copy(),
        "top_factors":      _deterministic_top_factors(shock_score, vuln_score, supply_score, readiness_score),
        "reasoning":        "Deterministic fallback scoring (Gemini unavailable).",
        "weight_rationale": "Default weights applied — Gemini unavailable.",
        "_source":          "deterministic",
    }
    _cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# State-level scoring
# ---------------------------------------------------------------------------

def score_state_fpi(
    state_abbr: str,
    state_name: str,
    weather_snapshot: dict,
    county_summaries: list[dict],
    fema_count: int = 0,
    incident_count: int = 0,
    logistics_status: str = "clear",
    force_deterministic: bool = False,
) -> dict[str, Any]:
    cache_key = _hash_inputs(state_abbr, weather_snapshot, len(county_summaries), fema_count)
    if cache_key in _cache:
        return _cache[cache_key]

    warning_plus = [c for c in county_summaries
                    if c.get("trigger") in ("warning", "action", "critical")]
    max_score    = max((c.get("score", 0) for c in county_summaries), default=0)
    total_pop    = sum(c.get("population", 50000) for c in county_summaries) or 1
    weighted_avg = round(
        sum(c.get("score", 0) * c.get("population", 50000) for c in county_summaries) / total_pop,
        1,
    )
    warning_pct = round(len(warning_plus) / max(len(county_summaries), 1) * 100, 1)

    # ------------------------------------------------------------------
    # Extract raw component scores from the first county summary entry.
    # state_fpi_api.py now passes these in directly so Gemini receives
    # unprocessed numbers and decides the weighting itself.
    # ------------------------------------------------------------------
    first = county_summaries[0] if county_summaries else {}
    shock_score_raw   = first.get("shock_score",   weather_snapshot.get("shock_score", 20))
    vuln_score_raw    = first.get("vulnerability",  40)
    supply_gap_raw    = first.get("supply_gap",     50)
    readiness_gap_raw = first.get("readiness_gap",  50)

    if not force_deterministic and _get_client():
        prompt = STATE_PROMPT.format(
            state_name=state_name,
            state_abbr=state_abbr,
            weather_data=json.dumps({
                "overall_status": weather_snapshot.get("overall_status"),
                "shock_score":    weather_snapshot.get("shock_score"),
                "alert_count":    len(weather_snapshot.get("nws_alerts", [])),
                "drought":        weather_snapshot.get("drought", {}).get("max_class", "unknown"),
                "active_storms":  len(weather_snapshot.get("active_storms", [])),
            }, indent=2),
            county_count=len(county_summaries),
            warning_plus_count=len(warning_plus),
            warning_plus_pct=warning_pct,
            max_county_score=max_score,
            weighted_avg=weighted_avg,
            # Raw components — no pre-weighting
            shock_score_raw=shock_score_raw,
            vuln_score_raw=vuln_score_raw,
            supply_gap_raw=supply_gap_raw,
            readiness_gap_raw=readiness_gap_raw,
            logistics_status=logistics_status,
            fema_count=fema_count,
            incident_count=incident_count,
        )
        gemini_result = _call_gemini(prompt)
        if gemini_result and "state_risk_score" in gemini_result:
            gemini_result["state_risk_score"] = max(0.0, min(100.0, float(gemini_result["state_risk_score"])))
            w_keys = [
                "hotspot_pressure", "pct_counties_warning_plus", "hazard_burden",
                "logistics_disruption", "response_capacity",
                "open_incident_pressure", "community_signal_surge",
            ]
            gemini_result["state_weights"] = _normalize_weights(
                gemini_result.get("state_weights", {}), w_keys
            )
            gemini_result["_source"] = "gemini"
            _cache[cache_key] = gemini_result
            return gemini_result

    # Deterministic fallback
    shock       = weather_snapshot.get("shock_score", 20.0)
    state_score = round(min(100.0,
        (weighted_avg * 0.4 + max_score * 0.1) +
        warning_pct * 0.3 +
        shock * 0.2
    ), 1)

    result = {
        "state_risk_score": state_score,
        "trigger":          _score_to_trigger(state_score),
        "dominant_driver":  "shock_exposure" if shock > 50 else "vulnerability",
        "state_weights": {
            "hotspot_pressure":          0.22,
            "pct_counties_warning_plus": 0.18,
            "hazard_burden":             0.16,
            "logistics_disruption":      0.12,
            "response_capacity":         0.12,
            "open_incident_pressure":    0.10,
            "community_signal_surge":    0.10,
        },
        "top_factors": [
            f"{warning_pct:.0f}% counties at Warning+",
            f"Shock score {shock:.0f}/100",
            f"Avg county risk {weighted_avg}",
        ],
        "reasoning":          "Deterministic fallback (Gemini unavailable).",
        "recommended_actions":["Monitor county-level alerts.", "Review supply chain status."],
        "_source":            "deterministic",
    }
    _cache[cache_key] = result
    return result


def _score_to_trigger(score: float) -> str:
    if score >= 90: return "critical"
    if score >= 75: return "action"
    if score >= 60: return "warning"
    if score >= 40: return "watch"
    return "prepared"


def _deterministic_top_factors(shock, vuln, supply, readiness) -> list[str]:
    factors = [
        ("Shock exposure",           shock),
        ("Community vulnerability",  vuln),
        ("Supply capacity gap",      supply),
        ("Response readiness gap",   readiness),
    ]
    factors.sort(key=lambda x: x[1], reverse=True)
    return [f"{name}: {score:.0f}/100" for name, score in factors[:3]]


def clear_cache():
    _cache.clear()