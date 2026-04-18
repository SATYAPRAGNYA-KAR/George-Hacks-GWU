"""
Offline tests for fema.py — uses a fixture so no network is required.

Run:
    python -m pytest backend/test_fema.py -v

The final `live` test is skipped by default; run with LIVE=1 to hit the
real OpenFEMA API end-to-end once you're on a networked machine.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import fema

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fema_sample.json"


@pytest.fixture
def fema_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_iowa_aggregates_counties_per_disaster(fema_payload):
    """Three IA rows for disaster 4812 should collapse into one record
    with all three counties."""
    with patch("fema._request_fema", return_value=fema_payload):
        disasters = fema.fetch_fema_disasters("IA", days_back=365)

    by_num = {d.disaster_number: d for d in disasters}
    assert 4812 in by_num
    storm = by_num[4812]
    assert storm.type == "Severe Storm"
    assert storm.state == "IA"
    assert storm.counties == ["Linn (County)", "Polk (County)", "Story (County)"]
    assert storm.is_active is True  # incidentEndDate is null


def test_active_only_filters_out_closed_and_old(fema_payload):
    """Default behavior: drop disasters whose incidentEndDate has passed
    and anything outside the days_back window."""
    with patch("fema._request_fema", return_value=fema_payload):
        disasters = fema.fetch_fema_disasters("IA", days_back=365)

    nums = {d.disaster_number for d in disasters}
    assert 4812 in nums        # ongoing, within window
    assert 4790 not in nums    # end date in Feb 2026, closed before Apr 18
    assert 4755 not in nums    # closed
    assert 4700 not in nums    # outside window


def test_include_closed_keeps_everything_in_window(fema_payload):
    with patch("fema._request_fema", return_value=fema_payload):
        disasters = fema.fetch_fema_disasters(
            "IA", days_back=365, include_closed=True
        )

    nums = {d.disaster_number for d in disasters}
    # 4700 is outside the 365-day window, so still filtered by FEMA's own
    # $filter clause -- but our fixture returns it anyway, so include_closed
    # should surface it here too.
    assert {4812, 4790, 4755}.issubset(nums)


def test_output_shape_matches_contract(fema_payload):
    """Builder 3 expects {type, counties, declaration_date} at minimum."""
    with patch("fema._request_fema", return_value=fema_payload):
        disasters = fema.fetch_fema_disasters("IA", days_back=365)

    assert disasters, "expected at least one active IA disaster"
    d = disasters[0].to_dict()
    for required in ("type", "counties", "declaration_date",
                     "disaster_number", "state", "is_active"):
        assert required in d, f"missing field: {required}"
    assert isinstance(d["counties"], list)


def test_filter_clause_includes_state_and_date():
    clause = fema._build_filter("ia", since=None)
    assert clause == "state eq 'IA'"

    import datetime as dt
    since = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    clause = fema._build_filter("CA", since=since)
    assert "state eq 'CA'" in clause
    assert "declarationDate ge '2026-01-01T00:00:00.000Z'" in clause


def test_empty_state_returns_empty_list(fema_payload):
    """A state with no rows in the response should just return []."""
    empty_payload = {"DisasterDeclarationsSummaries": []}
    with patch("fema._request_fema", return_value=empty_payload):
        disasters = fema.fetch_fema_disasters("WY")
    assert disasters == []


def test_newest_first_ordering(fema_payload):
    with patch("fema._request_fema", return_value=fema_payload):
        disasters = fema.fetch_fema_disasters(
            "IA", days_back=365, include_closed=True
        )
    dates = [d.declaration_date for d in disasters if d.declaration_date]
    assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# Live smoke test -- only runs when LIVE=1
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    os.environ.get("LIVE") != "1",
    reason="Live test disabled; set LIVE=1 to hit the real FEMA API.",
)
def test_live_iowa_call_returns_something():
    disasters = fema.fetch_fema_disasters("IA", days_back=365 * 2,
                                          include_closed=True)
    assert isinstance(disasters, list)
    if disasters:
        d = disasters[0]
        assert d.state == "IA"
        assert d.type
