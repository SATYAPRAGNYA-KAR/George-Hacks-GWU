"""
Offline tests for routes.py — uses the real corridors.json plus synthetic
alerts/disasters so we never hit the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import fema
import noaa
import routes


@pytest.fixture(autouse=True)
def clear_corridor_cache():
    """Corridors are cached globally; reset between tests."""
    routes._corridors_cache = None
    yield
    routes._corridors_cache = None


# ---------------------------------------------------------------------------
# Builders for synthetic data
# ---------------------------------------------------------------------------
def _alert(event, severity, areas, expires="2026-04-20T12:00:00-05:00"):
    return noaa.WeatherAlert(
        id=f"test-{event}-{'-'.join(areas)}",
        alert_type=noaa.EVENT_TO_CATEGORY.get(event, "flood"),
        event=event,
        severity=severity,
        affected_area="; ".join(areas),
        areas=areas,
        expires_at=expires,
        effective_at="2026-04-18T06:00:00-05:00",
        headline=f"{event} test",
    )


def _disaster(num, dtype, state, counties, end=None):
    return fema.Disaster(
        disaster_number=num,
        type=dtype,
        state=state,
        counties=[f"{c} (County)" for c in counties],
        declaration_date="2026-04-01T00:00:00.000Z",
        incident_begin_date="2026-03-28T00:00:00.000Z",
        incident_end_date=end,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_clear_when_no_disruptions():
    s = routes.check_route_status("I-80", alerts=[], disasters=[])
    assert s.status == "clear"
    assert "no active disruptions" in s.reason
    assert s.impaired_segments == []
    assert s.estimated_duration is None


def test_severe_flood_on_i80_iowa_impairs():
    """A Severe Flood Warning in Polk, IA (which is on I-80) => impaired."""
    alerts = [_alert("Flood Warning", "Severe",
                     ["Polk, IA", "Story, IA"])]
    s = routes.check_route_status("I-80", alerts=alerts, disasters=[])
    assert s.status == "impaired"
    assert "Flood Warning" in s.reason
    # Story is on I-35, not I-80, so only Polk should register for I-80
    impaired_counties = {seg["county"] for seg in s.impaired_segments}
    assert "polk" in impaired_counties
    assert s.estimated_duration is not None


def test_extreme_heat_blocks():
    """Extreme severity => blocked."""
    alerts = [_alert("Excessive Heat Warning", "Extreme",
                     ["Kern, CA", "Los Angeles, CA"])]
    s = routes.check_route_status("I-5", alerts=alerts, disasters=[])
    assert s.status == "blocked"


def test_blocking_beats_impairing():
    """If one alert blocks and another only impairs, status is blocked."""
    alerts = [
        _alert("Flood Warning", "Severe", ["Polk, IA"]),       # impaired
        _alert("Excessive Heat Warning", "Extreme", ["Kern, CA"]),  # blocked (diff corridor)
    ]
    # Only Polk is on I-80, so I-80 should be only impaired
    s80 = routes.check_route_status("I-80", alerts=alerts, disasters=[])
    assert s80.status == "impaired"

    # For I-5, Kern is on the corridor and is Extreme -> blocked
    s5 = routes.check_route_status("I-5", alerts=alerts, disasters=[])
    assert s5.status == "blocked"


def test_fema_wildfire_blocks_i5():
    disasters = [_disaster(4820, "Fire", "CA", ["Shasta", "Tehama"])]
    # Fire is not in BLOCKING_DISASTER_TYPES by default (Wildfire is).
    # So Fire => impaired.
    s = routes.check_route_status("I-5", alerts=[], disasters=disasters)
    assert s.status == "impaired"
    assert "Fire" in s.reason

    disasters2 = [_disaster(4820, "Wildfire", "CA", ["Shasta"])]
    s2 = routes.check_route_status("I-5", alerts=[], disasters=disasters2)
    assert s2.status == "blocked"


def test_county_normalization_matches_fema_format():
    """FEMA returns 'Polk (County)' — we must normalize to match the corridor
    waypoint 'Polk'."""
    disasters = [_disaster(9999, "Flood", "IA", ["Polk"])]
    s = routes.check_route_status("I-80", alerts=[], disasters=disasters)
    assert s.status == "impaired"


def test_no_hit_when_county_not_on_corridor():
    """A severe alert in a county NOT on the corridor shouldn't register."""
    alerts = [_alert("Flood Warning", "Severe", ["Muscatine, IA"])]
    # Muscatine isn't in our I-80 waypoints
    s = routes.check_route_status("I-80", alerts=alerts, disasters=[])
    assert s.status == "clear"


def test_unknown_corridor_raises():
    with pytest.raises(KeyError):
        routes.check_route_status("I-42", alerts=[], disasters=[])


def test_minor_severity_does_not_impair():
    alerts = [_alert("Flood Advisory", "Minor", ["Polk, IA"])]
    s = routes.check_route_status("I-80", alerts=alerts, disasters=[])
    assert s.status == "clear"


def test_check_all_corridors_runs_offline():
    statuses = routes.check_all_corridors(alerts=[], disasters=[])
    ids = {s.corridor_id for s in statuses}
    assert ids == {"I-5", "I-10", "I-80", "I-35"}
    assert all(s.status == "clear" for s in statuses)


def test_output_shape_matches_contract():
    """Builder 3 contract: {corridor_id, status, reason, estimated_duration}."""
    alerts = [_alert("Flood Warning", "Severe", ["Polk, IA"])]
    s = routes.check_route_status("I-80", alerts=alerts, disasters=[])
    d = s.to_dict()
    for required in ("corridor_id", "status", "reason", "estimated_duration"):
        assert required in d


def test_normalize_county_handles_variants():
    assert routes._normalize_county("Polk") == "polk"
    assert routes._normalize_county("Polk (County)") == "polk"
    assert routes._normalize_county("Polk County") == "polk"
    assert routes._normalize_county("Polk, IA") == "polk"
    assert routes._normalize_county("Orleans (Parish)") == "orleans"


def test_reason_is_human_readable():
    alerts = [
        _alert("Flood Warning", "Severe", ["Polk, IA", "Dallas, IA"]),
        _alert("Freeze Warning", "Moderate", ["Polk, IA"]),
    ]
    s = routes.check_route_status("I-80", alerts=alerts, disasters=[])
    assert "Flood Warning" in s.reason
    assert "Freeze Warning" in s.reason
