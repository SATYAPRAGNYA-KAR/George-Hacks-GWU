"""
Route disruption checker for major freight corridors.

We compute corridor status by intersecting corridor waypoints (state + county)
with:
  - active NOAA weather alerts from noaa.fetch_weather_alerts()
  - active FEMA disaster declarations from fema.fetch_fema_disasters()

Why not a DOT 511 feed? Each state runs its own, schemas differ, and for
the crop-disruption use case weather/disaster intersection is more directly
informative. A real DOT feed can be added as an additional signal later.

Output contract (per Builder 3):
    {corridor_id, status, reason, estimated_duration}

Author: Ruhani (Builder 2)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import fema
import noaa

logger = logging.getLogger(__name__)

CORRIDORS_PATH = Path(__file__).parent / "corridors.json"

# Severity → status mapping. NWS severities: Minor, Moderate, Severe, Extreme.
BLOCKING_SEVERITIES = {"Extreme"}
IMPAIRING_SEVERITIES = {"Severe", "Moderate"}

# FEMA disaster types that block vs impair (rough heuristic, tune for demo).
BLOCKING_DISASTER_TYPES = {
    "Hurricane", "Tornado", "Earthquake", "Wildfire"
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class CorridorStatus:
    corridor_id: str
    status: str                        # clear | impaired | blocked
    reason: str                        # human-readable summary
    estimated_duration: str | None     # ISO expiry of worst impact
    impaired_segments: list[dict] = field(default_factory=list)
    crop_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Waypoint:
    state: str
    county: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.state.upper(), _normalize_county(self.county))


# ---------------------------------------------------------------------------
# Corridor loading
# ---------------------------------------------------------------------------
_corridors_cache: dict[str, dict[str, Any]] | None = None


def load_corridors(path: Path | str = CORRIDORS_PATH) -> dict[str, dict[str, Any]]:
    """Load corridor definitions, indexed by corridor id."""
    global _corridors_cache
    if _corridors_cache is not None and path == CORRIDORS_PATH:
        return _corridors_cache

    data = json.loads(Path(path).read_text())
    corridors = {c["id"]: c for c in data.get("corridors", [])}

    if path == CORRIDORS_PATH:
        _corridors_cache = corridors
    return corridors


# ---------------------------------------------------------------------------
# County-name normalization
# ---------------------------------------------------------------------------
def _normalize_county(name: str) -> str:
    """Normalize a county name for comparison across data sources.

    NWS areaDesc:      "Polk, IA"  (we pass in "Polk")
    FEMA designated:   "Polk (County)" → "Polk"
    """
    n = name.strip()
    n = n.replace("(County)", "").replace("(Parish)", "").replace("(Borough)", "")
    n = n.replace("County", "").replace("Parish", "")
    # Drop trailing ', IA' if someone passed the NWS areaDesc form
    if "," in n:
        n = n.split(",", 1)[0]
    return n.strip().lower()


def _alert_affected_keys(alert: noaa.WeatherAlert) -> set[tuple[str, str]]:
    """Extract (STATE, normalized_county) pairs from an NWS alert's areaDesc."""
    keys: set[tuple[str, str]] = set()
    for piece in alert.areas:
        # "Polk, IA"
        if "," in piece:
            county, state = [p.strip() for p in piece.rsplit(",", 1)]
            keys.add((state.upper(), _normalize_county(county)))
    return keys


def _disaster_affected_keys(disaster: fema.Disaster) -> set[tuple[str, str]]:
    state = disaster.state.upper()
    return {(state, _normalize_county(c)) for c in disaster.counties}


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------
def _classify_alert(alert: noaa.WeatherAlert) -> str:
    if alert.severity in BLOCKING_SEVERITIES:
        return "blocked"
    if alert.severity in IMPAIRING_SEVERITIES:
        return "impaired"
    return "clear"


def _classify_disaster(disaster: fema.Disaster) -> str:
    if disaster.type in BLOCKING_DISASTER_TYPES:
        return "blocked"
    return "impaired"


def _worse(a: str, b: str) -> str:
    rank = {"clear": 0, "impaired": 1, "blocked": 2}
    return a if rank[a] >= rank[b] else b


def check_route_status(
    corridor_id: str,
    *,
    alerts: Iterable[noaa.WeatherAlert] | None = None,
    disasters: Iterable[fema.Disaster] | None = None,
    corridors: dict[str, dict[str, Any]] | None = None,
) -> CorridorStatus:
    """
    Compute current status for one corridor.

    Args:
        corridor_id: e.g. "I-80"
        alerts:      NWS alerts to intersect. If None, fetches live for every
                     state in the corridor via noaa.fetch_weather_alerts.
        disasters:   FEMA disasters. If None, fetches live.
        corridors:   Override corridor definitions (for tests).

    Returns:
        CorridorStatus with status, human-readable reason, est. duration.
    """
    cors = corridors if corridors is not None else load_corridors()
    if corridor_id not in cors:
        raise KeyError(f"Unknown corridor: {corridor_id}")

    corridor = cors[corridor_id]
    waypoints = [_Waypoint(**w) for w in corridor["waypoints"]]
    waypoint_keys = {w.key for w in waypoints}
    states = {w.state.upper() for w in waypoints}

    # Lazily fetch if not provided
    if alerts is None:
        alerts = []
        for st in states:
            try:
                alerts.extend(noaa.fetch_weather_alerts(st))
            except Exception as e:  # noqa: BLE001
                logger.warning("NOAA fetch failed for %s: %s", st, e)
    if disasters is None:
        disasters = []
        for st in states:
            try:
                disasters.extend(fema.fetch_fema_disasters(st))
            except Exception as e:  # noqa: BLE001
                logger.warning("FEMA fetch failed for %s: %s", st, e)

    impaired_segments: list[dict[str, Any]] = []
    status = "clear"
    worst_expiry: str | None = None
    reasons: list[str] = []

    # --- NOAA alerts ---
    for alert in alerts:
        hits = _alert_affected_keys(alert) & waypoint_keys
        if not hits:
            continue
        alert_status = _classify_alert(alert)
        if alert_status == "clear":
            continue
        status = _worse(status, alert_status)
        for state, county in sorted(hits):
            impaired_segments.append({
                "state": state,
                "county": county,
                "source": "NOAA",
                "reason": alert.event,
                "severity": alert.severity,
                "expires_at": alert.expires_at,
            })
        if alert.expires_at:
            if worst_expiry is None or alert.expires_at > worst_expiry:
                worst_expiry = alert.expires_at
        reasons.append(f"{alert.event} ({alert.severity}) in "
                       f"{len(hits)} segment(s)")

    # --- FEMA disasters ---
    for d in disasters:
        hits = _disaster_affected_keys(d) & waypoint_keys
        if not hits:
            continue
        d_status = _classify_disaster(d)
        status = _worse(status, d_status)
        for state, county in sorted(hits):
            impaired_segments.append({
                "state": state,
                "county": county,
                "source": "FEMA",
                "reason": d.type,
                "severity": "Disaster",
                "expires_at": d.incident_end_date,
            })
        if d.incident_end_date and (worst_expiry is None
                                    or d.incident_end_date > worst_expiry):
            worst_expiry = d.incident_end_date
        reasons.append(f"FEMA {d.type} disaster #{d.disaster_number} "
                       f"in {len(hits)} segment(s)")

    reason = "; ".join(reasons) if reasons else "no active disruptions"

    return CorridorStatus(
        corridor_id=corridor_id,
        status=status,
        reason=reason,
        estimated_duration=worst_expiry,
        impaired_segments=impaired_segments,
        crop_types=list(corridor.get("crop_types", [])),
    )


def check_all_corridors(
    *,
    alerts: Iterable[noaa.WeatherAlert] | None = None,
    disasters: Iterable[fema.Disaster] | None = None,
) -> list[CorridorStatus]:
    """Run check_route_status for every corridor, fetching data once."""
    corridors = load_corridors()

    # If the caller didn't supply, fetch once for all states we care about.
    if alerts is None or disasters is None:
        all_states = {w["state"].upper()
                      for c in corridors.values()
                      for w in c["waypoints"]}
        if alerts is None:
            alerts = []
            for st in all_states:
                try:
                    alerts.extend(noaa.fetch_weather_alerts(st))
                except Exception as e:  # noqa: BLE001
                    logger.warning("NOAA fetch failed for %s: %s", st, e)
        if disasters is None:
            disasters = []
            for st in all_states:
                try:
                    disasters.extend(fema.fetch_fema_disasters(st))
                except Exception as e:  # noqa: BLE001
                    logger.warning("FEMA fetch failed for %s: %s", st, e)

    alerts = list(alerts)
    disasters = list(disasters)

    return [
        check_route_status(cid, alerts=alerts, disasters=disasters,
                           corridors=corridors)
        for cid in corridors
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Check freight corridor status.")
    parser.add_argument("corridor", nargs="?", default=None,
                        help="Corridor id (I-5, I-10, I-80, I-35). "
                             "Omit to check all.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.corridor:
        statuses = [check_route_status(args.corridor)]
    else:
        statuses = check_all_corridors()

    if args.json:
        print(json.dumps([s.to_dict() for s in statuses], indent=2))
        return

    for s in statuses:
        tag = {"clear": "[OK]   ", "impaired": "[WARN] ", "blocked": "[STOP] "}[s.status]
        print(f"{tag} {s.corridor_id:<6} {s.status.upper():<9} "
              f"{s.reason}")
        if s.estimated_duration:
            print(f"         through: {s.estimated_duration}")
        for seg in s.impaired_segments[:5]:
            print(f"         - {seg['state']} {seg['county'].title():<18} "
                  f"{seg['source']}: {seg['reason']} ({seg['severity']})")
        if len(s.impaired_segments) > 5:
            print(f"         ... +{len(s.impaired_segments) - 5} more")
        print()


if __name__ == "__main__":
    _cli()
