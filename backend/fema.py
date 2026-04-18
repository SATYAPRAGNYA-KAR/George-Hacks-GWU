"""
OpenFEMA Disaster Declarations integration.

Pulls active disaster declarations from the OpenFEMA v2 API and normalizes
them into the shape Builder 3's risk engine expects.

API docs:     https://www.fema.gov/about/openfema/api
Dataset:      https://www.fema.gov/openfema-data-page/disaster-declarations-summaries-v2
Base URL:     https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries
Auth:         none (no API key required)

Author: Ruhani (Builder 2)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
DEFAULT_TIMEOUT = 20  # seconds
DEFAULT_ACTIVE_WINDOW_DAYS = 180


# ---------------------------------------------------------------------------
# Normalized output shape (what Builder 3 consumes)
# ---------------------------------------------------------------------------
@dataclass
class Disaster:
    disaster_number: int
    type: str                 # incidentType: Fire, Flood, Hurricane, etc.
    state: str                # two-letter code
    counties: list[str] = field(default_factory=list)  # designated areas
    declaration_date: str | None = None       # ISO date
    incident_begin_date: str | None = None
    incident_end_date: str | None = None      # null/None = still ongoing
    declaration_title: str | None = None
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------
def _build_filter(state: str, since: datetime | None) -> str:
    """Build the OData $filter clause."""
    clauses = [f"state eq '{state.upper()}'"]
    if since is not None:
        # FEMA accepts ISO 8601 with Z suffix for $filter comparisons
        iso = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        clauses.append(f"declarationDate ge '{iso}'")
    return " and ".join(clauses)


def _request_fema(params: dict[str, Any], timeout: int) -> dict[str, Any]:
    """Thin HTTP wrapper so it can be monkey-patched in tests."""
    url = f"{BASE_URL}?{urlencode(params)}"
    logger.info("GET %s", url)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_fema_disasters(
    state: str,
    *,
    days_back: int = DEFAULT_ACTIVE_WINDOW_DAYS,
    include_closed: bool = False,
    top: int = 1000,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[Disaster]:
    """
    Fetch active disaster declarations for a US state.

    "Active" means the declaration was issued within the last `days_back`
    days AND (unless `include_closed` is True) the incident has not ended.

    Args:
        state:          two-letter state code, e.g. "IA", "CA"
        days_back:      how far back to look for declarations
        include_closed: keep records whose incident_end_date is in the past
        top:            max raw rows to request from FEMA (default 1000)
        timeout:        HTTP timeout in seconds

    Returns:
        A list of Disaster objects, one per unique disaster_number, with
        all affected counties aggregated into `.counties`.

    Raises:
        requests.HTTPError, requests.ConnectionError on network failure.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days_back)

    params = {
        "$filter": _build_filter(state, since),
        "$orderby": "declarationDate desc",
        "$top": top,
        # Only pull the fields we care about -> smaller payload, faster
        "$select": ",".join([
            "disasterNumber",
            "state",
            "declarationDate",
            "incidentType",
            "incidentBeginDate",
            "incidentEndDate",
            "declarationTitle",
            "designatedArea",
        ]),
    }

    payload = _request_fema(params, timeout=timeout)
    rows = payload.get("DisasterDeclarationsSummaries", [])

    disasters = _aggregate_rows(rows)

    if not include_closed:
        disasters = [d for d in disasters if d.is_active]

    return disasters


def _aggregate_rows(rows: Iterable[dict[str, Any]]) -> list[Disaster]:
    """
    FEMA returns one row per (disaster_number, designated_area). Collapse
    into one Disaster per disaster_number with a counties list.
    """
    by_num: dict[int, Disaster] = {}
    now = datetime.now(timezone.utc)

    for r in rows:
        num = r.get("disasterNumber")
        if num is None:
            continue

        if num not in by_num:
            end_date = r.get("incidentEndDate")
            is_active = _is_active(end_date, now)
            by_num[num] = Disaster(
                disaster_number=num,
                type=r.get("incidentType") or "Unknown",
                state=r.get("state") or "",
                declaration_date=r.get("declarationDate"),
                incident_begin_date=r.get("incidentBeginDate"),
                incident_end_date=end_date,
                declaration_title=r.get("declarationTitle"),
                is_active=is_active,
            )

        area = r.get("designatedArea")
        if area and area not in by_num[num].counties:
            by_num[num].counties.append(area)

    # Sort counties for stable output
    for d in by_num.values():
        d.counties.sort()

    # Newest first
    return sorted(
        by_num.values(),
        key=lambda d: d.declaration_date or "",
        reverse=True,
    )


def _is_active(end_date: str | None, now: datetime) -> bool:
    """A declaration is active if incidentEndDate is null or in the future."""
    if not end_date:
        return True
    try:
        # FEMA returns e.g. "2024-03-15T00:00:00.000Z"
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return dt >= now
    except ValueError:
        logger.warning("Could not parse incidentEndDate=%r", end_date)
        return True


# ---------------------------------------------------------------------------
# CLI for quick manual testing
# ---------------------------------------------------------------------------
def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch active FEMA disasters.")
    parser.add_argument("state", help="Two-letter state code (e.g. IA, CA)")
    parser.add_argument("--days", type=int, default=DEFAULT_ACTIVE_WINDOW_DAYS)
    parser.add_argument("--include-closed", action="store_true")
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    disasters = fetch_fema_disasters(
        args.state,
        days_back=args.days,
        include_closed=args.include_closed,
    )

    if args.json:
        print(json.dumps([d.to_dict() for d in disasters], indent=2))
        return

    if not disasters:
        print(f"No active declarations for {args.state.upper()} "
              f"in the last {args.days} days.")
        return

    print(f"{len(disasters)} active declaration(s) for {args.state.upper()}:\n")
    for d in disasters:
        print(f"  #{d.disaster_number}  {d.type:<12}  {d.declaration_date}")
        print(f"    {d.declaration_title}")
        print(f"    Counties ({len(d.counties)}): "
              f"{', '.join(d.counties[:5])}"
              f"{' ...' if len(d.counties) > 5 else ''}")
        print()


if __name__ == "__main__":
    _cli()
