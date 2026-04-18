"""
Tests for alert_logic.py

Covers:
  - _level_from_score: threshold boundaries
  - generate_alert: full Alert construction from RiskScore
  - generate_all_alerts: sorting and bulk generation
  - filter_active_alerts: None-level filtering
  - SMS body length constraint (≤160 chars)
  - Voice script presence and structure
  - component_breakdown arithmetic
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Minimal stubs so alert_logic can be imported without risk_engine on sys.path
# ---------------------------------------------------------------------------
import sys
import types

# Stub risk_engine module with the dataclasses alert_logic imports
_risk_engine_stub = types.ModuleType("risk_engine")

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class _ComponentScores:
    crop_health: float = 50.0
    disruption: float = 40.0
    corridor_dependency: float = 60.0
    community_vulnerability: float = 30.0
    crop_raw: dict = field(default_factory=dict)
    disruption_raw: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class _RiskScore:
    community_id: str = "houma-la"
    community_name: str = "Houma, LA"
    corridor_id: str = "terrebonne-houma"
    risk_score: float = 55.0
    components: _ComponentScores = field(default_factory=_ComponentScores)
    top_factors: list = field(default_factory=lambda: [
        "Crop health alert: warning",
        "Supply route status: impaired",
        "High corridor dependency: Houma, LA (85%)",
    ])
    data_quality: str = "full"

    def to_dict(self):
        return asdict(self)


_risk_engine_stub.RiskScore = _RiskScore
_risk_engine_stub.ComponentScores = _ComponentScores
sys.modules.setdefault("risk_engine", _risk_engine_stub)

import alert_logic  # noqa: E402 — imported after stub registration
from alert_logic import (
    Alert,
    generate_alert,
    generate_all_alerts,
    filter_active_alerts,
    THRESHOLD_WATCH,
    THRESHOLD_WARNING,
    THRESHOLD_ACTION,
    _level_from_score,
    _sms_body,
    _headline,
    _voice_script,
    _explanation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_risk(score: float, data_quality: str = "full", top_factors=None) -> _RiskScore:
    return _RiskScore(
        community_id="test-community",
        community_name="Test City, LA",
        corridor_id="test-corridor",
        risk_score=score,
        components=_ComponentScores(
            crop_health=score,
            disruption=score * 0.5,
            corridor_dependency=70.0,
            community_vulnerability=25.0,
        ),
        top_factors=top_factors or ["Factor A", "Factor B"],
        data_quality=data_quality,
    )


# ---------------------------------------------------------------------------
# _level_from_score
# ---------------------------------------------------------------------------

class TestLevelFromScore:
    def test_below_watch_returns_none(self):
        assert _level_from_score(0.0) is None
        assert _level_from_score(39.99) is None

    def test_exact_watch_boundary(self):
        assert _level_from_score(THRESHOLD_WATCH) == "Watch"

    def test_mid_watch(self):
        assert _level_from_score(50.0) == "Watch"

    def test_exact_warning_boundary(self):
        assert _level_from_score(THRESHOLD_WARNING) == "Warning"

    def test_mid_warning(self):
        assert _level_from_score(70.0) == "Warning"

    def test_exact_action_boundary(self):
        assert _level_from_score(THRESHOLD_ACTION) == "Action"

    def test_max_score_action(self):
        assert _level_from_score(100.0) == "Action"

    def test_just_below_warning_is_watch(self):
        assert _level_from_score(59.99) == "Watch"

    def test_just_below_action_is_warning(self):
        assert _level_from_score(79.99) == "Warning"


# ---------------------------------------------------------------------------
# generate_alert — structure
# ---------------------------------------------------------------------------

class TestGenerateAlertStructure:
    """Verify every field of the returned Alert is populated correctly."""

    def test_returns_alert_instance(self):
        risk = _make_risk(75.0)
        alert = generate_alert(risk)
        assert isinstance(alert, Alert)

    def test_community_fields_copied(self):
        risk = _make_risk(75.0)
        alert = generate_alert(risk)
        assert alert.community_id == risk.community_id
        assert alert.community_name == risk.community_name
        assert alert.corridor_id == risk.corridor_id

    def test_risk_score_preserved(self):
        risk = _make_risk(82.5)
        alert = generate_alert(risk)
        assert alert.risk_score == 82.5

    def test_data_quality_propagated(self):
        risk = _make_risk(55.0, data_quality="mock")
        alert = generate_alert(risk)
        assert alert.data_quality == "mock"

    def test_alert_id_contains_community_and_level(self):
        risk = _make_risk(85.0)
        alert = generate_alert(risk)
        assert risk.community_id in alert.alert_id
        assert "action" in alert.alert_id.lower()

    def test_generated_at_is_utc_iso(self):
        import datetime
        risk = _make_risk(60.0)
        alert = generate_alert(risk)
        # Should parse without error
        dt = datetime.datetime.fromisoformat(alert.generated_at.rstrip("Z"))
        assert dt.year >= 2024

    def test_top_factors_copied(self):
        factors = ["Alpha factor", "Beta factor"]
        risk = _make_risk(75.0, top_factors=factors)
        alert = generate_alert(risk)
        assert alert.top_factors == factors

    def test_to_dict_is_serialisable(self):
        import json
        risk = _make_risk(65.0)
        alert = generate_alert(risk)
        d = alert.to_dict()
        # Must not raise
        json.dumps(d)


# ---------------------------------------------------------------------------
# generate_alert — alert levels and actions
# ---------------------------------------------------------------------------

class TestGenerateAlertLevels:
    def test_low_score_gives_none_level(self):
        alert = generate_alert(_make_risk(20.0))
        assert alert.level is None
        assert alert.recommended_actions == []

    def test_watch_level_and_action_count(self):
        alert = generate_alert(_make_risk(50.0))
        assert alert.level == "Watch"
        assert len(alert.recommended_actions) == 3  # _ACTION_COUNT_BY_LEVEL["Watch"]

    def test_warning_level_and_action_count(self):
        alert = generate_alert(_make_risk(70.0))
        assert alert.level == "Warning"
        assert len(alert.recommended_actions) == 4

    def test_action_level_and_action_count(self):
        alert = generate_alert(_make_risk(90.0))
        assert alert.level == "Action"
        assert len(alert.recommended_actions) == 5

    def test_actions_are_non_empty_strings(self):
        alert = generate_alert(_make_risk(80.0))
        for action in alert.recommended_actions:
            assert isinstance(action, str) and len(action) > 0


# ---------------------------------------------------------------------------
# SMS body
# ---------------------------------------------------------------------------

class TestSmsBody:
    def test_sms_max_160_chars_watch(self):
        alert = generate_alert(_make_risk(50.0))
        assert len(alert.sms_body) <= 160

    def test_sms_max_160_chars_warning(self):
        alert = generate_alert(_make_risk(70.0))
        assert len(alert.sms_body) <= 160

    def test_sms_max_160_chars_action(self):
        alert = generate_alert(_make_risk(90.0))
        assert len(alert.sms_body) <= 160

    def test_sms_none_level_mentions_low(self):
        alert = generate_alert(_make_risk(10.0))
        body = alert.sms_body.lower()
        assert "low" in body or "rootbridge" in body

    def test_sms_includes_level_tag_for_active_alert(self):
        alert = generate_alert(_make_risk(80.0))
        assert "[ACTION]" in alert.sms_body or "ACTION" in alert.sms_body.upper()

    def test_sms_contains_community_name(self):
        risk = _make_risk(75.0)
        alert = generate_alert(risk)
        assert risk.community_name in alert.sms_body or "Test City" in alert.sms_body


# ---------------------------------------------------------------------------
# Headline
# ---------------------------------------------------------------------------

class TestHeadline:
    def test_none_level_headline_mentions_low(self):
        alert = generate_alert(_make_risk(10.0))
        assert "low" in alert.headline.lower()

    def test_action_headline_mentions_urgent(self):
        alert = generate_alert(_make_risk(90.0))
        assert "urgent" in alert.headline.lower() or "emergency" in alert.headline.lower()

    def test_warning_headline_mentions_elevated(self):
        alert = generate_alert(_make_risk(70.0))
        assert "warning" in alert.headline.lower() or "elevated" in alert.headline.lower()

    def test_headline_contains_score(self):
        risk = _make_risk(72.0)
        alert = generate_alert(risk)
        assert "72" in alert.headline

    def test_headline_contains_community_name(self):
        risk = _make_risk(65.0)
        alert = generate_alert(risk)
        assert risk.community_name in alert.headline


# ---------------------------------------------------------------------------
# Voice script
# ---------------------------------------------------------------------------

class TestVoiceScript:
    def test_voice_script_non_empty(self):
        alert = generate_alert(_make_risk(85.0))
        assert len(alert.voice_script) > 30

    def test_none_level_voice_mentions_stable(self):
        alert = generate_alert(_make_risk(15.0))
        assert "stable" in alert.voice_script.lower() or "no action" in alert.voice_script.lower()

    def test_action_voice_mentions_urgent(self):
        alert = generate_alert(_make_risk(90.0))
        assert "urgent" in alert.voice_script.lower() or "emergency" in alert.voice_script.lower()

    def test_voice_mentions_community_name(self):
        risk = _make_risk(70.0)
        alert = generate_alert(risk)
        assert risk.community_name in alert.voice_script


# ---------------------------------------------------------------------------
# component_breakdown arithmetic
# ---------------------------------------------------------------------------

class TestComponentBreakdown:
    def test_breakdown_keys_present(self):
        alert = generate_alert(_make_risk(60.0))
        keys = alert.component_breakdown.keys()
        assert "crop_health" in keys
        assert "disruption" in keys
        assert "corridor_dependency" in keys
        assert "community_vulnerability" in keys

    def test_breakdown_values_are_weighted(self):
        """
        component_breakdown values are component_score × weight.
        For a risk with crop_health=80 → breakdown["crop_health"] = 80 × 0.40 = 32.0
        """
        components = _ComponentScores(
            crop_health=80.0,
            disruption=50.0,
            corridor_dependency=60.0,
            community_vulnerability=20.0,
        )
        risk = _RiskScore(risk_score=60.0, components=components)
        alert = generate_alert(risk)
        assert abs(alert.component_breakdown["crop_health"] - 32.0) < 0.1
        assert abs(alert.component_breakdown["disruption"] - 15.0) < 0.1
        assert abs(alert.component_breakdown["corridor_dependency"] - 12.0) < 0.1
        assert abs(alert.component_breakdown["community_vulnerability"] - 2.0) < 0.1


# ---------------------------------------------------------------------------
# generate_all_alerts
# ---------------------------------------------------------------------------

class TestGenerateAllAlerts:
    def test_sorted_descending_by_risk(self):
        risks = [_make_risk(s) for s in [30.0, 85.0, 55.0, 70.0]]
        alerts = generate_all_alerts(risks)
        scores = [a.risk_score for a in alerts]
        assert scores == sorted(scores, reverse=True)

    def test_count_matches_input(self):
        risks = [_make_risk(s) for s in [20.0, 50.0, 75.0, 90.0]]
        alerts = generate_all_alerts(risks)
        assert len(alerts) == 4

    def test_empty_input_returns_empty(self):
        assert generate_all_alerts([]) == []


# ---------------------------------------------------------------------------
# filter_active_alerts
# ---------------------------------------------------------------------------

class TestFilterActiveAlerts:
    def test_removes_none_level(self):
        risks = [_make_risk(10.0), _make_risk(50.0), _make_risk(70.0)]
        all_alerts = [generate_alert(r) for r in risks]
        active = filter_active_alerts(all_alerts)
        assert all(a.level is not None for a in active)

    def test_none_level_alert_excluded(self):
        risks = [_make_risk(5.0)]
        all_alerts = [generate_alert(r) for r in risks]
        assert filter_active_alerts(all_alerts) == []

    def test_all_active_levels_pass(self):
        risks = [_make_risk(45.0), _make_risk(65.0), _make_risk(85.0)]
        all_alerts = [generate_alert(r) for r in risks]
        active = filter_active_alerts(all_alerts)
        assert len(active) == 3
        levels = {a.level for a in active}
        assert levels == {"Watch", "Warning", "Action"}

    def test_empty_input_returns_empty(self):
        assert filter_active_alerts([]) == []


# ---------------------------------------------------------------------------
# Mock data quality flag propagation
# ---------------------------------------------------------------------------

class TestMockDataQuality:
    def test_mock_note_in_explanation(self):
        risk = _make_risk(60.0, data_quality="mock")
        alert = generate_alert(risk)
        # The explanation should note that data is estimated
        assert "estimated" in alert.explanation.lower() or "unavailable" in alert.explanation.lower()

    def test_full_quality_no_mock_note(self):
        risk = _make_risk(60.0, data_quality="full", top_factors=["Real factor"])
        alert = generate_alert(risk)
        assert "estimated" not in alert.explanation.lower()


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------

class TestExplanation:
    def test_explanation_contains_score(self):
        risk = _make_risk(73.0)
        alert = generate_alert(risk)
        assert "73" in alert.explanation

    def test_explanation_no_factors_fallback(self):
        risk = _make_risk(60.0, top_factors=[])
        alert = generate_alert(risk)
        assert len(alert.explanation) > 10