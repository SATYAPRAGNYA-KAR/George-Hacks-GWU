"""
db.py — MongoDB async client for RootBridge

Collections
-----------
  users               — onboarded platform users
  risk_cache          — per-state/county risk scores (TTL 6h)
  analysis_cache      — crop-health analysis results per region
  alerts_log          — alert history with timestamps
  signal_reports      — community ground-truth signals
  community_requests  — food access requests with full status lifecycle
  weights_log         — Gemini-suggested weight snapshots per state
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME     = os.getenv("MONGODB_DB",  "rootbridge")

_client: AsyncIOMotorClient | None = None


class Collections:
    USERS               = "users"
    RISK_CACHE          = "risk_cache"
    ANALYSIS_CACHE      = "analysis_cache"
    ALERTS_LOG          = "alerts_log"
    SIGNAL_REPORTS      = "signal_reports"
    COMMUNITY_REQUESTS  = "community_requests"
    WEIGHTS_LOG         = "weights_log"


async def get_db() -> AsyncIOMotorDatabase:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        await _ensure_indexes(_client[DB_NAME])
        logger.info("MongoDB connected: %s / %s", MONGODB_URI, DB_NAME)
    return _client[DB_NAME]


async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    try:
        await db[Collections.USERS].create_indexes([
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("state_abbr", ASCENDING)]),
            IndexModel([("role", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ])

        await db[Collections.RISK_CACHE].create_indexes([
            IndexModel([("state_abbr", ASCENDING), ("county_fips", ASCENDING)], unique=True),
            IndexModel([("state_abbr", ASCENDING)]),
            IndexModel([("cached_at", ASCENDING)], expireAfterSeconds=21600),
        ])

        await db[Collections.ANALYSIS_CACHE].create_indexes([
            IndexModel([("region_id", ASCENDING)], unique=True),
            IndexModel([("cached_at", ASCENDING)], expireAfterSeconds=21600),
        ])

        await db[Collections.ALERTS_LOG].create_indexes([
            IndexModel([("state_abbr", ASCENDING), ("generated_at", DESCENDING)]),
            IndexModel([("level", ASCENDING)]),
            IndexModel([("community_id", ASCENDING)]),
        ])

        await db[Collections.SIGNAL_REPORTS].create_indexes([
            IndexModel([("state_abbr", ASCENDING), ("county_fips", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ])

        # Community requests — full lifecycle tracking
        await db[Collections.COMMUNITY_REQUESTS].create_indexes([
            IndexModel([("reference", ASCENDING)], unique=True),
            IndexModel([("state_abbr", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("county_fips", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("urgency", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("contact_email", ASCENDING)]),
        ])

        await db[Collections.WEIGHTS_LOG].create_indexes([
            IndexModel([("state_abbr", ASCENDING), ("created_at", DESCENDING)]),
        ])

        logger.info("MongoDB indexes ensured.")
    except Exception as e:
        logger.warning("Index creation warning (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

def new_user(
    email: str,
    name: str,
    role: str,
    state_abbr: str,
    county_fips: str | None = None,
    org_name: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "email":       email.lower().strip(),
        "name":        name.strip(),
        "role":        role,
        "state_abbr":  state_abbr.upper(),
        "county_fips": county_fips,
        "org_name":    org_name,
        "phone":       phone,
        "created_at":  now,
        "updated_at":  now,
        "active":      True,
        "alerts_opt_in": True,
    }


# ---------------------------------------------------------------------------
# Community request model
# ---------------------------------------------------------------------------

# Valid status transitions:
#   submitted → screening → verified → assigned → in_transit → resolved
#   any → escalated
#   any → closed  (manual close without resolution)
VALID_STATUSES = [
    "submitted", "screening", "verified", "assigned",
    "in_transit", "resolved", "escalated", "closed",
]

STATUS_TRANSITIONS: dict[str, list[str]] = {
    "submitted":  ["screening", "verified", "escalated", "closed"],
    "screening":  ["verified", "escalated", "closed"],
    "verified":   ["assigned", "escalated", "closed"],
    "assigned":   ["in_transit", "escalated", "closed"],
    "in_transit": ["resolved", "escalated", "closed"],
    "resolved":   [],
    "escalated":  ["assigned", "closed"],
    "closed":     [],
}

STATUS_LABELS: dict[str, str] = {
    "submitted":  "Submitted",
    "screening":  "Under review",
    "verified":   "Verified",
    "assigned":   "Assigned to responder",
    "in_transit": "Help on the way",
    "resolved":   "Resolved",
    "escalated":  "Escalated",
    "closed":     "Closed",
}


def new_community_request(
    reference: str,
    state_abbr: str,
    county_fips: str,
    city: str,
    zip_code: str,
    request_type: str,
    urgency: str,
    household_size: int,
    description: str,
    contact: str | None = None,
    contact_email: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "reference":      reference,
        "state_abbr":     state_abbr.upper(),
        "county_fips":    county_fips,
        "city":           city,
        "zip":            zip_code,
        "type":           request_type,
        "urgency":        urgency,
        "household_size": household_size,
        "description":    description,
        "contact":        contact,
        "contact_email":  contact_email,
        "status":         "submitted",
        "status_history": [
            {"status": "submitted", "timestamp": now.isoformat(), "note": "Request submitted by community member."}
        ],
        "assigned_org":    None,
        "assigned_org_name": None,
        "resolution_note": None,
        "created_at":      now,
        "updated_at":      now,
    }


def new_signal_report(
    state_abbr: str,
    county_fips: str,
    category: str,
    severity: str,
    description: str,
    reporter_fingerprint: str,
    zip_code: str | None = None,
    image_url: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "state_abbr":           state_abbr.upper(),
        "county_fips":          county_fips,
        "zip_code":             zip_code,
        "category":             category,
        "severity":             severity,
        "description":          description,
        "reporter_fingerprint": reporter_fingerprint,
        "image_url":            image_url,
        "created_at":           now,
        "verified":             False,
    }