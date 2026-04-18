"""
Disruptions API — Builder 3 shim

Wraps Builder 2's fema.py, noaa.py, and routes.py into a single unified
GET /api/disruptions/{region_id} endpoint.

This runs in the SAME FastAPI process as the main api.py (port 8000),
eliminating the need for a separate Builder 2 service during the 1-day build.
Builder 4 / integration can later split this into its own service (port 8001)
by pointing BUILDER2_API env var at the separate host.

Endpoint contract (matches what risk_engine.py expects):
  {
    "region_id": str,
    "overall_status": "clear" | "impaired" | "blocked",
    "weather_alerts": [...],   // from noaa.fetch_weather_alerts
    "disasters": [...],        // from fema.fetch_fema_disasters
    "route_statuses": [...],   // from routes.check_all_corridors
    "generated_at": ISO str
  }

Author: Builder 3
"""

from __future__ import annotations

import datetime
import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import Builder 2 modules (they live in backend/)
# ---------------------------------------------------------------------------
_backend_dir = Path(__file__).parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

try:
    import fema as fema_mod
    import noaa as noaa_mod
    import routes as routes_mod
    _B2_AVAILABLE = True
except ImportError as e:
    logger.warning("Builder 2 modules not importable: %s. Disruption data will be mocked.", e)
    _B2_AVAILABLE = False

# ---------------------------------------------------------------------------
# State-level mapping for region_id → Louisiana state code
# ---------------------------------------------------------------------------
_REGION_STATE_MAP: dict[str, str] = {
    "louisiana":    "LA",
    "terrebonne":   "LA",
    "lafourche":    "LA",
    "st-mary":      "LA",
    "assumption":   "LA",
    "iberia":       "LA",
    "st-martin":    "LA",
    "vermilion":    "LA",
    "plaquemines":  "LA",
    "pointe-coupee":"LA",
    "concordia":    "LA",
    "tensas":       "LA",
    "east-carroll": "LA",
}

# Severity hierarchy for overall_status roll-up
_STATUS_RANK = {"clear": 0, "impaired": 1, "blocked": 2}


def _worst_status(*statuses: str) -> str:
    return max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))


# ---------------------------------------------------------------------------
# Mock fallback (used when Builder 2 modules can't be imported)
# ---------------------------------------------------------------------------

def _mock_disruptions(region_id: str) -> dict[str, Any]:
    return {
        "region_id": region_id,
        "overall_status": "clear",
        "weather_alerts": [],
        "disasters": [],
        "route_statuses": [],
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "_mock": True,
    }


# ---------------------------------------------------------------------------
# Live fetch
# ---------------------------------------------------------------------------

def _fetch_live_disruptions(region_id: str) -> dict[str, Any]:
    state = _REGION_STATE_MAP.get(region_id.lower(), "LA")

    # ---- Weather alerts ----
    weather_alerts = []
    weather_status = "clear"
    try:
        raw_alerts = noaa_mod.fetch_weather_alerts(state)
        for a in raw_alerts:
            weather_alerts.append(a.to_dict())
        if raw_alerts:
            worst_sev = max(
                raw_alerts,
                key=lambda x: {"Extreme": 4, "Severe": 3,
                               "Moderate": 2, "Minor": 1}.get(x.severity, 0),
            ).severity.lower()
            sev_map = {"extreme": "blocked", "severe": "impaired",
                       "moderate": "impaired", "minor": "clear"}
            weather_status = sev_map.get(worst_sev, "clear")
    except Exception as e:
        logger.warning("NOAA fetch failed for %s: %s", state, e)

    # ---- FEMA disasters ----
    disasters = []
    disaster_status = "clear"
    try:
        raw_disasters = fema_mod.fetch_fema_disasters(state)
        for d in raw_disasters:
            disasters.append(d.to_dict())
        if raw_disasters:
            has_major = any(
                d.type in routes_mod.BLOCKING_DISASTER_TYPES
                for d in raw_disasters
            )
            disaster_status = "blocked" if has_major else "impaired"
    except Exception as e:
        logger.warning("FEMA fetch failed for %s: %s", state, e)

    # ---- Route statuses ----
    route_statuses = []
    route_status = "clear"
    try:
        # Pass in the already-fetched data to avoid duplicate API calls
        corridor_statuses = routes_mod.check_all_corridors(
            alerts=[noaa_mod.WeatherAlert(**a) for a in weather_alerts] if weather_alerts else None,
            disasters=[fema_mod.Disaster(**d) for d in disasters] if disasters else None,
        )
        for cs in corridor_statuses:
            route_statuses.append(cs.to_dict())
        if corridor_statuses:
            route_status = max(
                (cs.status for cs in corridor_statuses),
                key=lambda s: _STATUS_RANK.get(s, 0),
            )
    except Exception as e:
        logger.warning("Routes check failed: %s", e)

    overall = _worst_status(weather_status, disaster_status, route_status)

    return {
        "region_id": region_id,
        "overall_status": overall,
        "weather_alerts": weather_alerts,
        "disasters": disasters,
        "route_statuses": route_statuses,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "_mock": False,
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()


@router.get(
    "/disruptions/{region_id}",
    summary="Unified disruption feed for a region",
    tags=["disruptions"],
)
def get_disruptions(region_id: str) -> dict[str, Any]:
    """
    Return all active disruptions for a region: weather alerts, FEMA
    disaster declarations, and freight corridor statuses.

    `region_id` should match a key in the supply_corridors.json
    source_region field (e.g. `louisiana`, `terrebonne`, `lafourche`).
    """
    if not _B2_AVAILABLE:
        return _mock_disruptions(region_id)

    try:
        return _fetch_live_disruptions(region_id)
    except Exception as e:
        logger.error("Disruption fetch failed for %s: %s", region_id, e)
        raise HTTPException(status_code=500, detail=str(e))