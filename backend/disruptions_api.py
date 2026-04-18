"""
Disruptions API — Builder 3 shim  (v2 — region-aware)

Wraps Builder 2's fema.py, noaa.py, and routes.py into a single unified
GET /api/disruptions/{region_id} endpoint.

Changes from v1
---------------
* Uses regions.py as the single source of truth for region → state + counties.
  Raises HTTP 404 (via RegionNotFoundError) for unknown region slugs instead
  of silently defaulting to Louisiana.
* County-level filtering: NOAA alerts and FEMA declarations are filtered to
  only the counties that belong to the requested region. "terrebonne" and
  "lafourche" now return genuinely different alert sets.
* Whole-state queries (e.g. region_id="LA") are still supported — they skip
  county filtering because RegionInfo.counties is empty for state-level entries.
* State-picker UI flow: the frontend passes a two-letter state code
  (e.g. "TX") and gets back that state's disruptions with no county filter.

Endpoint contract (matches what risk_engine.py expects):
  {
    "region_id":      str,
    "display_name":   str,
    "state_codes":    [str],
    "counties":       [str],          # empty = whole-state query
    "overall_status": "clear" | "impaired" | "blocked",
    "weather_alerts": [...],
    "disasters":      [...],
    "route_statuses": [...],
    "generated_at":   ISO str,
    "_mock":          bool
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
# Ensure project root is on sys.path so regions.py is importable whether
# this file is run directly or imported from api.py at the repo root.
# ---------------------------------------------------------------------------
_root_dir    = Path(__file__).parent.parent   # repo root
_backend_dir = Path(__file__).parent          # backend/

for _p in (_root_dir, _backend_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from regions import RegionInfo, RegionNotFoundError, get_region  # noqa: E402

# ---------------------------------------------------------------------------
# Import Builder 2 modules (live in backend/)
# ---------------------------------------------------------------------------
# fema_mod / noaa_mod / routes_mod are ALWAYS defined at module level
# (as None when unavailable) so unittest.mock.patch.object can replace
# them in tests regardless of whether the real modules are installed.
fema_mod   = None
noaa_mod   = None
routes_mod = None

try:
    import fema as fema_mod      # type: ignore[assignment]
    import noaa as noaa_mod      # type: ignore[assignment]
    import routes as routes_mod  # type: ignore[assignment]
    _B2_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "Builder 2 modules not importable: %s. Disruption data will be mocked.", e
    )
    _B2_AVAILABLE = False

# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------
_STATUS_RANK = {"clear": 0, "impaired": 1, "blocked": 2}
_SEV_RANK    = {"Minor": 1, "Moderate": 2, "Severe": 3, "Extreme": 4}


def _worst_status(*statuses: str) -> str:
    return max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))


# ---------------------------------------------------------------------------
# County-level filtering helpers
# ---------------------------------------------------------------------------

def _normalise_county(name: str) -> str:
    """Lower-case, strip 'Parish'/'County'/'Borough' suffixes for comparison."""
    n = name.strip().lower()
    for suffix in (" parish", " county", " borough", "(parish)", "(county)"):
        n = n.replace(suffix, "")
    return n.strip()


def _alert_touches_counties(alert: "noaa_mod.WeatherAlert",
                             target_counties: set[str]) -> bool:
    """
    Return True if the alert's affected area overlaps with target_counties.
    target_counties contains normalised names.
    """
    for piece in alert.areas:
        # NWS areaDesc pieces look like "Terrebonne, LA" or "Terrebonne"
        county_part = piece.split(",")[0].strip()
        if _normalise_county(county_part) in target_counties:
            return True
    return False


def _disaster_touches_counties(disaster: "fema_mod.Disaster",
                                target_counties: set[str]) -> bool:
    """
    Return True if any of the disaster's designated counties overlap
    with target_counties.
    """
    for county in disaster.counties:
        if _normalise_county(county) in target_counties:
            return True
    return False


# ---------------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------------

def _mock_disruptions(region: RegionInfo) -> dict[str, Any]:
    return {
        "region_id":      region.id,
        "display_name":   region.display_name,
        "state_codes":    region.state_codes,
        "counties":       region.counties,
        "overall_status": "clear",
        "weather_alerts": [],
        "disasters":      [],
        "route_statuses": [],
        "generated_at":   datetime.datetime.utcnow().isoformat() + "Z",
        "_mock":          True,
    }


# ---------------------------------------------------------------------------
# Live fetch — county-aware
# ---------------------------------------------------------------------------

def _fetch_live_disruptions(region: RegionInfo) -> dict[str, Any]:
    """
    Fetch disruptions for the given RegionInfo.

    If region.counties is non-empty (parish/sub-state query), filters all
    NOAA alerts and FEMA declarations to only those touching those counties.
    If region.counties is empty (whole-state query), no county filter is applied.
    """
    target_counties: set[str] = {
        _normalise_county(c) for c in region.counties
    }
    county_filter_active = bool(target_counties)

    # ---- Weather alerts ----
    raw_alerts_all: list["noaa_mod.WeatherAlert"] = []
    weather_status = "clear"
    for state in region.state_codes:
        try:
            raw_alerts_all.extend(noaa_mod.fetch_weather_alerts(state))
        except Exception as e:
            logger.warning("NOAA fetch failed for state=%s: %s", state, e)

    # County filter
    if county_filter_active:
        raw_alerts = [
            a for a in raw_alerts_all
            if _alert_touches_counties(a, target_counties)
        ]
    else:
        raw_alerts = raw_alerts_all

    weather_alerts = [a.to_dict() for a in raw_alerts]

    if raw_alerts:
        worst_sev = max(raw_alerts, key=lambda x: _SEV_RANK.get(x.severity, 0))
        sev_map = {
            "Extreme": "blocked", "Severe": "impaired",
            "Moderate": "impaired", "Minor": "clear",
        }
        weather_status = sev_map.get(worst_sev.severity, "clear")

    # ---- FEMA disasters ----
    raw_disasters_all: list["fema_mod.Disaster"] = []
    disaster_status = "clear"
    for state in region.state_codes:
        try:
            raw_disasters_all.extend(fema_mod.fetch_fema_disasters(state))
        except Exception as e:
            logger.warning("FEMA fetch failed for state=%s: %s", state, e)

    # County filter
    if county_filter_active:
        raw_disasters = [
            d for d in raw_disasters_all
            if _disaster_touches_counties(d, target_counties)
        ]
    else:
        raw_disasters = raw_disasters_all

    disasters = [d.to_dict() for d in raw_disasters]

    if raw_disasters:
        has_major = any(
            d.type in routes_mod.BLOCKING_DISASTER_TYPES
            for d in raw_disasters
        )
        disaster_status = "blocked" if has_major else "impaired"

    # ---- Route statuses ----
    # Re-use the already-filtered objects to avoid duplicate API calls.
    route_statuses: list[dict] = []
    route_status = "clear"
    try:
        # Reconstruct dataclass instances from dicts so routes module works
        alert_objs    = [noaa_mod.WeatherAlert(**a) for a in weather_alerts] or None
        disaster_objs = [fema_mod.Disaster(**d)     for d in disasters]      or None

        corridor_statuses = routes_mod.check_all_corridors(
            alerts=alert_objs,
            disasters=disaster_objs,
        )

        # If county filter active, keep only corridors whose waypoints overlap
        if county_filter_active:
            corridor_statuses = [
                cs for cs in corridor_statuses
                if any(
                    _normalise_county(seg.get("county", "")) in target_counties
                    for seg in cs.impaired_segments
                )
                or cs.status == "clear"   # always include clear corridors for context
            ]

        route_statuses = [cs.to_dict() for cs in corridor_statuses]
        if corridor_statuses:
            route_status = max(
                (cs.status for cs in corridor_statuses),
                key=lambda s: _STATUS_RANK.get(s, 0),
            )
    except Exception as e:
        logger.warning("Routes check failed: %s", e)

    overall = _worst_status(weather_status, disaster_status, route_status)

    return {
        "region_id":      region.id,
        "display_name":   region.display_name,
        "state_codes":    region.state_codes,
        "counties":       region.counties,
        "overall_status": overall,
        "weather_alerts": weather_alerts,
        "disasters":      disasters,
        "route_statuses": route_statuses,
        "generated_at":   datetime.datetime.utcnow().isoformat() + "Z",
        "_mock":          False,
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
    Return active disruptions for a region: weather alerts, FEMA declarations,
    and freight corridor statuses — filtered to the counties in that region.

    `region_id` accepts:
    - A two-letter US state code ("LA", "TX") for a whole-state query.
    - A sub-state parish/region slug ("terrebonne", "lafourche") for a
      county-filtered query. Slugs are defined in supply_corridors.json and
      auto-registered in regions.py at startup.

    Returns HTTP 404 for unrecognised region_id values (no silent fallback).
    """
    # Validate region — raises 404 if unknown (fixes the Atlantis bug)
    try:
        region = get_region(region_id)
    except RegionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error":    str(exc),
                "hint":     "Use a two-letter US state code (e.g. 'LA', 'TX') "
                            "or a corridor slug from supply_corridors.json "
                            "(e.g. 'terrebonne', 'lafourche').",
            },
        ) from exc

    if not _B2_AVAILABLE:
        return _mock_disruptions(region)

    try:
        return _fetch_live_disruptions(region)
    except Exception as e:
        logger.error("Disruption fetch failed for %s: %s", region_id, e)
        raise HTTPException(status_code=500, detail=str(e))