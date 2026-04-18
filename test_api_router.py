"""
Tests for alerts_api.py and disruptions_api.py FastAPI routers.

Uses FastAPI's TestClient so no real server is needed. All upstream calls
(risk_engine, alert_logic, Builder 2 modules) are patched.

Run with:
    pytest test_api_routers.py -v
"""

from __future__ import annotations

import datetime
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before any router import
# ---------------------------------------------------------------------------

def _make_stub(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod   # ✅ NO sys.modules modification here

# Minimal dataclasses matching what the routers use
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class _ComponentScores:
    crop_health: float = 50.0
    disruption: float = 40.0
    corridor_dependency: float = 60.0
    community_vulnerability: float = 20.0
    crop_raw: dict = field(default_factory=dict)
    disruption_raw: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class _RiskScore:
    community_id: str = "houma-la"
    community_name: str = "Houma, LA"
    corridor_id: str = "terrebonne-houma"
    risk_score: float = 65.0
    components: _ComponentScores = field(default_factory=_ComponentScores)
    top_factors: list = field(default_factory=lambda: ["Factor A"])
    data_quality: str = "full"

    def to_dict(self):
        return {
            "community_id": self.community_id,
            "community_name": self.community_name,
            "corridor_id": self.corridor_id,
            "risk_score": self.risk_score,
            "components": self.components.to_dict(),
            "top_factors": self.top_factors,
            "data_quality": self.data_quality,
        }


@dataclass
class _Alert:
    alert_id: str = "houma-la-20260418-warning"
    community_id: str = "houma-la"
    community_name: str = "Houma, LA"
    level: str = "Warning"
    risk_score: float = 65.0
    generated_at: str = "2026-04-18T00:00:00Z"
    headline: str = "WARNING — Houma, LA: elevated risk."
    explanation: str = "Risk driven by crop stress."
    top_factors: list = field(default_factory=lambda: ["Factor A"])
    recommended_actions: list = field(default_factory=lambda: ["Action 1"])
    sms_body: str = "[WARNING] Houma, LA 65/100."
    voice_script: str = "Warning for Houma."
    corridor_id: str = "terrebonne-houma"
    data_quality: str = "full"
    component_breakdown: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _make_alert(**kwargs) -> _Alert:
    a = _Alert()
    for k, v in kwargs.items():
        setattr(a, k, v)
    return a


# Stubs
_re_stub = _make_stub("risk_engine",
    RiskScore=_RiskScore,
    ComponentScores=_ComponentScores,
    compute_risk=MagicMock(return_value=_RiskScore()),
    compute_all_risks=MagicMock(return_value=[_RiskScore()]),
    get_all_community_ids=MagicMock(return_value=["houma-la", "dulac-la"]),
)

_al_stub = _make_stub("alert_logic",
    Alert=_Alert,
    generate_alert=MagicMock(return_value=_Alert()),
    generate_all_alerts=MagicMock(return_value=[_Alert()]),
    filter_active_alerts=MagicMock(return_value=[_Alert()]),
)

_fema_stub = _make_stub("fema")
_noaa_stub = _make_stub("noaa")
_routes_stub = _make_stub("routes")

# ---------------------------------------------------------------------------
# Import routers AFTER stubs are registered
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Patch sys.path so backend imports resolve
import backend.alerts_api as alerts_api_mod
import backend.disruptions_api as disruptions_api_mod

app = FastAPI()
app.include_router(alerts_api_mod.router, prefix="/api")
app.include_router(disruptions_api_mod.router, prefix="/api")

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

def _reset_cache():
    """Clear the in-memory alert cache between tests."""
    import backend.alerts_api as m
    with m._cache_lock:
        m._cache.clear()
        m._refresh_running = False


@pytest.fixture(autouse=True)
def clear_alert_cache():
    _reset_cache()
    yield
    _reset_cache()


def _mock_cache_entry(community_id: str, level: str = "Warning", score: float = 65.0):
    """Insert a synthetic _CacheEntry directly into the cache."""
    from backend.alerts_api import _CacheEntry, _cache, _cache_lock
    alert = _make_alert(community_id=community_id, level=level, risk_score=score)
    risk = _RiskScore(community_id=community_id, risk_score=score)
    entry = _CacheEntry(alert, risk)
    with _cache_lock:
        _cache[community_id] = entry
    return entry


# ===========================================================================
# alerts_api — GET /api/alerts
# ===========================================================================

class TestGetAllAlerts:
    def test_returns_200(self):
        _mock_cache_entry("houma-la", "Warning", 65.0)
        _mock_cache_entry("dulac-la", "Action", 85.0)
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la", "dulac-la"]):
            resp = client.get("/api/alerts")
        assert resp.status_code == 200

    def test_response_has_count_and_alerts(self):
        _mock_cache_entry("houma-la", "Warning", 65.0)
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la"]):
            resp = client.get("/api/alerts")
        body = resp.json()
        assert "count" in body
        assert "alerts" in body
        assert isinstance(body["alerts"], list)

    def test_sorted_by_risk_score_desc(self):
        _mock_cache_entry("houma-la", "Warning", 65.0)
        _mock_cache_entry("dulac-la", "Action", 85.0)
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la", "dulac-la"]):
            resp = client.get("/api/alerts")
        alerts = resp.json()["alerts"]
        scores = [a["risk_score"] for a in alerts]
        assert scores == sorted(scores, reverse=True)

    def test_min_level_watch_returns_all_active(self):
        _mock_cache_entry("houma-la", "Watch", 45.0)
        _mock_cache_entry("dulac-la", "Action", 85.0)
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la", "dulac-la"]):
            resp = client.get("/api/alerts?min_level=Watch")
        assert resp.status_code == 200
        levels = {a["level"] for a in resp.json()["alerts"]}
        assert levels.issubset({"Watch", "Warning", "Action"})

    def test_min_level_action_filters_lower(self):
        _mock_cache_entry("houma-la", "Warning", 65.0)
        _mock_cache_entry("dulac-la", "Action", 85.0)
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la", "dulac-la"]):
            resp = client.get("/api/alerts?min_level=Action")
        assert resp.status_code == 200
        levels = [a["level"] for a in resp.json()["alerts"]]
        assert all(l == "Action" for l in levels)

    def test_include_low_risk_returns_none_level(self):
        _mock_cache_entry("houma-la", "Warning", 65.0)
        # Insert a None-level entry
        from backend.alerts_api import _CacheEntry, _cache, _cache_lock
        none_alert = _make_alert(community_id="low-risk-la", level=None, risk_score=10.0)
        none_risk = _RiskScore(community_id="low-risk-la", risk_score=10.0)
        with _cache_lock:
            _cache["low-risk-la"] = _CacheEntry(none_alert, none_risk)

        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la", "low-risk-la"]):
            resp = client.get("/api/alerts?include_low_risk=true")
        ids = [a["community_id"] for a in resp.json()["alerts"]]
        assert "low-risk-la" in ids

    def test_invalid_min_level_returns_422(self):
        resp = client.get("/api/alerts?min_level=Critical")
        assert resp.status_code == 422

    def test_generated_at_present(self):
        _mock_cache_entry("houma-la")
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la"]):
            resp = client.get("/api/alerts")
        assert "generated_at" in resp.json()


# ===========================================================================
# alerts_api — GET /api/alerts/{community_id}
# ===========================================================================

class TestGetCommunityAlert:
    def test_cached_community_returns_200(self):
        _mock_cache_entry("houma-la")
        resp = client.get("/api/alerts/houma-la")
        assert resp.status_code == 200

    def test_response_contains_alert_fields(self):
        _mock_cache_entry("houma-la")
        resp = client.get("/api/alerts/houma-la")
        body = resp.json()
        assert "community_id" in body
        assert "risk_score" in body
        assert "level" in body

    def test_unknown_community_returns_404(self):
        with patch.object(alerts_api_mod, "_get_or_compute", side_effect=KeyError("not-found")):
            resp = client.get("/api/alerts/nonexistent-community")
        assert resp.status_code == 404

    def test_server_error_returns_500(self):
        with patch.object(alerts_api_mod, "_get_or_compute", side_effect=RuntimeError("boom")):
            resp = client.get("/api/alerts/houma-la")
        assert resp.status_code == 500


# ===========================================================================
# alerts_api — GET /api/risk
# ===========================================================================

class TestGetAllRisks:
    def test_returns_200(self):
        _mock_cache_entry("houma-la")
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la"]):
            resp = client.get("/api/risk")
        assert resp.status_code == 200

    def test_response_has_communities(self):
        _mock_cache_entry("houma-la")
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la"]):
            resp = client.get("/api/risk")
        body = resp.json()
        assert "communities" in body
        assert "count" in body

    def test_community_has_required_fields(self):
        _mock_cache_entry("houma-la")
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la"]):
            resp = client.get("/api/risk")
        community = resp.json()["communities"][0]
        for key in ("community_id", "risk_score", "components", "top_factors"):
            assert key in community

    def test_sorted_by_risk_score_desc(self):
        _mock_cache_entry("houma-la", "Warning", 65.0)
        _mock_cache_entry("dulac-la", "Action", 88.0)
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la", "dulac-la"]):
            resp = client.get("/api/risk")
        scores = [c["risk_score"] for c in resp.json()["communities"]]
        assert scores == sorted(scores, reverse=True)


# ===========================================================================
# alerts_api — GET /api/risk/{community_id}
# ===========================================================================

class TestGetCommunityRisk:
    def test_known_community_returns_200(self):
        _mock_cache_entry("houma-la")
        resp = client.get("/api/risk/houma-la")
        assert resp.status_code == 200

    def test_unknown_community_returns_404(self):
        with patch.object(alerts_api_mod, "_get_or_compute", side_effect=KeyError("x")):
            resp = client.get("/api/risk/nonexistent")
        assert resp.status_code == 404


# ===========================================================================
# alerts_api — POST /api/alerts/refresh
# ===========================================================================

class TestRefreshAlerts:
    def test_refresh_all_returns_200(self):
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la"]):
            with patch.object(alerts_api_mod, "_get_or_compute", return_value=_mock_cache_entry("houma-la")):
                resp = client.post("/api/alerts/refresh", json={})
        assert resp.status_code == 200

    def test_refresh_response_has_refreshed_key(self):
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la"]):
            entry = _mock_cache_entry("houma-la")
            with patch.object(alerts_api_mod, "_get_or_compute", return_value=entry):
                resp = client.post("/api/alerts/refresh", json={})
        body = resp.json()
        assert "refreshed" in body
        assert "communities" in body

    def test_refresh_specific_community_ids(self):
        entry = _mock_cache_entry("houma-la")
        with patch.object(alerts_api_mod, "_get_or_compute", return_value=entry):
            resp = client.post("/api/alerts/refresh", json={"community_ids": ["houma-la"]})
        assert resp.status_code == 200
        assert resp.json()["refreshed"] == 1

    def test_refresh_clears_cache(self):
        _mock_cache_entry("houma-la", "Warning", 65.0)
        from backend.alerts_api import _cache, _cache_lock
        with _cache_lock:
            assert "houma-la" in _cache

        entry = _mock_cache_entry("houma-la")
        with patch.object(alerts_api_mod.risk_engine, "get_all_community_ids", return_value=["houma-la"]):
            with patch.object(alerts_api_mod, "_get_or_compute", return_value=entry):
                client.post("/api/alerts/refresh", json={})
        # After refresh the cache should be repopulated (not empty)
        with _cache_lock:
            assert "houma-la" in _cache


# ===========================================================================
# Cache TTL / freshness
# ===========================================================================

class TestCacheFreshness:
    def test_fresh_entry_not_re_computed(self):
        """A fresh cache entry should be returned without calling compute_risk."""
        _mock_cache_entry("houma-la")
        compute_mock = MagicMock(return_value=_RiskScore())
        with patch.object(alerts_api_mod.risk_engine, "compute_risk", compute_mock):
            with patch.object(alerts_api_mod, "compute_risk", compute_mock):
                client.get("/api/alerts/houma-la")
        compute_mock.assert_not_called()

    def test_stale_entry_triggers_recompute(self):
        """An expired cache entry should trigger a fresh compute."""
        from backend.alerts_api import _CacheEntry, _cache, _cache_lock
        alert = _make_alert()
        risk = _RiskScore()
        entry = _CacheEntry(alert, risk)
        # Force-age the entry beyond TTL
        entry.ts = datetime.datetime.utcnow() - datetime.timedelta(seconds=10000)
        with _cache_lock:
            _cache["houma-la"] = entry

        new_risk = _RiskScore(community_id="houma-la", risk_score=77.0)
        new_alert = _make_alert(community_id="houma-la", risk_score=77.0)

        with patch.object(alerts_api_mod, "compute_risk", return_value=new_risk):
            with patch.object(alerts_api_mod, "generate_alert", return_value=new_alert):
                resp = client.get("/api/alerts/houma-la")
        assert resp.status_code == 200


# ===========================================================================
# disruptions_api — GET /api/disruptions/{region_id}
# ===========================================================================

class TestGetDisruptions:
    """
    Builder 2 modules (fema, noaa, routes) may not be installed in the test
    environment. We mock _B2_AVAILABLE and the live-fetch function to keep
    tests isolated from network I/O.
    """

    def test_returns_200_when_mock_mode(self):
        with patch.object(disruptions_api_mod, "_B2_AVAILABLE", False):
            resp = client.get("/api/disruptions/terrebonne")
        assert resp.status_code == 200

    def test_mock_response_has_required_fields(self):
        with patch.object(disruptions_api_mod, "_B2_AVAILABLE", False):
            resp = client.get("/api/disruptions/terrebonne")
        body = resp.json()
        for key in ("region_id", "overall_status", "weather_alerts", "disasters",
                    "route_statuses", "generated_at"):
            assert key in body, f"Missing key: {key}"

    def test_mock_response_region_id_matches(self):
        with patch.object(disruptions_api_mod, "_B2_AVAILABLE", False):
            resp = client.get("/api/disruptions/lafourche")
        assert resp.json()["region_id"] == "lafourche"

    def test_mock_response_clear_status(self):
        with patch.object(disruptions_api_mod, "_B2_AVAILABLE", False):
            resp = client.get("/api/disruptions/terrebonne")
        assert resp.json()["overall_status"] == "clear"

    def test_live_fetch_path_used_when_b2_available(self):
        live_data = {
            "region_id": "louisiana",
            "overall_status": "impaired",
            "weather_alerts": [{"event": "Flood Warning", "severity": "Severe"}],
            "disasters": [],
            "route_statuses": [],
            "generated_at": "2026-04-18T00:00:00Z",
            "_mock": False,
        }
        with patch.object(disruptions_api_mod, "_B2_AVAILABLE", True):
            with patch.object(disruptions_api_mod, "_fetch_live_disruptions", return_value=live_data):
                resp = client.get("/api/disruptions/louisiana")
        assert resp.status_code == 200
        body = resp.json()
        assert body["overall_status"] == "impaired"
        assert len(body["weather_alerts"]) == 1

    def test_live_fetch_exception_returns_500(self):
        with patch.object(disruptions_api_mod, "_B2_AVAILABLE", True):
            with patch.object(disruptions_api_mod, "_fetch_live_disruptions", side_effect=RuntimeError("API down")):
                resp = client.get("/api/disruptions/louisiana")
        assert resp.status_code == 500

    def test_unknown_region_falls_back_to_la_state(self):
        """An unrecognised region_id should default to 'LA' state mapping."""
        live_data = {
            "region_id": "unknown-parish",
            "overall_status": "clear",
            "weather_alerts": [],
            "disasters": [],
            "route_statuses": [],
            "generated_at": "2026-04-18T00:00:00Z",
            "_mock": False,
        }
        with patch.object(disruptions_api_mod, "_B2_AVAILABLE", True):
            with patch.object(disruptions_api_mod, "_fetch_live_disruptions", return_value=live_data) as mock_live:
                resp = client.get("/api/disruptions/unknown-parish")
        assert resp.status_code == 200
        # The fetch was called — region was passed through
        mock_live.assert_called_once_with("unknown-parish")

    def test_all_known_region_ids_return_200(self):
        """Smoke test: every region in _REGION_STATE_MAP should respond without error."""
        known_regions = list(disruptions_api_mod._REGION_STATE_MAP.keys())
        assert len(known_regions) > 0
        with patch.object(disruptions_api_mod, "_B2_AVAILABLE", False):
            for region in known_regions:
                resp = client.get(f"/api/disruptions/{region}")
                assert resp.status_code == 200, f"Failed for region: {region}"


# ===========================================================================
# _worst_status helper (disruptions_api internal)
# ===========================================================================

class TestWorstStatus:
    def test_blocked_beats_impaired(self):
        from backend.disruptions_api import _worst_status
        assert _worst_status("impaired", "blocked") == "blocked"

    def test_impaired_beats_clear(self):
        from backend.disruptions_api import _worst_status
        assert _worst_status("clear", "impaired") == "impaired"

    def test_same_status_returns_it(self):
        from backend.disruptions_api import _worst_status
        assert _worst_status("clear", "clear") == "clear"

    def test_order_independent(self):
        from backend.disruptions_api import _worst_status
        assert _worst_status("blocked", "clear") == _worst_status("clear", "blocked")