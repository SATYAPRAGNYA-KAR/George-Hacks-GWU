"""
community_requests_api.py — Community food access request lifecycle

Endpoints (mounted under /api):
  POST /api/requests                          — submit new request
  GET  /api/requests/{reference}              — look up by reference number
  GET  /api/requests?state=TX&status=verified — list requests (responder view)
  PATCH /api/requests/{reference}/status     — update status (responder action)
  GET  /api/requests/stats/{state_abbr}      — aggregate stats for dashboard

Status lifecycle:
  submitted → screening → verified → assigned → in_transit → resolved
  any → escalated | closed
"""

from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


def _db():
    from db import get_db
    return get_db()


def _generate_reference() -> str:
    """Generate a human-readable reference like FR-A3K7-9QXZ."""
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(random.choices(chars, k=4))
    part2 = "".join(random.choices(chars, k=4))
    return f"FR-{part1}-{part2}"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SubmitRequestBody(BaseModel):
    state_abbr:     str
    county_fips:    str
    city:           str = ""
    zip:            str = ""
    type:           str
    urgency:        str
    household_size: int = Field(0, ge=0, le=200)
    description:    str = Field(..., min_length=5, max_length=1000)
    contact:        Optional[str] = None
    contact_email:  Optional[str] = None


class UpdateStatusBody(BaseModel):
    status:         str
    note:           str = ""
    assigned_org:   Optional[str] = None
    assigned_org_name: Optional[str] = None
    resolution_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(doc: dict) -> dict:
    """Convert MongoDB doc to JSON-safe dict."""
    doc = dict(doc)
    doc.pop("_id", None)
    # Convert datetime objects
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    if "status_history" in doc:
        for entry in doc["status_history"]:
            if isinstance(entry.get("timestamp"), datetime):
                entry["timestamp"] = entry["timestamp"].isoformat()
    return doc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/requests", tags=["community"], status_code=201)
async def submit_request(body: SubmitRequestBody):
    """Submit a new community food access request. Saved to MongoDB."""
    from db import Collections, new_community_request

    reference = _generate_reference()
    db = await _db()

    # Ensure uniqueness (extremely unlikely collision but safe)
    while await db[Collections.COMMUNITY_REQUESTS].find_one({"reference": reference}):
        reference = _generate_reference()

    doc = new_community_request(
        reference=reference,
        state_abbr=body.state_abbr,
        county_fips=body.county_fips,
        city=body.city,
        zip_code=body.zip,
        request_type=body.type,
        urgency=body.urgency,
        household_size=body.household_size,
        description=body.description,
        contact=body.contact,
        contact_email=body.contact_email,
    )

    await db[Collections.COMMUNITY_REQUESTS].insert_one(doc)
    return {"status": "submitted", "reference": reference, "request": _serialize(doc)}


@router.get("/requests/{reference}", tags=["community"])
async def get_request(reference: str):
    """Look up a request by its reference number (e.g. FR-A3K7-9QXZ)."""
    from db import Collections
    db = await _db()
    doc = await db[Collections.COMMUNITY_REQUESTS].find_one(
        {"reference": reference.upper().strip()}
    )
    if not doc:
        raise HTTPException(404, f"No request found with reference {reference!r}")
    return _serialize(doc)


@router.get("/requests", tags=["community"])
async def list_requests(
    state_abbr: Optional[str] = Query(None),
    county_fips: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    urgency: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
):
    """
    List community requests. Used by the Responder portal.
    Filter by state, county, status, or urgency.
    """
    from db import Collections
    db = await _db()

    query: dict[str, Any] = {}
    if state_abbr:
        query["state_abbr"] = state_abbr.upper()
    if county_fips:
        query["county_fips"] = county_fips
    if status:
        query["status"] = status
    if urgency:
        query["urgency"] = urgency

    cursor = (
        db[Collections.COMMUNITY_REQUESTS]
        .find(query)
        .sort([("urgency", 1), ("created_at", -1)])  # urgent_24h sorts first alphabetically
        .skip(skip)
        .limit(limit)
    )

    docs = []
    async for doc in cursor:
        docs.append(_serialize(doc))

    total = await db[Collections.COMMUNITY_REQUESTS].count_documents(query)
    return {"count": len(docs), "total": total, "requests": docs}


@router.patch("/requests/{reference}/status", tags=["community"])
async def update_request_status(reference: str, body: UpdateStatusBody):
    """
    Update the status of a request.
    Validates status transitions. Appends to status_history.
    Used by responders to move requests through the lifecycle.
    """
    from db import Collections, STATUS_TRANSITIONS, STATUS_LABELS, VALID_STATUSES
    db = await _db()

    doc = await db[Collections.COMMUNITY_REQUESTS].find_one(
        {"reference": reference.upper().strip()}
    )
    if not doc:
        raise HTTPException(404, f"No request found with reference {reference!r}")

    current = doc["status"]
    new_status = body.status

    if new_status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status {new_status!r}. Valid: {VALID_STATUSES}")

    allowed = STATUS_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        raise HTTPException(
            400,
            f"Cannot transition from {current!r} to {new_status!r}. "
            f"Allowed next statuses: {allowed}"
        )

    now = datetime.now(timezone.utc)
    history_entry = {
        "status":    new_status,
        "timestamp": now.isoformat(),
        "note":      body.note or f"Status updated to {STATUS_LABELS.get(new_status, new_status)}.",
    }
    if body.assigned_org:
        history_entry["assigned_org"] = body.assigned_org

    update: dict[str, Any] = {
        "$set": {
            "status":     new_status,
            "updated_at": now,
        },
        "$push": {"status_history": history_entry},
    }

    if body.assigned_org:
        update["$set"]["assigned_org"]      = body.assigned_org
        update["$set"]["assigned_org_name"] = body.assigned_org_name or body.assigned_org
    if body.resolution_note:
        update["$set"]["resolution_note"] = body.resolution_note

    await db[Collections.COMMUNITY_REQUESTS].update_one(
        {"reference": reference.upper().strip()}, update
    )

    updated = await db[Collections.COMMUNITY_REQUESTS].find_one(
        {"reference": reference.upper().strip()}
    )
    return {"status": "updated", "request": _serialize(updated)}


@router.get("/requests/stats/{state_abbr}", tags=["community"])
async def get_request_stats(state_abbr: str):
    """
    Aggregate request statistics for a state.
    Used by the national and state dashboards.
    """
    from db import Collections
    db = await _db()

    pipeline = [
        {"$match": {"state_abbr": state_abbr.upper()}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
        }},
    ]
    cursor = db[Collections.COMMUNITY_REQUESTS].aggregate(pipeline)

    by_status: dict[str, int] = {}
    async for doc in cursor:
        by_status[doc["_id"]] = doc["count"]

    total = sum(by_status.values())
    open_count = sum(
        v for k, v in by_status.items()
        if k not in ("resolved", "closed")
    )

    return {
        "state_abbr": state_abbr.upper(),
        "total":      total,
        "open":       open_count,
        "by_status":  by_status,
    }