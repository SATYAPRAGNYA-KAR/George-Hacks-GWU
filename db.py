"""
db.py — MongoDB async client for RootBridge

Collections
-----------
  users           — onboarded platform users
  risk_cache      — per-state/county risk scores (TTL-indexed, 6h)
  analysis_cache  — crop-health analysis results per region
  alerts_log      — alert history with timestamps
  signal_reports  — community-submitted ground-truth signals

Connection
----------
Set MONGODB_URI in your .env (or environment).
Defaults to mongodb://localhost:27017 for local dev.

Usage
-----
  from db import get_db, Collections
  db = await get_db()
  await db[Collections.USERS].insert_one({...})
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
    USERS          = "users"
    RISK_CACHE     = "risk_cache"
    ANALYSIS_CACHE = "analysis_cache"
    ALERTS_LOG     = "alerts_log"
    SIGNAL_REPORTS = "signal_reports"
    WEIGHTS_LOG    = "weights_log"   # Gemini-suggested weight snapshots per state


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
    """Create all indexes idempotently on startup."""
    try:
        # users — unique email, state filter
        await db[Collections.USERS].create_indexes([
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("state_abbr", ASCENDING)]),
            IndexModel([("role", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ])

        # risk_cache — keyed by state+county, TTL 6 hours
        await db[Collections.RISK_CACHE].create_indexes([
            IndexModel([("state_abbr", ASCENDING), ("county_fips", ASCENDING)], unique=True),
            IndexModel([("state_abbr", ASCENDING)]),
            # TTL index: documents expire 6 hours after cached_at
            IndexModel([("cached_at", ASCENDING)], expireAfterSeconds=21600),
        ])

        # analysis_cache — keyed by region_id, TTL 6 hours
        await db[Collections.ANALYSIS_CACHE].create_indexes([
            IndexModel([("region_id", ASCENDING)], unique=True),
            IndexModel([("cached_at", ASCENDING)], expireAfterSeconds=21600),
        ])

        # alerts_log — query by state, level, timestamp
        await db[Collections.ALERTS_LOG].create_indexes([
            IndexModel([("state_abbr", ASCENDING), ("generated_at", DESCENDING)]),
            IndexModel([("level", ASCENDING)]),
            IndexModel([("community_id", ASCENDING)]),
        ])

        # signal_reports — community-submitted
        await db[Collections.SIGNAL_REPORTS].create_indexes([
            IndexModel([("state_abbr", ASCENDING), ("county_fips", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ])

        # weights_log — Gemini-suggested weights per state
        await db[Collections.WEIGHTS_LOG].create_indexes([
            IndexModel([("state_abbr", ASCENDING), ("created_at", DESCENDING)]),
        ])

        logger.info("MongoDB indexes ensured.")
    except Exception as e:
        logger.warning("Index creation warning (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# User model helpers
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
    """
    Build a new user document. `role` is one of:
      public | community | responder | coordinator | government | admin
    """
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
        "alerts_opt_in": True,   # receive SMS/voice alerts by default
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