"""
state_fpi_api.py — FastAPI router: state + county FPI for all 50 US states

New endpoints (all mounted under /api):
  GET  /api/fpi/state/{state_abbr}              — state FPI with Gemini weights
  GET  /api/fpi/county/{state_abbr}/{county_fips} — county FPI
  GET  /api/fpi/states                          — all states summary (for national map)
  GET  /api/weather/{state_abbr}                — raw weather snapshot
  POST /api/users/register                      — onboard a new user to MongoDB
  GET  /api/users/{email}                       — look up a user
  POST /api/signals                             — submit a community signal report
  GET  /api/signals/{state_abbr}                — get signals for a state

All FPI endpoints accept an optional `refresh=true` query param to bypass cache.

The frontend calls these to replace / augment its deterministic baseline data.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy imports so the module loads even if optional deps are missing
def _db():
    from db import get_db
    return get_db()

def _weather(state: str):
    from nasa_weather import get_state_weather_snapshot
    return get_state_weather_snapshot(state)

def _county_weather(state: str, fips: str):
    from nasa_weather import get_county_weather_snapshot
    return get_county_weather_snapshot(state, fips)

def _score_county(state_abbr, state_name, fips, name, shock, vuln, supply, readiness):
    from gemini_scorer import score_county_fpi
    return score_county_fpi(state_abbr, state_name, fips, name, shock, vuln, supply, readiness)

def _score_state(state_abbr, state_name, weather, county_sums, fema_count=0):
    from gemini_scorer import score_state_fpi
    return score_state_fpi(state_abbr, state_name, weather, county_sums, fema_count=fema_count)

# State name lookup
from regions import list_regions, get_region, RegionNotFoundError

_STATE_NAMES: dict[str, str] = {
    r.id.upper(): r.display_name
    for r in list_regions()
    if len(r.id) == 2 and r.id.upper() == r.id
}

# Baseline vulnerability estimates from ACS/USDA (seeded; real connector is v2)
# Format: {state_abbr: {county_fips: {poverty_pct, food_insecurity_pct, ...}}}
# For states without seeded data, we use state-level estimates
_STATE_VULN_BASELINE: dict[str, dict] = {
    "IA": {"poverty_pct": 11.2, "food_insecurity_pct": 10.8, "no_vehicle_pct": 5.1, "svi_score": 38},
    "LA": {"poverty_pct": 19.0, "food_insecurity_pct": 17.5, "no_vehicle_pct": 10.2, "svi_score": 62},
    "TX": {"poverty_pct": 14.2, "food_insecurity_pct": 13.8, "no_vehicle_pct": 6.2, "svi_score": 48},
    "MS": {"poverty_pct": 21.5, "food_insecurity_pct": 19.2, "no_vehicle_pct": 9.8, "svi_score": 70},
    "WV": {"poverty_pct": 17.5, "food_insecurity_pct": 16.1, "no_vehicle_pct": 8.2, "svi_score": 65},
    "AL": {"poverty_pct": 16.8, "food_insecurity_pct": 15.4, "no_vehicle_pct": 7.9, "svi_score": 60},
    "KY": {"poverty_pct": 16.2, "food_insecurity_pct": 14.8, "no_vehicle_pct": 7.1, "svi_score": 58},
    "AR": {"poverty_pct": 16.0, "food_insecurity_pct": 14.9, "no_vehicle_pct": 7.5, "svi_score": 57},
    "FL": {"poverty_pct": 13.5, "food_insecurity_pct": 12.9, "no_vehicle_pct": 8.8, "svi_score": 52},
    "CA": {"poverty_pct": 12.8, "food_insecurity_pct": 11.6, "no_vehicle_pct": 7.2, "svi_score": 45},
    "NY": {"poverty_pct": 13.0, "food_insecurity_pct": 12.1, "no_vehicle_pct": 28.5, "svi_score": 44},
    "GA": {"poverty_pct": 14.9, "food_insecurity_pct": 14.2, "no_vehicle_pct": 7.0, "svi_score": 52},
}
_DEFAULT_VULN = {"poverty_pct": 14.0, "food_insecurity_pct": 12.5, "no_vehicle_pct": 7.5, "svi_score": 45}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserRegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    name: str
    role: str = Field("public", description="public|community|responder|coordinator|government|admin")
    state_abbr: str = Field(..., max_length=2)
    county_fips: Optional[str] = None
    org_name: Optional[str] = None
    phone: Optional[str] = None


class SignalReportRequest(BaseModel):
    state_abbr: str
    county_fips: str
    category: str
    severity: str
    description: str
    zip_code: Optional[str] = None
    reporter_fingerprint: Optional[str] = None


# ---------------------------------------------------------------------------
# Weather endpoints
# ---------------------------------------------------------------------------

@router.get("/weather/{state_abbr}", tags=["weather"])
async def get_weather(state_abbr: str):
    """Real-time weather snapshot for a state: NWS alerts + drought + FIRMS."""
    try:
        get_region(state_abbr.upper())
    except RegionNotFoundError:
        raise HTTPException(404, f"Unknown state: {state_abbr}")

    snapshot = _weather(state_abbr.upper())
    return snapshot


# ---------------------------------------------------------------------------
# FPI endpoints
# ---------------------------------------------------------------------------

@router.get("/fpi/states", tags=["fpi"])
async def get_all_states_fpi(
    refresh: bool = Query(False, description="Bypass cache and re-score"),
):
    """
    Return FPI summary for all 50 states.
    Used by the frontend national map to color states by risk.
    """
    from regions import list_regions
    all_states = [r for r in list_regions() if len(r.id) == 2 and r.id.upper() == r.id and r.id != "DC"]

    results = []
    for region in all_states:
        try:
            state = region.id.upper()

            # Try MongoDB cache first
            if not refresh:
                db = await _db()
                from db import Collections
                cached = await db[Collections.RISK_CACHE].find_one(
                    {"state_abbr": state, "county_fips": "__state__"},
                    sort=[("cached_at", -1)]
                )
                if cached:
                    cached.pop("_id", None)
                    results.append(cached)
                    continue

            weather = _weather(state)
            vuln    = _STATE_VULN_BASELINE.get(state, _DEFAULT_VULN)
            state_name = _STATE_NAMES.get(state, region.display_name)

            # # State-level score: no county data needed for quick overview
            # shock = weather.get("shock_score", 20.0)
            # vuln_score = (
            #     vuln["poverty_pct"] * 0.35 +
            #     vuln["food_insecurity_pct"] * 0.35 +
            #     vuln["no_vehicle_pct"] * 0.15 +
            #     vuln["svi_score"] * 0.15
            # )
            # # For states page we use a lighter Gemini call (state-level)
            # scored = _score_state(
            #     state, state_name, weather,
            #     [{"score": (shock * 0.4 + vuln_score * 0.6), "trigger": "watch",
            #       "population": 1000000}],
            # )
            shock      = weather.get("shock_score", 20.0)
            vuln       = _STATE_VULN_BASELINE.get(state, _DEFAULT_VULN)
            vuln_score = (
                vuln["poverty_pct"] * 0.35 +
                vuln["food_insecurity_pct"] * 0.35 +
                vuln["no_vehicle_pct"] * 0.15 +
                vuln["svi_score"] * 0.15
            )

            # Pass raw components — Gemini decides how to weight them
            scored = _score_state(
                state, state_name, weather,
                [{
                    "shock_score":    round(shock, 1),
                    "vulnerability":  round(vuln_score, 1),
                    "supply_gap":     50,
                    "readiness_gap":  50,
                    "trigger":        "watch",
                    "population":     1_000_000,
                }],
            )

            doc = {
                "state_abbr":      state,
                "state_name":      state_name,
                "risk_score":      scored.get("state_risk_score", 30),
                "trigger":         scored.get("trigger", "prepared"),
                "dominant_driver": scored.get("dominant_driver", "vulnerability"),
                "top_factors":     scored.get("top_factors", []),
                "weather_status":  weather.get("overall_status", "clear"),
                "shock_score":     shock,
                "gemini_source":   scored.get("_source", "deterministic"),
                "cached_at":       datetime.datetime.utcnow().isoformat() + "Z",
                "county_fips":     "__state__",
            }

            # Cache to MongoDB
            try:
                db = await _db()
                from db import Collections
                await db[Collections.RISK_CACHE].replace_one(
                    {"state_abbr": state, "county_fips": "__state__"},
                    doc,
                    upsert=True,
                )
            except Exception as e:
                logger.warning("MongoDB cache write failed: %s", e)

            doc.pop("county_fips", None)
            results.append(doc)

        except Exception as e:
            logger.error("State FPI failed for %s: %s", region.id, e)
            results.append({
                "state_abbr": region.id.upper(),
                "state_name": region.display_name,
                "risk_score": 30,
                "trigger": "prepared",
                "error": str(e),
            })

    results.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    return {
        "count": len(results),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "states": results,
    }


@router.get("/fpi/state/{state_abbr}", tags=["fpi"])
async def get_state_fpi(
    state_abbr: str,
    refresh: bool = Query(False),
):
    """Full state FPI with weather, Gemini weights, and recommended actions."""
    state = state_abbr.upper()
    try:
        get_region(state)
    except RegionNotFoundError:
        raise HTTPException(404, f"Unknown state: {state_abbr}")

    if not refresh:
        try:
            db = await _db()
            from db import Collections
            cached = await db[Collections.RISK_CACHE].find_one(
                {"state_abbr": state, "county_fips": "__state_full__"},
                sort=[("cached_at", -1)]
            )
            if cached:
                cached.pop("_id", None)
                return cached
        except Exception:
            pass

    state_name = _STATE_NAMES.get(state, state)
    weather    = _weather(state)
    vuln       = _STATE_VULN_BASELINE.get(state, _DEFAULT_VULN)

    # Get FEMA active declarations for this state
    fema_count = 0
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent / "backend"))
        import fema as fema_mod
        fema_disasters = fema_mod.fetch_fema_disasters(state)
        fema_count = len(fema_disasters)
    except Exception as e:
        logger.warning("FEMA fetch failed: %s", e)

    shock = weather.get("shock_score", 20.0)
    vuln_score = (
        vuln["poverty_pct"] * 0.35 +
        vuln["food_insecurity_pct"] * 0.35 +
        vuln["no_vehicle_pct"] * 0.15 +
        vuln["svi_score"] * 0.15
    )
    # county_proxy = [{"score": shock * 0.4 + vuln_score * 0.6, "trigger": "watch", "population": 1000000}]

    # scored = _score_state(state, state_name, weather, county_proxy, fema_count=fema_count)
    from db import Collections
    db_handle = await _db()

    # Pull any cached county scores for this state from MongoDB
    county_summaries = []
    try:
        cursor = db_handle[Collections.RISK_CACHE].find(
            {"state_abbr": state, "county_fips": {"$nin": ["__state__", "__state_full__"]}}
        )
        async for doc in cursor:
            county_summaries.append({
                "score":      doc.get("risk_score", 30),
                "trigger":    doc.get("trigger", "prepared"),
                "population": 50000,
                "fips":       doc.get("county_fips"),
            })
    except Exception as e:
        logger.warning("County cache lookup failed: %s", e)

    # Fall back to the proxy if no counties cached yet
    # if not county_summaries:
    #     county_summaries = [{"score": shock * 0.4 + vuln_score * 0.6,
    #                         "trigger": "watch", "population": 1000000}]
    if not county_summaries:
        county_summaries = [{
            "shock_score":    round(shock, 1),
            "vulnerability":  round(vuln_score, 1),
            "supply_gap":     50,
            "readiness_gap":  50,
            "trigger":        "watch",
            "population":     1_000_000,
        }]

    scored = _score_state(state, state_name, weather, county_summaries, fema_count=fema_count)

    doc = {
        "state_abbr":         state,
        "state_name":         state_name,
        "risk_score":         scored.get("state_risk_score", 30),
        "trigger":            scored.get("trigger", "prepared"),
        "dominant_driver":    scored.get("dominant_driver", "vulnerability"),
        "state_weights":      scored.get("state_weights", {}),
        "top_factors":        scored.get("top_factors", []),
        "reasoning":          scored.get("reasoning", ""),
        "recommended_actions":scored.get("recommended_actions", []),
        "weather":            weather,
        "vulnerability":      vuln,
        "fema_declarations":  fema_count,
        "gemini_source":      scored.get("_source", "deterministic"),
        "cached_at":          datetime.datetime.utcnow().isoformat() + "Z",
        "county_fips":        "__state_full__",
    }

    try:
        db = await _db()
        from db import Collections
        await db[Collections.RISK_CACHE].replace_one(
            {"state_abbr": state, "county_fips": "__state_full__"},
            doc, upsert=True,
        )
        # Log alert if elevated
        if doc["trigger"] in ("warning", "action", "critical"):
            await db[Collections.ALERTS_LOG].insert_one({
                **{k: v for k, v in doc.items() if k != "_id"},
                "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                "level": doc["trigger"].capitalize(),
            })
    except Exception as e:
        logger.warning("MongoDB write failed: %s", e)

    doc.pop("county_fips", None)
    return doc


@router.get("/fpi/county/{state_abbr}/{county_fips}", tags=["fpi"])
async def get_county_fpi(
    state_abbr: str,
    county_fips: str,
    county_name: str = Query("", description="County name for Gemini prompt context"),
    refresh: bool = Query(False),
):
    """Full county FPI with Gemini-derived weights."""
    state = state_abbr.upper()

    if not refresh:
        try:
            db = await _db()
            from db import Collections
            cached = await db[Collections.RISK_CACHE].find_one(
                {"state_abbr": state, "county_fips": county_fips},
                sort=[("cached_at", -1)]
            )
            if cached:
                cached.pop("_id", None)
                return cached
        except Exception:
            pass

    state_name = _STATE_NAMES.get(state, state)
    weather    = _county_weather(state, county_fips)
    vuln       = _STATE_VULN_BASELINE.get(state, _DEFAULT_VULN)

    supply   = {"food_access_score": 50, "retailer_density": "moderate"}
    readiness= {"stock_level": 50, "voucher_capacity": "moderate"}

    name = county_name or f"County {county_fips}"
    scored = _score_county(state, state_name, county_fips, name, weather, vuln, supply, readiness)

    doc = {
        "state_abbr":       state,
        "county_fips":      county_fips,
        "county_name":      name,
        "risk_score":       scored["risk_score"],
        "trigger":          scored["trigger"],
        "weights":          scored["weights"],
        "top_factors":      scored["top_factors"],
        "reasoning":        scored["reasoning"],
        "weight_rationale": scored.get("weight_rationale", ""),
        "weather":          weather,
        "vulnerability":    vuln,
        "gemini_source":    scored.get("_source", "deterministic"),
        "cached_at":        datetime.datetime.utcnow().isoformat() + "Z",
    }

    try:
        db = await _db()
        from db import Collections
        await db[Collections.RISK_CACHE].replace_one(
            {"state_abbr": state, "county_fips": county_fips},
            doc, upsert=True,
        )
    except Exception as e:
        logger.warning("MongoDB county cache write failed: %s", e)

    return doc


# ---------------------------------------------------------------------------
# User onboarding endpoints
# ---------------------------------------------------------------------------

@router.post("/users/register", tags=["users"], status_code=201)
async def register_user(req: UserRegisterRequest):
    """
    Onboard a new user to the platform.
    Stores in MongoDB users collection.
    Returns the created user document (minus _id).
    """
    try:
        db = await _db()
        from db import Collections, new_user
        doc = new_user(
            email=req.email,
            name=req.name,
            role=req.role,
            state_abbr=req.state_abbr,
            county_fips=req.county_fips,
            org_name=req.org_name,
            phone=req.phone,
        )
        result = await db[Collections.USERS].insert_one(doc)
        doc.pop("_id", None)
        doc["id"] = str(result.inserted_id)
        return {"status": "created", "user": doc}
    except Exception as e:
        if "duplicate" in str(e).lower() or "E11000" in str(e):
            raise HTTPException(409, f"Email already registered: {req.email}")
        logger.error("User registration failed: %s", e)
        raise HTTPException(500, str(e))


@router.get("/users/{email}", tags=["users"])
async def get_user(email: str):
    """Look up a registered user by email."""
    try:
        db = await _db()
        from db import Collections
        user = await db[Collections.USERS].find_one({"email": email.lower().strip()})
        if not user:
            raise HTTPException(404, f"User not found: {email}")
        user.pop("_id", None)
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/users", tags=["users"])
async def list_users(
    state_abbr: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """List registered users (admin use). Filter by state or role."""
    try:
        db = await _db()
        from db import Collections
        query: dict = {}
        if state_abbr:
            query["state_abbr"] = state_abbr.upper()
        if role:
            query["role"] = role
        cursor = db[Collections.USERS].find(query).limit(limit)
        users = []
        async for user in cursor:
            user.pop("_id", None)
            users.append(user)
        return {"count": len(users), "users": users}
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Community signal reports
# ---------------------------------------------------------------------------

@router.post("/signals", tags=["signals"], status_code=201)
async def submit_signal(req: SignalReportRequest):
    """Submit a community ground-truth signal report."""
    import hashlib, time
    fingerprint = req.reporter_fingerprint or hashlib.sha256(
        f"anon-{time.time()}".encode()
    ).hexdigest()[:12]

    try:
        db = await _db()
        from db import Collections, new_signal_report
        doc = new_signal_report(
            state_abbr=req.state_abbr,
            county_fips=req.county_fips,
            category=req.category,
            severity=req.severity,
            description=req.description,
            reporter_fingerprint=fingerprint,
            zip_code=req.zip_code,
        )
        result = await db[Collections.SIGNAL_REPORTS].insert_one(doc)
        doc.pop("_id", None)
        doc["id"] = str(result.inserted_id)
        return {"status": "submitted", "signal": doc}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/signals/{state_abbr}", tags=["signals"])
async def get_signals(
    state_abbr: str,
    county_fips: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Get community signal reports for a state or county."""
    try:
        db = await _db()
        from db import Collections
        query: dict = {"state_abbr": state_abbr.upper()}
        if county_fips:
            query["county_fips"] = county_fips
        cursor = db[Collections.SIGNAL_REPORTS].find(query).sort("created_at", -1).limit(limit)
        reports = []
        async for r in cursor:
            r.pop("_id", None)
            r["created_at"] = str(r["created_at"])
            reports.append(r)
        return {"count": len(reports), "reports": reports}
    except Exception as e:
        raise HTTPException(500, str(e))


# Importing Optional at module level
from typing import Optional