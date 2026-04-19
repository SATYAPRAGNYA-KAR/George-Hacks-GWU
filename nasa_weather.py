"""
nasa_weather.py — Real-time NASA / NOAA weather data for any US state

Sources
-------
1. NOAA/NWS Active Alerts API   https://api.weather.gov/alerts/active
   - Floods, drought, extreme heat, frost, coastal flood
   - No API key required; User-Agent header required

2. NASA FIRMS Fire/Anomaly API  https://firms.modaps.eosdis.nasa.gov/api/
   - Active fire and thermal anomaly detections
   - Free API key from https://firms.modaps.eosdis.nasa.gov/api/area/

3. NOAA NHC Storm Track         https://www.nhc.noaa.gov/CurrentStorms.json
   - Active tropical storm cones (hurricane season)
   - No API key required

4. US Drought Monitor           https://usdm.climate.unl.edu/services/
   - Current drought classifications D0-D4 by county
   - No API key required; GeoJSON endpoint

All functions accept `state_abbr` (two-letter code) or `county_fips` for
county-level filtering.  Returns normalized dicts consumed by risk_engine.py
and served directly to the frontend via /api/weather/{state_abbr}.

Author: Builder 3 — extended to all 50 states
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from datetime import date, timedelta

logger = logging.getLogger(__name__)

NWS_BASE   = "https://api.weather.gov"
FIRMS_KEY  = os.getenv("NASA_FIRMS_KEY", "")  # optional; increases rate limit
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
NHC_BASE   = "https://www.nhc.noaa.gov/CurrentStorms.json"
# USDM_BASE  = "https://usdm.climate.unl.edu/services/USDMServices.svc"
USDM_BASE = "https://usdmdataservices.unl.edu/api"

USER_AGENT = (
    "RootBridge-FoodSecurity/1.0 "
    "(https://github.com/SATYAPRAGNYA-KAR/George-Hacks-GWU; rootbridge@example.com)"
)

DEFAULT_TIMEOUT = 15

# NWS severity → our status rank
_SEV_RANK = {"Extreme": 4, "Severe": 3, "Moderate": 2, "Minor": 1, "Unknown": 0}

# NWS event → our category bucket
_EVENT_CATEGORIES: dict[str, str] = {
    "Flood Warning": "flood",        "Flood Watch": "flood",
    "Flash Flood Warning": "flood",  "Flash Flood Watch": "flood",
    "River Flood Warning": "flood",  "River Flood Watch": "flood",
    "Coastal Flood Warning": "flood","Coastal Flood Watch": "flood",
    "Coastal Flood Advisory": "flood",
    "Drought Information Statement": "drought",
    "Excessive Heat Warning": "heat","Excessive Heat Watch": "heat",
    "Extreme Heat Warning": "heat",  "Extreme Heat Watch": "heat",
    "Heat Advisory": "heat",
    "Frost Advisory": "frost",       "Freeze Warning": "frost",
    "Freeze Watch": "frost",         "Hard Freeze Warning": "frost",
    "Hard Freeze Watch": "frost",
    "Tornado Warning": "tornado",    "Tornado Watch": "tornado",
    "Severe Thunderstorm Warning": "severe_storm",
    "Winter Storm Warning": "winter","Blizzard Warning": "winter",
    "Ice Storm Warning": "winter",   "Winter Weather Advisory": "winter",
    "High Wind Warning": "wind",     "High Wind Watch": "wind",
}

# State FIPS prefix map for county filtering
_STATE_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
    "DC": "11",
}

# Approximate state bounding boxes for FIRMS queries
# Format: (min_lat, max_lat, min_lon, max_lon)
_STATE_BBOX: dict[str, tuple[float, float, float, float]] = {
    "AL": (30.14, 35.01, -88.47, -84.89), "AK": (51.21, 71.35, -179.99, -129.99),
    "AZ": (31.33, 37.00, -114.82, -109.04), "AR": (33.00, 36.50, -94.62, -89.64),
    "CA": (32.53, 42.01, -124.41, -114.13), "CO": (36.99, 41.00, -109.06, -102.04),
    "CT": (40.95, 42.05, -73.73, -71.79), "DE": (38.45, 39.84, -75.79, -75.05),
    "FL": (24.52, 31.00, -87.63, -80.03), "GA": (30.36, 35.00, -85.61, -80.84),
    "HI": (18.91, 22.24, -160.25, -154.81), "ID": (41.99, 49.00, -117.24, -111.04),
    "IL": (36.97, 42.51, -91.51, -87.49), "IN": (37.77, 41.77, -88.10, -84.78),
    "IA": (40.37, 43.50, -96.64, -90.14), "KS": (36.99, 40.00, -102.05, -94.59),
    "KY": (36.50, 39.15, -89.57, -81.96), "LA": (28.93, 33.02, -94.04, -88.82),
    "ME": (43.06, 47.46, -71.08, -66.95), "MD": (37.89, 39.72, -79.49, -75.05),
    "MA": (41.24, 42.89, -73.51, -69.93), "MI": (41.70, 48.19, -90.42, -82.41),
    "MN": (43.50, 49.38, -97.24, -89.49), "MS": (30.17, 35.01, -91.65, -88.10),
    "MO": (35.99, 40.61, -95.77, -89.10), "MT": (44.36, 49.00, -116.05, -104.04),
    "NE": (39.99, 43.00, -104.05, -95.31), "NV": (35.00, 42.00, -120.00, -114.03),
    "NH": (42.70, 45.31, -72.56, -70.70), "NJ": (38.93, 41.36, -75.56, -73.89),
    "NM": (31.33, 37.00, -109.05, -103.00), "NY": (40.50, 45.01, -79.76, -71.86),
    "NC": (33.84, 36.59, -84.32, -75.46), "ND": (45.93, 49.00, -104.05, -96.55),
    "OH": (38.40, 42.00, -84.82, -80.52), "OK": (33.62, 37.00, -103.00, -94.43),
    "OR": (41.99, 46.26, -124.57, -116.46), "PA": (39.72, 42.27, -80.52, -74.69),
    "RI": (41.15, 42.02, -71.86, -71.12), "SC": (32.05, 35.21, -83.35, -78.54),
    "SD": (42.48, 45.94, -104.06, -96.44), "TN": (34.98, 36.68, -90.31, -81.65),
    "TX": (25.84, 36.50, -106.65, -93.51), "UT": (37.00, 42.00, -114.05, -109.04),
    "VT": (42.73, 45.02, -73.44, -71.46), "VA": (36.54, 39.47, -83.68, -75.24),
    "WA": (45.54, 49.00, -124.73, -116.92), "WV": (37.20, 40.64, -82.64, -77.72),
    "WI": (42.49, 47.08, -92.89, -86.25), "WY": (40.99, 45.01, -111.06, -104.05),
    "DC": (38.79, 38.99, -77.12, -76.91),
}


def _get(url: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict | None:
    try:
        r = requests.get(
            url, params=params, timeout=timeout,
            # headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("GET %s failed: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# 1. NWS Active Alerts — any US state, with county-level filtering
# ---------------------------------------------------------------------------

def fetch_nws_alerts(
    state_abbr: str,
    county_fips: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch active NWS alerts for a state, optionally filtered to a county.

    Returns a list of normalized alert dicts:
      {id, category, event, severity, severity_rank,
       affected_area, areas, expires_at, effective_at, headline}
    """
    payload = _get(
        f"{NWS_BASE}/alerts/active",
        params={"status": "actual", "area": state_abbr.upper()},
    )
    if not payload:
        return []

    results = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        event    = props.get("event", "")
        category = _EVENT_CATEGORIES.get(event)
        if not category:
            continue   # skip events we don't care about

        area_desc = props.get("areaDesc", "")
        areas     = [a.strip() for a in area_desc.split(";") if a.strip()]

        # County filter: check if any area piece matches the target county
        if county_fips:
            # NWS uses FIPS in geocode property
            geocode = props.get("geocode", {})
            ugc_list = geocode.get("SAME", []) or []
            # SAME codes: state FIPS (2) + county FIPS (3) = 5 digits, prefixed with 0
            target = county_fips.zfill(6)  # NWS SAME is 6 chars: 0+FIPS5
            county_in_alert = any(
                code.lstrip("0") == county_fips.lstrip("0")
                or code == target
                for code in ugc_list
            )
            if not county_in_alert:
                # fallback: name match
                fips_prefix = _STATE_FIPS.get(state_abbr.upper(), "")
                county_name_hint = area_desc.split(",")[0].strip().lower()
                if not any(county_name_hint in a.lower() for a in areas):
                    continue

        results.append({
            "id":            feature.get("id", ""),
            "category":      category,
            "event":         event,
            "severity":      props.get("severity", "Unknown"),
            "severity_rank": _SEV_RANK.get(props.get("severity", ""), 0),
            "affected_area": area_desc,
            "areas":         areas,
            "expires_at":    props.get("expires"),
            "effective_at":  props.get("effective"),
            "headline":      props.get("headline"),
        })

    # Sort by severity descending
    results.sort(key=lambda x: x["severity_rank"], reverse=True)
    return results


def _worst_nws_status(alerts: list[dict]) -> str:
    """Roll up a list of alerts to clear/impaired/blocked."""
    if not alerts:
        return "clear"
    max_sev = max(a["severity_rank"] for a in alerts)
    if max_sev >= 4:  # Extreme
        return "blocked"
    if max_sev >= 2:  # Moderate or Severe
        return "impaired"
    return "clear"


# ---------------------------------------------------------------------------
# 2. NOAA NHC Active Tropical Storms
# ---------------------------------------------------------------------------

def fetch_active_storms() -> list[dict[str, Any]]:
    """
    Return active NHC tropical storm tracks. Empty list outside hurricane season
    or when no storms are active.
    """
    payload = _get(NHC_BASE, timeout=10)
    if not payload:
        return []

    storms = []
    for storm in payload.get("activeStorms", []):
        storms.append({
            "id":           storm.get("id"),
            "name":         storm.get("name"),
            "classification": storm.get("classification"),
            "intensity":    storm.get("intensity"),    # mph
            "pressure":     storm.get("pressure"),     # mb
            "latitude":     storm.get("latitude"),
            "longitude":    storm.get("longitude"),
            "movement_dir": storm.get("movementDir"),
            "movement_spd": storm.get("movementSpeed"),
            "public_advisory": storm.get("publicAdvisoryNumber"),
        })
    return storms


# ---------------------------------------------------------------------------
# 3. NASA FIRMS — fire/thermal anomaly detections
# ---------------------------------------------------------------------------

def fetch_firms_anomalies(
    state_abbr: str,
    days: int = 1,
) -> list[dict[str, Any]]:
    """
    Return recent FIRMS fire/thermal anomaly detections within a state bbox.
    Uses VIIRS SNPP (high resolution, 375m).

    If NASA_FIRMS_KEY is not set, returns empty list with a warning logged.
    """
    if not FIRMS_KEY:
        logger.debug("NASA_FIRMS_KEY not set — skipping FIRMS fetch for %s", state_abbr)
        return []

    bbox = _STATE_BBOX.get(state_abbr.upper())
    if not bbox:
        return []

    min_lat, max_lat, min_lon, max_lon = bbox
    area = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    url = f"{FIRMS_BASE}/VIIRS_SNPP_NRT/{area}/{days}/{FIRMS_KEY}"
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        text = r.text.strip()
        if not text or text.startswith("Error") or "Invalid" in text:
            return []

        rows = []
        lines = text.splitlines()
        if len(lines) < 2:
            return []

        headers_row = [h.strip() for h in lines[0].split(",")]
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < len(headers_row):
                continue
            row = dict(zip(headers_row, parts))
            rows.append({
                "latitude":      float(row.get("latitude", 0)),
                "longitude":     float(row.get("longitude", 0)),
                "brightness":    float(row.get("bright_ti4", 0) or row.get("brightness", 0)),
                "confidence":    row.get("confidence", "n"),
                "frp":           float(row.get("frp", 0) or 0),   # fire radiative power
                "acq_date":      row.get("acq_date", ""),
                "acq_time":      row.get("acq_time", ""),
                "type":          "fire_anomaly",
            })
        return rows
    except Exception as e:
        logger.warning("FIRMS fetch failed for %s: %s", state_abbr, e)
        return []


# ---------------------------------------------------------------------------
# 4. US Drought Monitor — current drought severity by state
# ---------------------------------------------------------------------------

def fetch_drought_status(state_abbr: str) -> dict[str, Any]:
    """
    Return current drought classification for a state from the US Drought Monitor.
    Returns {state_abbr, none_pct, d0_pct, d1_pct, d2_pct, d3_pct, d4_pct, max_class, as_of}
    """
    # USDM state statistics endpoint
    url = f"{USDM_BASE}/StateStatistics/GetDroughtSeverityStatisticsByArea"
    today = date.today()
    days_since_tuesday = (today.weekday() - 1) % 7  # Tuesday = weekday 1
    safe_end = today - timedelta(days=days_since_tuesday + 7)  # one extra week buffer

    params = {
        "aoi": state_abbr.upper(),
        "startdate": safe_end.strftime("%Y-%m-%d"),  # also try hyphenated format
        "enddate":   safe_end.strftime("%Y-%m-%d"),
        "statisticsType": "1",
    }
    payload = _get(url, params=params, timeout=10)

    if not payload:
        # Fallback: try the simple CSV endpoint
        return _drought_fallback(state_abbr)

    try:
        items = payload if isinstance(payload, list) else payload.get("value", [payload])
        if not items:
            return _drought_fallback(state_abbr)

        latest = items[-1]
        d0 = float(latest.get("D0", 0) or 0)
        d1 = float(latest.get("D1", 0) or 0)
        d2 = float(latest.get("D2", 0) or 0)
        d3 = float(latest.get("D3", 0) or 0)
        d4 = float(latest.get("D4", 0) or 0)
        none_pct = max(0.0, 100.0 - d0 - d1 - d2 - d3 - d4)

        if d4 > 5:   max_class = "D4"
        elif d3 > 5: max_class = "D3"
        elif d2 > 10:max_class = "D2"
        elif d1 > 20:max_class = "D1"
        elif d0 > 30:max_class = "D0"
        else:        max_class = "None"

        return {
            "state_abbr": state_abbr.upper(),
            "none_pct": round(none_pct, 1),
            "d0_pct": d0, "d1_pct": d1, "d2_pct": d2,
            "d3_pct": d3, "d4_pct": d4,
            "max_class": max_class,
            "as_of": latest.get("MapDate", ""),
            "source": "usdm",
        }
    except Exception as e:
        logger.warning("USDM parse failed for %s: %s", state_abbr, e)
        return _drought_fallback(state_abbr)


def _drought_fallback(state_abbr: str) -> dict[str, Any]:
    return {
        "state_abbr": state_abbr.upper(),
        "none_pct": 100.0,
        "d0_pct": 0.0, "d1_pct": 0.0, "d2_pct": 0.0,
        "d3_pct": 0.0, "d4_pct": 0.0,
        "max_class": "unknown",
        "as_of": "",
        "source": "unavailable",
    }


def _drought_severity_score(drought: dict) -> float:
    """Convert drought classification percentages to a 0-100 risk score."""
    return min(100.0, (
        drought["d0_pct"] * 0.10 +
        drought["d1_pct"] * 0.25 +
        drought["d2_pct"] * 0.45 +
        drought["d3_pct"] * 0.70 +
        drought["d4_pct"] * 1.00
    ))


# ---------------------------------------------------------------------------
# 5. Unified weather snapshot for a state (called by disruptions_api and risk_engine)
# ---------------------------------------------------------------------------

def get_state_weather_snapshot(state_abbr: str) -> dict[str, Any]:
    """
    Return a complete weather snapshot for a state combining NWS + NHC + FIRMS + USDM.

    This is the single function called by the risk engine for shock-exposure scoring.
    {
      state_abbr, overall_status, shock_score,
      nws_alerts, active_storms, firms_anomalies,
      drought, generated_at
    }
    """
    state = state_abbr.upper()
    nws   = fetch_nws_alerts(state)
    drought = fetch_drought_status(state)
    firms = fetch_firms_anomalies(state, days=1)

    # Only fetch storm tracks if in hurricane basin states
    hurricane_states = {"FL","GA","SC","NC","VA","MD","DE","NJ","NY","CT","RI","MA","NH","ME",
                        "TX","LA","MS","AL","AL","PR","VI","HI","GU"}
    storms = fetch_active_storms() if state in hurricane_states else []

    # Compute overall shock score 0-100
    nws_score     = min(100.0, len(nws) * 12 + max((a["severity_rank"] for a in nws), default=0) * 15)
    drought_score = _drought_severity_score(drought)
    storm_score   = min(100.0, sum(min(100.0, s.get("intensity", 0) / 1.8) for s in storms))
    firms_score   = min(40.0, len(firms) * 2.0)  # FIRMS anomalies add up to 40

    shock_score = round(min(100.0,
        nws_score    * 0.45 +
        drought_score* 0.30 +
        storm_score  * 0.15 +
        firms_score  * 0.10
    ), 1)

    overall_status = "clear"
    if shock_score >= 60:
        overall_status = "blocked"
    elif shock_score >= 30:
        overall_status = "impaired"

    return {
        "state_abbr":      state,
        "overall_status":  overall_status,
        "shock_score":     shock_score,
        "nws_alerts":      nws,
        "active_storms":   storms,
        "firms_anomalies": firms,
        "drought":         drought,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
    }


def get_county_weather_snapshot(state_abbr: str, county_fips: str) -> dict[str, Any]:
    """
    Same as get_state_weather_snapshot but filtered to a specific county.
    Used by the county-level FPI endpoint.
    """
    state  = state_abbr.upper()
    nws    = fetch_nws_alerts(state, county_fips=county_fips)
    drought = fetch_drought_status(state)  # county-level USDM not available free; use state

    nws_score     = min(100.0, len(nws) * 15 + max((a["severity_rank"] for a in nws), default=0) * 18)
    drought_score = _drought_severity_score(drought)
    shock_score   = round(min(100.0, nws_score * 0.60 + drought_score * 0.40), 1)

    return {
        "state_abbr":     state,
        "county_fips":    county_fips,
        "overall_status": "blocked" if shock_score >= 60 else "impaired" if shock_score >= 30 else "clear",
        "shock_score":    shock_score,
        "nws_alerts":     nws,
        "drought":        drought,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
    }