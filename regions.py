"""
regions.py — Central region registry for RootBridge.

Single source of truth that maps a region_id string to:
  - The US state code(s) the region spans
  - The counties (parishes/boroughs) within that region
  - A human-readable display name
  - The bounding box (WGS84) for satellite / crop-health queries

Design goals
------------
1. Any US state can be looked up by its two-letter FIPS code or by a
   sub-state region slug derived from supply_corridors.json.
2. `get_region(region_id)` raises a typed RegionNotFoundError — never
   silently falls back to a default state (fixes the Atlantis bug).
3. County lists drive the disruptions shim's alert filtering, so
   "terrebonne" and "lafourche" return different data from the NOAA/FEMA APIs.
4. The registry is auto-seeded from supply_corridors.json for parish-level
   regions, and covers all 50 US states for the state-picker UI flow.

Usage
-----
    from regions import get_region, list_regions, RegionNotFoundError

    region = get_region("terrebonne")
    # RegionInfo(id='terrebonne', display_name='Terrebonne Parish, LA',
    #            state_codes=['LA'], counties=['Terrebonne'], ...)

    region = get_region("TX")       # works too — whole-state lookup
    region = get_region("atlantis") # raises RegionNotFoundError
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegionInfo:
    id: str                          # slug, e.g. "terrebonne", "LA", "TX"
    display_name: str                # e.g. "Terrebonne Parish, LA"
    state_codes: list[str]           # one or more two-letter FIPS codes
    counties: list[str]              # county/parish names within the region
                                     # (empty list = whole-state query)
    bbox: Optional[tuple[float, float, float, float]] = None
    # (min_lon, min_lat, max_lon, max_lat) WGS84; None = derive from state

    @property
    def primary_state(self) -> str:
        return self.state_codes[0]

    @property
    def is_whole_state(self) -> bool:
        return len(self.counties) == 0


class RegionNotFoundError(KeyError):
    """Raised when get_region() is called with an unrecognised region_id."""
    def __init__(self, region_id: str, known: list[str]):
        self.region_id = region_id
        self.known = known
        super().__init__(
            f"Unknown region: {region_id!r}. "
            f"Known regions: {sorted(known)}"
        )


# ---------------------------------------------------------------------------
# All 50 US states — whole-state entries (no county filter)
# Bboxes are approximate state extents in WGS84.
# ---------------------------------------------------------------------------

_US_STATE_ENTRIES: list[dict] = [
    {"id": "AL", "display_name": "Alabama",             "state_codes": ["AL"], "bbox": (-88.47, 30.14, -84.89, 35.01)},
    {"id": "AK", "display_name": "Alaska",              "state_codes": ["AK"], "bbox": (-179.99, 51.21, -129.99, 71.35)},
    {"id": "AZ", "display_name": "Arizona",             "state_codes": ["AZ"], "bbox": (-114.82, 31.33, -109.04, 37.00)},
    {"id": "AR", "display_name": "Arkansas",            "state_codes": ["AR"], "bbox": (-94.62, 33.00, -89.64, 36.50)},
    {"id": "CA", "display_name": "California",          "state_codes": ["CA"], "bbox": (-124.41, 32.53, -114.13, 42.01)},
    {"id": "CO", "display_name": "Colorado",            "state_codes": ["CO"], "bbox": (-109.06, 36.99, -102.04, 41.00)},
    {"id": "CT", "display_name": "Connecticut",         "state_codes": ["CT"], "bbox": (-73.73, 40.95, -71.79, 42.05)},
    {"id": "DE", "display_name": "Delaware",            "state_codes": ["DE"], "bbox": (-75.79, 38.45, -75.05, 39.84)},
    {"id": "FL", "display_name": "Florida",             "state_codes": ["FL"], "bbox": (-87.63, 24.52, -80.03, 31.00)},
    {"id": "GA", "display_name": "Georgia",             "state_codes": ["GA"], "bbox": (-85.61, 30.36, -80.84, 35.00)},
    {"id": "HI", "display_name": "Hawaii",              "state_codes": ["HI"], "bbox": (-160.25, 18.91, -154.81, 22.24)},
    {"id": "ID", "display_name": "Idaho",               "state_codes": ["ID"], "bbox": (-117.24, 41.99, -111.04, 49.00)},
    {"id": "IL", "display_name": "Illinois",            "state_codes": ["IL"], "bbox": (-91.51, 36.97, -87.49, 42.51)},
    {"id": "IN", "display_name": "Indiana",             "state_codes": ["IN"], "bbox": (-88.10, 37.77, -84.78, 41.77)},
    {"id": "IA", "display_name": "Iowa",                "state_codes": ["IA"], "bbox": (-96.64, 40.37, -90.14, 43.50)},
    {"id": "KS", "display_name": "Kansas",              "state_codes": ["KS"], "bbox": (-102.05, 36.99, -94.59, 40.00)},
    {"id": "KY", "display_name": "Kentucky",            "state_codes": ["KY"], "bbox": (-89.57, 36.50, -81.96, 39.15)},
    {"id": "LA", "display_name": "Louisiana",           "state_codes": ["LA"], "bbox": (-94.04, 28.93, -88.82, 33.02)},
    {"id": "ME", "display_name": "Maine",               "state_codes": ["ME"], "bbox": (-71.08, 43.06, -66.95, 47.46)},
    {"id": "MD", "display_name": "Maryland",            "state_codes": ["MD"], "bbox": (-79.49, 37.89, -75.05, 39.72)},
    {"id": "MA", "display_name": "Massachusetts",       "state_codes": ["MA"], "bbox": (-73.51, 41.24, -69.93, 42.89)},
    {"id": "MI", "display_name": "Michigan",            "state_codes": ["MI"], "bbox": (-90.42, 41.70, -82.41, 48.19)},
    {"id": "MN", "display_name": "Minnesota",           "state_codes": ["MN"], "bbox": (-97.24, 43.50, -89.49, 49.38)},
    {"id": "MS", "display_name": "Mississippi",         "state_codes": ["MS"], "bbox": (-91.65, 30.17, -88.10, 35.01)},
    {"id": "MO", "display_name": "Missouri",            "state_codes": ["MO"], "bbox": (-95.77, 35.99, -89.10, 40.61)},
    {"id": "MT", "display_name": "Montana",             "state_codes": ["MT"], "bbox": (-116.05, 44.36, -104.04, 49.00)},
    {"id": "NE", "display_name": "Nebraska",            "state_codes": ["NE"], "bbox": (-104.05, 39.99, -95.31, 43.00)},
    {"id": "NV", "display_name": "Nevada",              "state_codes": ["NV"], "bbox": (-120.00, 35.00, -114.03, 42.00)},
    {"id": "NH", "display_name": "New Hampshire",       "state_codes": ["NH"], "bbox": (-72.56, 42.70, -70.70, 45.31)},
    {"id": "NJ", "display_name": "New Jersey",          "state_codes": ["NJ"], "bbox": (-75.56, 38.93, -73.89, 41.36)},
    {"id": "NM", "display_name": "New Mexico",          "state_codes": ["NM"], "bbox": (-109.05, 31.33, -103.00, 37.00)},
    {"id": "NY", "display_name": "New York",            "state_codes": ["NY"], "bbox": (-79.76, 40.50, -71.86, 45.01)},
    {"id": "NC", "display_name": "North Carolina",      "state_codes": ["NC"], "bbox": (-84.32, 33.84, -75.46, 36.59)},
    {"id": "ND", "display_name": "North Dakota",        "state_codes": ["ND"], "bbox": (-104.05, 45.93, -96.55, 49.00)},
    {"id": "OH", "display_name": "Ohio",                "state_codes": ["OH"], "bbox": (-84.82, 38.40, -80.52, 42.00)},
    {"id": "OK", "display_name": "Oklahoma",            "state_codes": ["OK"], "bbox": (-103.00, 33.62, -94.43, 37.00)},
    {"id": "OR", "display_name": "Oregon",              "state_codes": ["OR"], "bbox": (-124.57, 41.99, -116.46, 46.26)},
    {"id": "PA", "display_name": "Pennsylvania",        "state_codes": ["PA"], "bbox": (-80.52, 39.72, -74.69, 42.27)},
    {"id": "RI", "display_name": "Rhode Island",        "state_codes": ["RI"], "bbox": (-71.86, 41.15, -71.12, 42.02)},
    {"id": "SC", "display_name": "South Carolina",      "state_codes": ["SC"], "bbox": (-83.35, 32.05, -78.54, 35.21)},
    {"id": "SD", "display_name": "South Dakota",        "state_codes": ["SD"], "bbox": (-104.06, 42.48, -96.44, 45.94)},
    {"id": "TN", "display_name": "Tennessee",           "state_codes": ["TN"], "bbox": (-90.31, 34.98, -81.65, 36.68)},
    {"id": "TX", "display_name": "Texas",               "state_codes": ["TX"], "bbox": (-106.65, 25.84, -93.51, 36.50)},
    {"id": "UT", "display_name": "Utah",                "state_codes": ["UT"], "bbox": (-114.05, 37.00, -109.04, 42.00)},
    {"id": "VT", "display_name": "Vermont",             "state_codes": ["VT"], "bbox": (-73.44, 42.73, -71.46, 45.02)},
    {"id": "VA", "display_name": "Virginia",            "state_codes": ["VA"], "bbox": (-83.68, 36.54, -75.24, 39.47)},
    {"id": "WA", "display_name": "Washington",          "state_codes": ["WA"], "bbox": (-124.73, 45.54, -116.92, 49.00)},
    {"id": "WV", "display_name": "West Virginia",       "state_codes": ["WV"], "bbox": (-82.64, 37.20, -77.72, 40.64)},
    {"id": "WI", "display_name": "Wisconsin",           "state_codes": ["WI"], "bbox": (-92.89, 42.49, -86.25, 47.08)},
    {"id": "WY", "display_name": "Wyoming",             "state_codes": ["WY"], "bbox": (-111.06, 40.99, -104.05, 45.01)},
    {"id": "DC", "display_name": "Washington D.C.",     "state_codes": ["DC"], "bbox": (-77.12, 38.79, -76.91, 38.99)},
]

# ---------------------------------------------------------------------------
# Registry build
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, RegionInfo] = {}


def _build_registry() -> None:
    """
    Populate _REGISTRY with:
    1. All 50 US state whole-state entries (keyed by state code, e.g. "LA").
    2. Sub-state parish/county entries auto-seeded from supply_corridors.json
       (keyed by source_region slug, e.g. "terrebonne").
    """
    # 1. US states
    for entry in _US_STATE_ENTRIES:
        info = RegionInfo(
            id=entry["id"],
            display_name=entry["display_name"],
            state_codes=entry["state_codes"],
            counties=[],       # whole-state: no county filter
            bbox=tuple(entry["bbox"]) if entry.get("bbox") else None,
        )
        _REGISTRY[entry["id"].lower()] = info
        # Also index by uppercase for convenience (e.g. "LA" and "la" both work)
        _REGISTRY[entry["id"].upper()] = info

    # 2. Sub-state regions from supply_corridors.json
    corridors_path = Path(__file__).parent / "supply_corridors.json"
    if not corridors_path.exists():
        return

    data = json.loads(corridors_path.read_text())
    for corridor in data.get("corridors", []):
        region_slug = corridor.get("source_region", "").strip().lower()
        if not region_slug or region_slug in _REGISTRY:
            continue

        # Collect counties: prefer explicit source_counties, fall back to waypoints.
        # source_counties = the producing region only (e.g. ["Terrebonne"])
        # waypoints       = full route including transit counties — too broad for alert filtering
        counties: list[str] = []
        state_codes: list[str] = []

        if corridor.get("source_counties"):
            counties = [c.strip() for c in corridor["source_counties"] if c.strip()]
            # Derive state from waypoints (still needed for the API call)
            for wp in corridor.get("waypoints", []):
                state = wp.get("state", "").strip().upper()
                if state and state not in state_codes:
                    state_codes.append(state)
        else:
            # Fallback: use waypoints (acceptable when corridor doesn't cross parish boundaries)
            for wp in corridor.get("waypoints", []):
                county = wp.get("county", "").strip()
                state  = wp.get("state", "").strip().upper()
                if county and county not in counties:
                    counties.append(county)
                if state and state not in state_codes:
                    state_codes.append(state)

        if not state_codes:
            continue

        # Derive display name
        primary_state = state_codes[0]
        county_str = " / ".join(counties) if counties else primary_state
        display_name = f"{county_str} Parish, {primary_state}"

        bbox_raw = corridor.get("source_bbox")
        bbox = tuple(bbox_raw) if bbox_raw and len(bbox_raw) == 4 else None

        info = RegionInfo(
            id=region_slug,
            display_name=display_name,
            state_codes=state_codes,
            counties=counties,
            bbox=bbox,
        )
        _REGISTRY[region_slug] = info


_build_registry()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_region(region_id: str) -> RegionInfo:
    """
    Look up a region by its slug or two-letter state code.

    Raises RegionNotFoundError (a KeyError subclass) if not found.
    Never silently defaults to a fallback state.

    Examples
    --------
        get_region("terrebonne")  # → Terrebonne Parish, LA
        get_region("LA")          # → whole-state Louisiana
        get_region("TX")          # → whole-state Texas
        get_region("atlantis")    # → RegionNotFoundError
    """
    key = region_id.strip()
    result = _REGISTRY.get(key) or _REGISTRY.get(key.lower()) or _REGISTRY.get(key.upper())
    if result is None:
        raise RegionNotFoundError(region_id, list(_REGISTRY.keys()))
    return result


def list_regions(state_code: str | None = None) -> list[RegionInfo]:
    """
    Return all registered regions.

    Pass state_code (e.g. "LA") to filter to regions within that state.
    Whole-state entries and sub-state entries are both returned.
    """
    seen: set[str] = set()
    out: list[RegionInfo] = []
    for info in _REGISTRY.values():
        if info.id in seen:
            continue
        seen.add(info.id)
        if state_code and state_code.upper() not in info.state_codes:
            continue
        out.append(info)
    return sorted(out, key=lambda r: r.display_name)


def counties_for_region(region_id: str) -> list[str]:
    """
    Return the county list for a region (empty list = whole state).
    Raises RegionNotFoundError if region_id is unknown.
    """
    return list(get_region(region_id).counties)


def state_codes_for_region(region_id: str) -> list[str]:
    """
    Return the state code(s) for a region.
    Raises RegionNotFoundError if region_id is unknown.
    """
    return list(get_region(region_id).state_codes)