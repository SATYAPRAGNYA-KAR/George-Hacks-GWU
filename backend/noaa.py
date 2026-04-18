"""
NOAA / National Weather Service active-alerts integration.

Pulls active watches, warnings, and advisories for the categories our risk
engine cares about — drought, extreme heat, frost/freeze, and flood — and
normalizes them into the shape Builder 3 expects.

API docs:    https://www.weather.gov/documentation/services-web-api
Endpoint:    https://api.weather.gov/alerts/active
Auth:        none (but a descriptive User-Agent is required)
Format:      GeoJSON (FeatureCollection)

Author: Ruhani (Builder 2)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.weather.gov/alerts/active"
DEFAULT_TIMEOUT = 20
USER_AGENT = (
    "GeorgeHacks-FoodSecurity/0.1 "
    "(https://github.com/SATYAPRAGNYA-KAR/George-Hacks-GWU; rmn2151@columbia.edu)"
)


# ---------------------------------------------------------------------------
# Event-category taxonomy — maps NWS event strings to our four buckets.
# Anything not in this map is dropped.
# ---------------------------------------------------------------------------
CATEGORY_EVENTS: dict[str, tuple[str, ...]] = {
    "drought": (
        "Drought Information Statement",
    ),
    "heat": (
        "Excessive Heat Warning",
        "Excessive Heat Watch",
        "Heat Advisory",
        "Extreme Heat Warning",
        "Extreme Heat Watch",
    ),
    "frost": (
        "Frost Advisory",
        "Freeze Warning",
        "Freeze Watch",
        "Hard Freeze Warning",
        "Hard Freeze Watch",
    ),
    "flood": (
        "Flood Warning",
        "Flood Watch",
        "Flood Advisory",
        "Flash Flood Warning",
        "Flash Flood Watch",
        "Coastal Flood Warning",
        "Coastal Flood Watch",
        "Coastal Flood Advisory",
        "River Flood Warning",
        "River Flood Watch",
    ),
}

EVENT_TO_CATEGORY: dict[str, str] = {
    ev: cat for cat, events in CATEGORY_EVENTS.items() for ev in events
}

DEFAULT_CATEGORIES = tuple(CATEGORY_EVENTS.keys())


# ---------------------------------------------------------------------------
# Normalized output shape (what Builder 3 consumes)
# ---------------------------------------------------------------------------
@dataclass
class WeatherAlert:
    id: str
    alert_type: str          # our bucket: drought | heat | frost | flood
    event: str               # NWS event, e.g. "Flood Warning"
    severity: str            # Minor | Moderate | Severe | Extreme | Unknown
    affected_area: str       # areaDesc: "Polk, IA; Story, IA"
    expires_at: str | None   # ISO 8601
    effective_at: str | None = None
    headline: str | None = None
    areas: list[str] = field(default_factory=list)  # split areaDesc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------
def _request_nws(params: dict[str, Any], timeout: int) -> dict[str, Any]:
    """Thin HTTP wrapper — monkey-patched in tests."""
    url = f"{BASE_URL}?{urlencode(params)}"
    logger.info("GET %s", url)
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
    )
    resp.raise_for_status()
    return resp.json()


def fetch_weather_alerts(
    region: str,
    *,
    categories: Iterable[str] = DEFAULT_CATEGORIES,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[WeatherAlert]:
    """
    Fetch active NWS alerts for a region, filtered to the categories we care
    about (drought, heat, frost, flood by default).

    Args:
        region:     two-letter state code ("IA") or "lat,lon" point string
                    ("41.59,-93.62").
        categories: subset of {"drought","heat","frost","flood"}.
        timeout:    HTTP timeout in seconds.

    Returns:
        List of WeatherAlert, newest (by effective time) first.

    Raises:
        requests.HTTPError, requests.ConnectionError on network failure.
        ValueError if an unknown category is passed.
    """
    cats = tuple(categories)
    unknown = [c for c in cats if c not in CATEGORY_EVENTS]
    if unknown:
        raise ValueError(
            f"Unknown categories: {unknown}. "
            f"Valid: {sorted(CATEGORY_EVENTS)}"
        )

    wanted_events = {
        ev for c in cats for ev in CATEGORY_EVENTS[c]
    }

    params: dict[str, Any] = {"status": "actual"}
    # NWS accepts `area=IA` for state filters and `point=lat,lon` for points.
    region = region.strip()
    if "," in region:
        params["point"] = region
    else:
        params["area"] = region.upper()

    # NWS supports filtering events server-side but the list can be long and
    # strings must match exactly (including spaces). We pass our candidate
    # list and also filter client-side to stay resilient to vocabulary drift.
    params["event"] = ",".join(sorted(wanted_events))

    payload = _request_nws(params, timeout=timeout)
    features = payload.get("features", []) or []

    alerts = _normalize_features(features, wanted_events)

    # Newest effective first; fall back to expires, then id for stability
    alerts.sort(
        key=lambda a: (a.effective_at or "", a.expires_at or "", a.id),
        reverse=True,
    )
    return alerts


def _normalize_features(
    features: Iterable[dict[str, Any]],
    wanted_events: set[str],
) -> list[WeatherAlert]:
    out: list[WeatherAlert] = []
    for f in features:
        props = f.get("properties") or {}
        event = props.get("event") or ""
        if event not in wanted_events:
            continue

        area_desc = props.get("areaDesc") or ""
        areas = [a.strip() for a in area_desc.split(";") if a.strip()]

        out.append(WeatherAlert(
            id=f.get("id") or props.get("id") or "",
            alert_type=EVENT_TO_CATEGORY.get(event, "unknown"),
            event=event,
            severity=props.get("severity") or "Unknown",
            affected_area=area_desc,
            areas=areas,
            expires_at=props.get("expires"),
            effective_at=props.get("effective"),
            headline=props.get("headline"),
        ))
    return out


# ---------------------------------------------------------------------------
# CLI for quick manual testing
# ---------------------------------------------------------------------------
def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch active NWS alerts.")
    parser.add_argument("region",
                        help="State code ('IA') or lat,lon point ('41.6,-93.6')")
    parser.add_argument("--categories", nargs="*", default=list(DEFAULT_CATEGORIES),
                        help=f"Subset of {sorted(CATEGORY_EVENTS)}")
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    alerts = fetch_weather_alerts(args.region, categories=args.categories)

    if args.json:
        print(json.dumps([a.to_dict() for a in alerts], indent=2))
        return

    if not alerts:
        print(f"No active {'/'.join(args.categories)} alerts for {args.region}.")
        return

    print(f"{len(alerts)} active alert(s) for {args.region}:\n")
    for a in alerts:
        print(f"  [{a.alert_type.upper():<7}] {a.severity:<8} {a.event}")
        print(f"    {a.headline or ''}")
        print(f"    Area: {a.affected_area[:80]}"
              f"{'...' if len(a.affected_area) > 80 else ''}")
        print(f"    Expires: {a.expires_at}")
        print()


if __name__ == "__main__":
    _cli()
