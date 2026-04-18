"""
Offline tests for noaa.py — uses a fixture so no network is required.

Run:
    python -m pytest backend/test_noaa.py -v

The final `live` test is skipped by default; run with LIVE=1 to hit the
real NWS API end-to-end.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import noaa

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "noaa_sample.json"


@pytest.fixture
def nws_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_filters_to_monitored_categories(nws_payload):
    """Tornado Warning is in the fixture but not in our monitored set —
    it must be dropped."""
    with patch("noaa._request_nws", return_value=nws_payload):
        alerts = noaa.fetch_weather_alerts("IA")

    events = {a.event for a in alerts}
    assert "Tornado Warning" not in events
    # The four we expect:
    assert {"Flood Warning", "Freeze Warning",
            "Excessive Heat Warning", "Drought Information Statement"} == events


def test_category_buckets_correctly(nws_payload):
    with patch("noaa._request_nws", return_value=nws_payload):
        alerts = noaa.fetch_weather_alerts("IA")

    by_event = {a.event: a for a in alerts}
    assert by_event["Flood Warning"].alert_type == "flood"
    assert by_event["Freeze Warning"].alert_type == "frost"
    assert by_event["Excessive Heat Warning"].alert_type == "heat"
    assert by_event["Drought Information Statement"].alert_type == "drought"


def test_subset_of_categories(nws_payload):
    """Passing categories=['flood'] should yield only flood alerts."""
    with patch("noaa._request_nws", return_value=nws_payload):
        alerts = noaa.fetch_weather_alerts("IA", categories=["flood"])
    assert all(a.alert_type == "flood" for a in alerts)
    assert len(alerts) == 1


def test_unknown_category_raises(nws_payload):
    with patch("noaa._request_nws", return_value=nws_payload):
        with pytest.raises(ValueError):
            noaa.fetch_weather_alerts("IA", categories=["locusts"])


def test_output_shape_matches_contract(nws_payload):
    """Builder 3 contract: {alert_type, severity, affected_area, expires_at}."""
    with patch("noaa._request_nws", return_value=nws_payload):
        alerts = noaa.fetch_weather_alerts("IA")

    assert alerts
    d = alerts[0].to_dict()
    for required in ("alert_type", "severity", "affected_area", "expires_at"):
        assert required in d, f"missing: {required}"
    assert isinstance(d["affected_area"], str)


def test_area_desc_split_into_list(nws_payload):
    with patch("noaa._request_nws", return_value=nws_payload):
        alerts = noaa.fetch_weather_alerts("IA", categories=["flood"])
    flood = alerts[0]
    assert flood.areas == ["Polk, IA", "Story, IA", "Dallas, IA"]


def test_point_vs_state_routing():
    """Point strings should hit ?point=, state codes should hit ?area=."""
    captured: list[dict] = []

    def fake_request(params, timeout):
        captured.append(params)
        return {"features": []}

    with patch("noaa._request_nws", side_effect=fake_request):
        noaa.fetch_weather_alerts("IA")
        noaa.fetch_weather_alerts("41.59,-93.62")

    assert captured[0].get("area") == "IA"
    assert "point" not in captured[0]
    assert captured[1].get("point") == "41.59,-93.62"
    assert "area" not in captured[1]


def test_newest_first_by_effective(nws_payload):
    with patch("noaa._request_nws", return_value=nws_payload):
        alerts = noaa.fetch_weather_alerts("IA")
    effs = [a.effective_at for a in alerts if a.effective_at]
    assert effs == sorted(effs, reverse=True)


def test_empty_response_returns_empty_list():
    with patch("noaa._request_nws", return_value={"features": []}):
        assert noaa.fetch_weather_alerts("WY") == []


# ---------------------------------------------------------------------------
# Live smoke test -- only runs when LIVE=1
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    os.environ.get("LIVE") != "1",
    reason="Live test disabled; set LIVE=1 to hit the real NWS API.",
)
def test_live_iowa_call_returns_list():
    alerts = noaa.fetch_weather_alerts("IA")
    assert isinstance(alerts, list)
    for a in alerts:
        assert a.alert_type in {"drought", "heat", "frost", "flood"}
