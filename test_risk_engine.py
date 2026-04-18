"""
Tests for risk_engine.py

Covers:
  - _interp: linear interpolation between NDVI breakpoints
  - _crop_health_score: NDVI deviation → component score, drought bonus
  - _disruption_score: overall_status → component score, weather/FEMA/route signals
  - _corridor_dependency_score: dependency_weight → component score
  - _vulnerability_score: food_insecurity_rate → component score
  - compute_risk: integration with mocked Builder 1 / Builder 2 HTTP calls
  - get_all_community_ids: reads supply_corridors.json (mocked)

All external HTTP calls are patched via unittest.mock so tests run offline.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# We need risk_engine importable. It imports `requests` (fine) and reads
# supply_corridors.json from Path(__file__).parent. We'll patch the file
# path and json loading where needed.
# ---------------------------------------------------------------------------

import risk_engine
from risk_engine import (
    _interp,
    _crop_health_score,
    _disruption_score,
    _corridor_dependency_score,
    _vulnerability_score,
    _CROP_BREAKPOINTS,
    _DISRUPTION_SEVERITY_SCORES,
    W_CROP,
    W_DISRUPTION,
    W_CORRIDOR,
    W_VULNERABILITY,
    compute_risk,
    get_all_community_ids,
    RiskScore,
)

# ---------------------------------------------------------------------------
# Shared fixture data mirroring supply_corridors.json structure
# ---------------------------------------------------------------------------

MOCK_CORRIDORS = {
    "corridors": [
        {
            "id": "terrebonne-houma",
            "name": "Terrebonne Basin → Houma Metro",
            "source_region": "terrebonne",
            "source_region_id": "louisiana",
            "source_bbox": [-90.82, 29.10, -90.30, 29.65],
            "crop_types": ["crawfish", "rice", "sugarcane"],
            "destination_communities": [
                {
                    "community_id": "houma-la",
                    "name": "Houma, LA",
                    "population": 33000,
                    "food_insecurity_rate": 0.18,
                    "dependency_weight": 0.85,
                },
                {
                    "community_id": "dulac-la",
                    "name": "Dulac, LA",
                    "population": 1700,
                    "food_insecurity_rate": 0.34,
                    "dependency_weight": 0.95,
                },
            ],
            "primary_route": "LA-24",
            "backup_route": "US-90",
            "waypoints": [
                {"state": "LA", "county": "Terrebonne"},
                {"state": "LA", "county": "Lafourche"},
            ],
        }
    ],
    "community_vulnerability_index": {
        "houma-la": 0.18,
        "dulac-la": 0.34,
    },
}

MOCK_CROP_PAYLOAD_NORMAL = {
    "summary": {
        "alert": "normal",
        "ndvi_deviation_pct": -5.0,
        "drought_status": "no_drought",
    }
}

MOCK_CROP_PAYLOAD_WARNING = {
    "summary": {
        "alert": "warning",
        "ndvi_deviation_pct": -18.0,
        "drought_status": "moderate_drought",
    }
}

MOCK_CROP_PAYLOAD_CRITICAL = {
    "summary": {
        "alert": "critical",
        "ndvi_deviation_pct": -35.0,
        "drought_status": "severe_drought",
    }
}

MOCK_CROP_PAYLOAD_NO_DEVIATION = {
    "summary": {
        "alert": "warning",
        "ndvi_deviation_pct": None,
        "drought_status": None,
    }
}

MOCK_DISRUPTION_CLEAR = {
    "overall_status": "clear",
    "weather_alerts": [],
    "disasters": [],
    "route_statuses": [],
}

MOCK_DISRUPTION_IMPAIRED = {
    "overall_status": "impaired",
    "weather_alerts": [
        {
            "alert_type": "flood",
            "event": "Flood Warning",
            "severity": "Severe",
            "affected_area": "Terrebonne, LA",
        }
    ],
    "disasters": [],
    "route_statuses": [
        {"corridor_id": "terrebonne-houma", "status": "impaired", "reason": "Flooding"},
    ],
}

MOCK_DISRUPTION_BLOCKED = {
    "overall_status": "blocked",
    "weather_alerts": [
        {
            "alert_type": "flood",
            "event": "Flash Flood Warning",
            "severity": "Extreme",
            "affected_area": "Terrebonne, LA",
        }
    ],
    "disasters": [
        {"type": "Hurricane", "state": "LA", "declaration_title": "Hurricane Test"},
        {"type": "Flood", "state": "LA", "declaration_title": "Flood Test"},
    ],
    "route_statuses": [
        {"corridor_id": "terrebonne-houma", "status": "blocked", "reason": "Hurricane"},
    ],
}

MOCK_DISRUPTION_MOCK = {
    "_mock": True,
    "overall_status": "unknown",
    "weather_alerts": [],
    "disasters": [],
    "route_statuses": [],
}


# ---------------------------------------------------------------------------
# Helper to reset module-level cache between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_corridors_cache():
    """Clear the module-level _corridors_data cache before each test."""
    original = risk_engine._corridors_data
    risk_engine._corridors_data = None
    yield
    risk_engine._corridors_data = original


# ---------------------------------------------------------------------------
# _interp
# ---------------------------------------------------------------------------

class TestInterp:
    def test_above_first_breakpoint_returns_first_y(self):
        # deviation ≥ 0 → score 0
        assert _interp(5.0, _CROP_BREAKPOINTS) == 0.0

    def test_at_first_breakpoint(self):
        assert _interp(0.0, _CROP_BREAKPOINTS) == 0.0

    def test_exact_breakpoint_match(self):
        # -10 → 20
        assert _interp(-10.0, _CROP_BREAKPOINTS) == pytest.approx(20.0, abs=0.1)

    def test_midpoint_interpolation(self):
        # midpoint between (-10, 20) and (-15, 40) → should be ~30
        result = _interp(-12.5, _CROP_BREAKPOINTS)
        assert 20.0 < result < 40.0

    def test_at_last_breakpoint(self):
        assert _interp(-40.0, _CROP_BREAKPOINTS) == 100.0

    def test_below_last_breakpoint_clamps(self):
        # Anything more negative than -40 → 100
        assert _interp(-99.0, _CROP_BREAKPOINTS) == 100.0


# ---------------------------------------------------------------------------
# _crop_health_score
# ---------------------------------------------------------------------------

class TestCropHealthScore:
    def test_normal_low_deviation_low_score(self):
        score, factors = _crop_health_score(MOCK_CROP_PAYLOAD_NORMAL)
        assert score < 20.0  # -5% → between 0 and 20

    def test_warning_deviation_mid_score(self):
        score, factors = _crop_health_score(MOCK_CROP_PAYLOAD_WARNING)
        # -18% deviation → between 40 and 60, plus moderate_drought bonus (9)
        assert 40.0 <= score <= 70.0

    def test_critical_deviation_high_score(self):
        score, factors = _crop_health_score(MOCK_CROP_PAYLOAD_CRITICAL)
        # -35% + severe_drought (14) bonus
        assert score >= 80.0

    def test_drought_bonus_added(self):
        score_no_drought, _ = _crop_health_score({
            "summary": {"alert": "normal", "ndvi_deviation_pct": -18.0, "drought_status": "no_drought"}
        })
        score_drought, _ = _crop_health_score({
            "summary": {"alert": "normal", "ndvi_deviation_pct": -18.0, "drought_status": "severe_drought"}
        })
        assert score_drought > score_no_drought

    def test_drought_capped_at_100(self):
        score, _ = _crop_health_score({
            "summary": {
                "alert": "critical",
                "ndvi_deviation_pct": -50.0,
                "drought_status": "exceptional_drought",
            }
        })
        assert score <= 100.0

    def test_no_deviation_uses_alert_fallback(self):
        score, factors = _crop_health_score(MOCK_CROP_PAYLOAD_NO_DEVIATION)
        # "warning" fallback → 40.0
        assert score == pytest.approx(40.0, abs=0.1)
        assert any("unavailable" in f.lower() for f in factors)

    def test_data_unavailable_alert_fallback(self):
        payload = {"summary": {"alert": "data_unavailable", "ndvi_deviation_pct": None, "drought_status": None}}
        score, factors = _crop_health_score(payload)
        assert score == pytest.approx(30.0, abs=0.1)

    def test_factors_non_empty_for_stressed_crop(self):
        _, factors = _crop_health_score(MOCK_CROP_PAYLOAD_CRITICAL)
        assert len(factors) >= 1

    def test_mock_payload_handled(self):
        payload = {"_mock": True, "summary": {"alert": "data_unavailable", "ndvi_deviation_pct": None, "drought_status": None}}
        score, _ = _crop_health_score(payload)
        assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# _disruption_score
# ---------------------------------------------------------------------------

class TestDisruptionScore:
    def test_clear_status_low_score(self):
        score, factors = _disruption_score(MOCK_DISRUPTION_CLEAR)
        assert score == pytest.approx(_DISRUPTION_SEVERITY_SCORES["clear"], abs=0.1)
        assert factors == []

    def test_impaired_status_mid_score(self):
        score, _ = _disruption_score(MOCK_DISRUPTION_IMPAIRED)
        assert score >= _DISRUPTION_SEVERITY_SCORES["impaired"]

    def test_blocked_status_high_score(self):
        score, _ = _disruption_score(MOCK_DISRUPTION_BLOCKED)
        assert score >= 80.0

    def test_weather_alert_raises_score(self):
        score_no_alert, _ = _disruption_score(MOCK_DISRUPTION_CLEAR)
        impaired_payload = {
            "overall_status": "clear",
            "weather_alerts": [{"alert_type": "flood", "event": "Flood Warning", "severity": "Extreme", "affected_area": "X"}],
            "disasters": [],
            "route_statuses": [],
        }
        score_with_alert, _ = _disruption_score(impaired_payload)
        assert score_with_alert > score_no_alert

    def test_fema_disaster_adds_penalty(self):
        score_no_disaster, _ = _disruption_score(MOCK_DISRUPTION_CLEAR)
        payload_with_disaster = {
            "overall_status": "clear",
            "weather_alerts": [],
            "disasters": [{"type": "Flood", "state": "LA", "declaration_title": "Flood"}],
            "route_statuses": [],
        }
        score_with_disaster, _ = _disruption_score(payload_with_disaster)
        assert score_with_disaster > score_no_disaster

    def test_blocked_route_forces_min_80(self):
        payload = {
            "overall_status": "clear",
            "weather_alerts": [],
            "disasters": [],
            "route_statuses": [{"corridor_id": "X", "status": "blocked", "reason": "test"}],
        }
        score, _ = _disruption_score(payload)
        assert score >= 80.0

    def test_impaired_route_forces_min_50(self):
        payload = {
            "overall_status": "clear",
            "weather_alerts": [],
            "disasters": [],
            "route_statuses": [{"corridor_id": "X", "status": "impaired", "reason": "test"}],
        }
        score, _ = _disruption_score(payload)
        assert score >= 50.0

    def test_score_never_exceeds_100(self):
        score, _ = _disruption_score(MOCK_DISRUPTION_BLOCKED)
        assert score <= 100.0

    def test_unknown_status_uses_default(self):
        payload = {"overall_status": "unknown", "weather_alerts": [], "disasters": [], "route_statuses": []}
        score, _ = _disruption_score(payload)
        assert score == pytest.approx(30.0, abs=0.1)

    def test_multiple_disasters_cumulative_penalty(self):
        one_disaster = {
            "overall_status": "clear",
            "weather_alerts": [],
            "disasters": [{"type": "Flood", "state": "LA", "declaration_title": "A"}],
            "route_statuses": [],
        }
        two_disasters = {
            "overall_status": "clear",
            "weather_alerts": [],
            "disasters": [
                {"type": "Flood", "state": "LA", "declaration_title": "A"},
                {"type": "Fire", "state": "LA", "declaration_title": "B"},
            ],
            "route_statuses": [],
        }
        s1, _ = _disruption_score(one_disaster)
        s2, _ = _disruption_score(two_disasters)
        assert s2 >= s1


# ---------------------------------------------------------------------------
# _corridor_dependency_score
# ---------------------------------------------------------------------------

class TestCorridorDependencyScore:
    def test_high_dependency_high_score(self):
        community = {"name": "Dulac, LA", "dependency_weight": 0.95}
        score, factors = _corridor_dependency_score(community)
        assert score == pytest.approx(95.0, abs=0.1)
        assert len(factors) >= 1

    def test_low_dependency_low_score(self):
        community = {"name": "Test City", "dependency_weight": 0.20}
        score, factors = _corridor_dependency_score(community)
        assert score == pytest.approx(20.0, abs=0.1)
        assert factors == []

    def test_weight_at_85_threshold(self):
        community = {"name": "Test City", "dependency_weight": 0.85}
        score, factors = _corridor_dependency_score(community)
        assert score == pytest.approx(85.0, abs=0.1)
        assert any("critical" in f.lower() for f in factors)

    def test_weight_at_65_threshold(self):
        community = {"name": "Test City", "dependency_weight": 0.65}
        score, factors = _corridor_dependency_score(community)
        assert any("high" in f.lower() for f in factors)

    def test_score_proportional_to_weight(self):
        c1 = {"name": "X", "dependency_weight": 0.30}
        c2 = {"name": "Y", "dependency_weight": 0.70}
        s1, _ = _corridor_dependency_score(c1)
        s2, _ = _corridor_dependency_score(c2)
        assert s2 > s1

    def test_missing_weight_defaults(self):
        community = {"name": "No Weight City"}
        score, _ = _corridor_dependency_score(community)
        assert score == pytest.approx(50.0, abs=0.1)


# ---------------------------------------------------------------------------
# _vulnerability_score
# ---------------------------------------------------------------------------

class TestVulnerabilityScore:
    def test_high_insecurity_high_score(self):
        # lake-providence-la has 0.43 in mock corridors
        with patch.object(risk_engine, "_load_corridors", return_value=MOCK_CORRIDORS):
            with patch.object(risk_engine, "_corridors_data", MOCK_CORRIDORS):
                # dulac-la has 0.34
                score, factors = _vulnerability_score("dulac-la", {"name": "Dulac, LA"})
        assert score == pytest.approx(34.0, abs=0.1)

    def test_low_insecurity_low_score(self):
        with patch.object(risk_engine, "_load_corridors", return_value=MOCK_CORRIDORS):
            with patch.object(risk_engine, "_corridors_data", MOCK_CORRIDORS):
                score, factors = _vulnerability_score("houma-la", {"name": "Houma, LA"})
        assert score == pytest.approx(18.0, abs=0.1)

    def test_missing_community_defaults_to_20(self):
        with patch.object(risk_engine, "_load_corridors", return_value=MOCK_CORRIDORS):
            with patch.object(risk_engine, "_corridors_data", MOCK_CORRIDORS):
                score, _ = _vulnerability_score("unknown-community", {"name": "Unknown"})
        assert score == pytest.approx(20.0, abs=0.1)

    def test_very_high_insecurity_factor_label(self):
        custom = dict(MOCK_CORRIDORS)
        custom["community_vulnerability_index"] = {"high-risk": 0.40}
        with patch.object(risk_engine, "_load_corridors", return_value=custom):
            with patch.object(risk_engine, "_corridors_data", custom):
                _, factors = _vulnerability_score("high-risk", {"name": "High Risk City"})
        assert any("very high" in f.lower() for f in factors)


# ---------------------------------------------------------------------------
# get_all_community_ids
# ---------------------------------------------------------------------------

class TestGetAllCommunityIds:
    def test_returns_list_of_strings(self):
        with patch.object(risk_engine, "_load_corridors", return_value=MOCK_CORRIDORS):
            risk_engine._corridors_data = MOCK_CORRIDORS
            ids = get_all_community_ids()
        assert isinstance(ids, list)
        assert all(isinstance(i, str) for i in ids)

    def test_expected_ids_present(self):
        with patch.object(risk_engine, "_load_corridors", return_value=MOCK_CORRIDORS):
            risk_engine._corridors_data = MOCK_CORRIDORS
            ids = get_all_community_ids()
        assert "houma-la" in ids
        assert "dulac-la" in ids

    def test_count_matches_communities(self):
        with patch.object(risk_engine, "_load_corridors", return_value=MOCK_CORRIDORS):
            risk_engine._corridors_data = MOCK_CORRIDORS
            ids = get_all_community_ids()
        assert len(ids) == 2


# ---------------------------------------------------------------------------
# compute_risk — integration (HTTP mocked)
# ---------------------------------------------------------------------------

class TestComputeRisk:
    def _patch_and_compute(self, community_id, crop_payload, disruption_payload):
        with patch.object(risk_engine, "_load_corridors", return_value=MOCK_CORRIDORS):
            risk_engine._corridors_data = MOCK_CORRIDORS
            with patch.object(risk_engine, "_fetch_crop_health", return_value=crop_payload):
                with patch.object(risk_engine, "_fetch_disruptions", return_value=disruption_payload):
                    return compute_risk(community_id)

    def test_returns_risk_score_instance(self):
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_NORMAL, MOCK_DISRUPTION_CLEAR)
        assert isinstance(result, RiskScore)

    def test_community_fields_correct(self):
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_NORMAL, MOCK_DISRUPTION_CLEAR)
        assert result.community_id == "houma-la"
        assert result.community_name == "Houma, LA"
        assert result.corridor_id == "terrebonne-houma"

    def test_risk_score_in_valid_range(self):
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_CRITICAL, MOCK_DISRUPTION_BLOCKED)
        assert 0.0 <= result.risk_score <= 100.0

    def test_data_quality_full_when_no_mock(self):
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_NORMAL, MOCK_DISRUPTION_CLEAR)
        assert result.data_quality == "full"

    def test_data_quality_mock_when_either_mock(self):
        mock_crop = {**MOCK_CROP_PAYLOAD_NORMAL, "_mock": True}
        result = self._patch_and_compute("houma-la", mock_crop, MOCK_DISRUPTION_CLEAR)
        assert result.data_quality == "mock"

    def test_high_risk_inputs_produce_high_score(self):
        result = self._patch_and_compute("dulac-la", MOCK_CROP_PAYLOAD_CRITICAL, MOCK_DISRUPTION_BLOCKED)
        # dulac has 0.95 corridor dependency + critical crop + blocked disruption
        assert result.risk_score > 70.0

    def test_low_risk_inputs_produce_low_score(self):
        # Normal crop, clear disruption, low dependency community
        # houma-la has 0.85 dependency so let's use a custom low-dep community
        custom = dict(MOCK_CORRIDORS)
        custom["corridors"][0]["destination_communities"] = [
            {
                "community_id": "low-risk-la",
                "name": "Low Risk, LA",
                "population": 5000,
                "food_insecurity_rate": 0.10,
                "dependency_weight": 0.10,
            }
        ]
        custom["community_vulnerability_index"] = {"low-risk-la": 0.10}
        with patch.object(risk_engine, "_load_corridors", return_value=custom):
            risk_engine._corridors_data = custom
            with patch.object(risk_engine, "_fetch_crop_health", return_value=MOCK_CROP_PAYLOAD_NORMAL):
                with patch.object(risk_engine, "_fetch_disruptions", return_value=MOCK_DISRUPTION_CLEAR):
                    result = compute_risk("low-risk-la")
        # -5% NDVI is a low score; clear disruption; 10% dependency and vulnerability
        assert result.risk_score < 40.0

    def test_top_factors_non_empty_for_active_risk(self):
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_WARNING, MOCK_DISRUPTION_IMPAIRED)
        assert len(result.top_factors) >= 1

    def test_top_factors_max_three(self):
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_CRITICAL, MOCK_DISRUPTION_BLOCKED)
        assert len(result.top_factors) <= 3

    def test_unknown_community_raises_key_error(self):
        with patch.object(risk_engine, "_load_corridors", return_value=MOCK_CORRIDORS):
            risk_engine._corridors_data = MOCK_CORRIDORS
            with pytest.raises(KeyError, match="unknown-xyz"):
                compute_risk("unknown-xyz")

    def test_composite_formula_weights(self):
        """Verify the weighted sum formula is applied correctly."""
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_NORMAL, MOCK_DISRUPTION_CLEAR)
        c = result.components
        expected = (
            c.crop_health * W_CROP
            + c.disruption * W_DISRUPTION
            + c.corridor_dependency * W_CORRIDOR
            + c.community_vulnerability * W_VULNERABILITY
        )
        assert abs(result.risk_score - expected) < 0.1

    def test_components_stored_in_result(self):
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_NORMAL, MOCK_DISRUPTION_CLEAR)
        assert result.components is not None
        assert hasattr(result.components, "crop_health")
        assert hasattr(result.components, "disruption")

    def test_raw_payloads_stored_in_components(self):
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_NORMAL, MOCK_DISRUPTION_CLEAR)
        assert result.components.crop_raw is not None
        assert result.components.disruption_raw is not None

    def test_to_dict_serialisable(self):
        import json
        result = self._patch_and_compute("houma-la", MOCK_CROP_PAYLOAD_NORMAL, MOCK_DISRUPTION_CLEAR)
        d = result.to_dict()
        json.dumps(d)  # must not raise