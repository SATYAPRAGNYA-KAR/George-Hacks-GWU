"""
Tests for backend/disruptions_api.py

Covers:
  1. regions.py — get_region 404 on unknown, county lists, state lookups
  2. County-filtering helpers (_alert_touches_counties, _disaster_touches_counties)
  3. _fetch_live_disruptions — terrebonne vs lafourche return different data
  4. _fetch_live_disruptions — whole-state "LA" skips county filter
  5. HTTP layer — FastAPI TestClient 200, 404, mock fallback path

Run with:
    pytest test_disruptions_api.py -v
"""

from __future__ import annotations

import sys
import types
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure imports resolve from repo root + backend/
# ---------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).parent
BACKEND_DIR = REPO_ROOT / "backend"

for p in (str(REPO_ROOT), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Minimal stub dataclasses that mimic fema_mod and noaa_mod shapes
# (so we don't need real network access)
# ---------------------------------------------------------------------------

@dataclass
class _StubWeatherAlert:
    id: str
    alert_type: str
    event: str
    severity: str
    affected_area: str
    expires_at: str | None
    effective_at: str | None = None
    headline: str | None = None
    areas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class _StubDisaster:
    disaster_number: int
    type: str
    state: str
    counties: list[str] = field(default_factory=list)
    declaration_date: str | None = None
    incident_begin_date: str | None = None
    incident_end_date: str | None = None
    declaration_title: str | None = None
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class _StubCorridorStatus:
    corridor_id: str
    status: str
    reason: str
    estimated_duration: str | None
    impaired_segments: list[dict] = field(default_factory=list)
    crop_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


# ---------------------------------------------------------------------------
# Fixtures — synthetic alerts scoped to specific parishes
# ---------------------------------------------------------------------------

TERREBONNE_ALERT = _StubWeatherAlert(
    id="nws-terrebonne-001",
    alert_type="flood",
    event="Flood Warning",
    severity="Severe",
    affected_area="Terrebonne, LA",
    expires_at="2026-04-20T00:00:00Z",
    areas=["Terrebonne, LA"],
)

LAFOURCHE_ALERT = _StubWeatherAlert(
    id="nws-lafourche-001",
    alert_type="flood",
    event="Coastal Flood Watch",
    severity="Moderate",
    affected_area="Lafourche, LA",
    expires_at="2026-04-21T00:00:00Z",
    areas=["Lafourche, LA"],
)

STATEWIDE_HEAT_ALERT = _StubWeatherAlert(
    id="nws-la-heat-001",
    alert_type="heat",
    event="Excessive Heat Warning",
    severity="Extreme",
    affected_area="Orleans, LA; Jefferson, LA; Terrebonne, LA; Lafourche, LA",
    expires_at="2026-04-19T18:00:00Z",
    areas=["Orleans, LA", "Jefferson, LA", "Terrebonne, LA", "Lafourche, LA"],
)

TERREBONNE_DISASTER = _StubDisaster(
    disaster_number=4701,
    type="Hurricane",
    state="LA",
    counties=["Terrebonne (Parish)", "Lafourche (Parish)"],
    declaration_title="Hurricane Ida",
    is_active=True,
)

CONCORDIA_DISASTER = _StubDisaster(
    disaster_number=4702,
    type="Flood",
    state="LA",
    counties=["Concordia (Parish)"],
    declaration_title="Mississippi River Flooding",
    is_active=True,
)

TERREBONNE_CORRIDOR = _StubCorridorStatus(
    corridor_id="terrebonne-houma",
    status="impaired",
    reason="Flood Warning (Severe) in 1 segment(s)",
    estimated_duration="2026-04-20T00:00:00Z",
    impaired_segments=[{"state": "LA", "county": "terrebonne",
                        "source": "NOAA", "reason": "Flood Warning",
                        "severity": "Severe", "expires_at": "2026-04-20T00:00:00Z"}],
)

CLEAR_CORRIDOR = _StubCorridorStatus(
    corridor_id="stmartin-breaux-bridge",
    status="clear",
    reason="no active disruptions",
    estimated_duration=None,
)


# ---------------------------------------------------------------------------
# Helper — build mock B2 modules
# ---------------------------------------------------------------------------

def _make_b2_mocks(
    weather_alerts: list | None = None,
    disasters: list | None = None,
    corridor_statuses: list | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (fema_mock, noaa_mock, routes_mock) with canned return values."""
    fema_mock   = MagicMock()
    noaa_mock   = MagicMock()
    routes_mock = MagicMock()

    noaa_mock.fetch_weather_alerts.return_value = weather_alerts or []
    noaa_mock.WeatherAlert = _StubWeatherAlert

    fema_mock.fetch_fema_disasters.return_value = disasters or []
    fema_mock.Disaster = _StubDisaster

    routes_mock.check_all_corridors.return_value = corridor_statuses or []
    routes_mock.BLOCKING_DISASTER_TYPES = {"Hurricane", "Tornado", "Earthquake", "Wildfire"}

    return fema_mock, noaa_mock, routes_mock


# ===========================================================================
# 1. regions.py unit tests
# ===========================================================================

class TestRegionsRegistry:

    def test_known_state_code_resolves(self):
        from regions import get_region
        r = get_region("LA")
        assert r.primary_state == "LA"
        assert r.is_whole_state  # no county filter for state-level

    def test_state_code_case_insensitive(self):
        from regions import get_region
        assert get_region("la").id == get_region("LA").id

    def test_parish_slug_resolves(self):
        from regions import get_region
        r = get_region("terrebonne")
        assert "LA" in r.state_codes
        assert "Terrebonne" in r.counties
        assert not r.is_whole_state

    def test_terrebonne_and_lafourche_have_different_counties(self):
        from regions import get_region
        t = get_region("terrebonne")
        l = get_region("lafourche")
        assert set(t.counties) != set(l.counties), (
            "terrebonne and lafourche must have different county lists"
        )

    def test_unknown_region_raises_not_found_error(self):
        from regions import get_region, RegionNotFoundError
        with pytest.raises(RegionNotFoundError) as exc_info:
            get_region("atlantis")
        assert "atlantis" in str(exc_info.value).lower()

    def test_unknown_region_error_carries_known_list(self):
        from regions import get_region, RegionNotFoundError
        with pytest.raises(RegionNotFoundError) as exc_info:
            get_region("narnia")
        assert exc_info.value.known  # non-empty list of valid IDs

    def test_all_50_states_registered(self):
        from regions import list_regions
        state_ids = {r.id.upper() for r in list_regions() if len(r.id) == 2}
        required = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
                    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
                    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
                    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
                    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"}
        missing = required - state_ids
        assert not missing, f"Missing states: {missing}"

    def test_list_regions_state_filter(self):
        from regions import list_regions
        la_regions = list_regions(state_code="LA")
        assert all("LA" in r.state_codes for r in la_regions)
        assert len(la_regions) >= 1

    def test_texas_is_whole_state(self):
        from regions import get_region
        tx = get_region("TX")
        assert tx.is_whole_state
        assert tx.counties == []

    def test_parish_has_bbox(self):
        from regions import get_region
        r = get_region("terrebonne")
        assert r.bbox is not None
        assert len(r.bbox) == 4


# ===========================================================================
# 2. County filtering helpers
# ===========================================================================

class TestCountyFiltering:

    def setup_method(self):
        import backend.disruptions_api as shim
        self.shim = shim

    def test_alert_in_terrebonne_matches_terrebonne(self):
        target = {"terrebonne"}
        assert self.shim._alert_touches_counties(TERREBONNE_ALERT, target)

    def test_alert_in_terrebonne_does_not_match_lafourche(self):
        target = {"lafourche"}
        assert not self.shim._alert_touches_counties(TERREBONNE_ALERT, target)

    def test_statewide_alert_matches_both_parishes(self):
        assert self.shim._alert_touches_counties(STATEWIDE_HEAT_ALERT, {"terrebonne"})
        assert self.shim._alert_touches_counties(STATEWIDE_HEAT_ALERT, {"lafourche"})

    def test_normalise_strips_parish_suffix(self):
        assert self.shim._normalise_county("Terrebonne Parish") == "terrebonne"
        assert self.shim._normalise_county("Terrebonne (Parish)") == "terrebonne"
        assert self.shim._normalise_county("Terrebonne") == "terrebonne"

    def test_disaster_county_match(self):
        target = {"terrebonne"}
        assert self.shim._disaster_touches_counties(TERREBONNE_DISASTER, target)

    def test_disaster_county_no_match(self):
        target = {"concordia"}
        assert not self.shim._disaster_touches_counties(TERREBONNE_DISASTER, target)

    def test_disaster_parish_suffix_normalisation(self):
        # counties in fixture are "Terrebonne (Parish)" — should still match
        target = {"terrebonne"}
        assert self.shim._disaster_touches_counties(TERREBONNE_DISASTER, target)


# ===========================================================================
# 3. _fetch_live_disruptions — terrebonne vs lafourche return different data
# ===========================================================================

class TestFetchLiveDisruptions:

    def _run(self, region_id: str,
             weather_alerts=None, disasters=None, corridor_statuses=None):
        """Run _fetch_live_disruptions with mocked B2 modules."""
        fema_m, noaa_m, routes_m = _make_b2_mocks(
            weather_alerts=weather_alerts,
            disasters=disasters,
            corridor_statuses=corridor_statuses,
        )
        import backend.disruptions_api as shim
        from regions import get_region
        with patch.object(shim, "fema_mod",   fema_m), \
             patch.object(shim, "noaa_mod",   noaa_m), \
             patch.object(shim, "routes_mod", routes_m):
            return shim._fetch_live_disruptions(get_region(region_id))

    def test_terrebonne_sees_terrebonne_alert(self):
        result = self._run(
            "terrebonne",
            weather_alerts=[TERREBONNE_ALERT, LAFOURCHE_ALERT],
        )
        ids = [a["id"] for a in result["weather_alerts"]]
        assert "nws-terrebonne-001" in ids
        assert "nws-lafourche-001" not in ids, (
            "Lafourche alert should be filtered out for Terrebonne query"
        )

    def test_lafourche_sees_lafourche_alert(self):
        result = self._run(
            "lafourche",
            weather_alerts=[TERREBONNE_ALERT, LAFOURCHE_ALERT],
        )
        ids = [a["id"] for a in result["weather_alerts"]]
        assert "nws-lafourche-001" in ids
        assert "nws-terrebonne-001" not in ids

    def test_statewide_alert_appears_in_both_parishes(self):
        result_t = self._run("terrebonne", weather_alerts=[STATEWIDE_HEAT_ALERT])
        result_l = self._run("lafourche",  weather_alerts=[STATEWIDE_HEAT_ALERT])
        assert len(result_t["weather_alerts"]) == 1
        assert len(result_l["weather_alerts"]) == 1

    def test_disaster_filtered_by_county(self):
        result = self._run(
            "terrebonne",
            disasters=[TERREBONNE_DISASTER, CONCORDIA_DISASTER],
        )
        nums = [d["disaster_number"] for d in result["disasters"]]
        assert 4701 in nums      # Terrebonne disaster
        assert 4702 not in nums  # Concordia disaster — different parish

    def test_whole_state_la_skips_county_filter(self):
        """A whole-state "LA" query should return all alerts, not filter by county."""
        result = self._run(
            "LA",
            weather_alerts=[TERREBONNE_ALERT, LAFOURCHE_ALERT],
            disasters=[TERREBONNE_DISASTER, CONCORDIA_DISASTER],
        )
        alert_ids = [a["id"] for a in result["weather_alerts"]]
        disaster_nums = [d["disaster_number"] for d in result["disasters"]]
        assert "nws-terrebonne-001" in alert_ids
        assert "nws-lafourche-001" in alert_ids
        assert 4701 in disaster_nums
        assert 4702 in disaster_nums

    def test_overall_status_rolls_up_correctly(self):
        result = self._run(
            "terrebonne",
            weather_alerts=[TERREBONNE_ALERT],   # Severe → impaired
            disasters=[],
            corridor_statuses=[TERREBONNE_CORRIDOR],
        )
        assert result["overall_status"] == "impaired"

    def test_hurricane_disaster_makes_status_blocked(self):
        result = self._run(
            "terrebonne",
            weather_alerts=[],
            disasters=[TERREBONNE_DISASTER],  # Hurricane → blocked
        )
        assert result["overall_status"] == "blocked"

    def test_response_shape(self):
        result = self._run("terrebonne")
        for key in ("region_id", "display_name", "state_codes", "counties",
                    "overall_status", "weather_alerts", "disasters",
                    "route_statuses", "generated_at", "_mock"):
            assert key in result, f"Missing key: {key}"
        assert result["region_id"] == "terrebonne"
        assert result["_mock"] is False

    def test_no_alerts_returns_clear(self):
        result = self._run("iberia")
        assert result["overall_status"] == "clear"
        assert result["weather_alerts"] == []
        assert result["disasters"] == []

    def test_noaa_failure_degrades_gracefully(self):
        import backend.disruptions_api as shim
        from regions import get_region
        fema_m, noaa_m, routes_m = _make_b2_mocks()
        noaa_m.fetch_weather_alerts.side_effect = Exception("NOAA down")
        with patch.object(shim, "fema_mod",   fema_m), \
             patch.object(shim, "noaa_mod",   noaa_m), \
             patch.object(shim, "routes_mod", routes_m):
            result = shim._fetch_live_disruptions(get_region("terrebonne"))
        # Should not raise; weather_alerts empty, overall_status reflects remaining
        assert "weather_alerts" in result
        assert result["weather_alerts"] == []

    def test_fema_failure_degrades_gracefully(self):
        import backend.disruptions_api as shim
        from regions import get_region
        fema_m, noaa_m, routes_m = _make_b2_mocks()
        fema_m.fetch_fema_disasters.side_effect = Exception("FEMA down")
        with patch.object(shim, "fema_mod",   fema_m), \
             patch.object(shim, "noaa_mod",   noaa_m), \
             patch.object(shim, "routes_mod", routes_m):
            result = shim._fetch_live_disruptions(get_region("lafourche"))
        assert result["disasters"] == []


# ===========================================================================
# 4. HTTP layer via FastAPI TestClient
# ===========================================================================

@pytest.fixture(scope="module")
def client():
    """Minimal FastAPI app with only the disruptions router mounted."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import backend.disruptions_api as shim

    # Force B2 available so the live path is exercised (we'll mock inside tests)
    original = shim._B2_AVAILABLE
    shim._B2_AVAILABLE = True

    mini_app = FastAPI()
    mini_app.include_router(shim.router)
    c = TestClient(mini_app, raise_server_exceptions=False)

    yield c

    shim._B2_AVAILABLE = original


class TestHTTPLayer:

    def test_known_region_returns_200(self, client):
        import backend.disruptions_api as shim
        fema_m, noaa_m, routes_m = _make_b2_mocks()
        with patch.object(shim, "fema_mod",   fema_m), \
             patch.object(shim, "noaa_mod",   noaa_m), \
             patch.object(shim, "routes_mod", routes_m):
            resp = client.get("/disruptions/terrebonne")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region_id"] == "terrebonne"

    def test_unknown_region_returns_404(self, client):
        resp = client.get("/disruptions/atlantis")
        assert resp.status_code == 404
        body = resp.json()
        assert "atlantis" in body["detail"]["error"].lower()
        assert "hint" in body["detail"]

    def test_state_code_returns_200(self, client):
        import backend.disruptions_api as shim
        fema_m, noaa_m, routes_m = _make_b2_mocks()
        with patch.object(shim, "fema_mod",   fema_m), \
             patch.object(shim, "noaa_mod",   noaa_m), \
             patch.object(shim, "routes_mod", routes_m):
            resp = client.get("/disruptions/TX")
        assert resp.status_code == 200
        body = resp.json()
        assert "TX" in body["state_codes"]

    def test_lowercase_state_code_returns_200(self, client):
        import backend.disruptions_api as shim
        fema_m, noaa_m, routes_m = _make_b2_mocks()
        with patch.object(shim, "fema_mod",   fema_m), \
             patch.object(shim, "noaa_mod",   noaa_m), \
             patch.object(shim, "routes_mod", routes_m):
            resp = client.get("/disruptions/tx")
        assert resp.status_code == 200

    def test_mock_fallback_when_b2_unavailable(self, client):
        import backend.disruptions_api as shim
        original = shim._B2_AVAILABLE
        shim._B2_AVAILABLE = False
        try:
            resp = client.get("/disruptions/terrebonne")
            assert resp.status_code == 200
            body = resp.json()
            assert body["_mock"] is True
            assert body["overall_status"] == "clear"
        finally:
            shim._B2_AVAILABLE = original

    def test_404_body_includes_hint(self, client):
        resp = client.get("/disruptions/fakeplace")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "hint" in detail
        # Hint should mention how to find valid IDs
        assert "supply_corridors" in detail["hint"] or "state code" in detail["hint"]

    def test_terrebonne_and_lafourche_differ(self, client):
        """End-to-end: two parish queries with overlapping state alerts
        should return different filtered results."""
        import backend.disruptions_api as shim
        fema_m, noaa_m, routes_m = _make_b2_mocks(
            weather_alerts=[TERREBONNE_ALERT, LAFOURCHE_ALERT],
        )
        with patch.object(shim, "fema_mod",   fema_m), \
             patch.object(shim, "noaa_mod",   noaa_m), \
             patch.object(shim, "routes_mod", routes_m):
            r_t = client.get("/disruptions/terrebonne").json()
            r_l = client.get("/disruptions/lafourche").json()

        t_ids = {a["id"] for a in r_t["weather_alerts"]}
        l_ids = {a["id"] for a in r_l["weather_alerts"]}
        assert t_ids != l_ids, "Terrebonne and Lafourche must return different alert sets"
        assert "nws-terrebonne-001" in t_ids
        assert "nws-lafourche-001" in l_ids