"""
Alerts API router — Builder 3

Mounts under /api in the main FastAPI app (api.py).
Provides:
  GET  /api/alerts                     list all active alerts (all communities)
  GET  /api/alerts/{community_id}      single-community alert
  GET  /api/risk/{community_id}        raw risk score breakdown
  GET  /api/risk                       risk scores for all communities
  POST /api/alerts/refresh             re-score all communities and cache results

All responses are JSON.  The router fetches live data from Builder 1 + 2 and
never caches results longer than the TTL configured in ALERT_CACHE_TTL_SECONDS.

Author: Builder 3
"""

from __future__ import annotations

import datetime
import logging
import os
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import risk_engine
import alert_logic
from risk_engine import RiskScore, compute_risk, compute_all_risks
from alert_logic import Alert, generate_alert, generate_all_alerts, filter_active_alerts

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
CACHE_TTL = int(os.getenv("ALERT_CACHE_TTL_SECONDS", "300"))  # 5 min default

# @dataclass_workaround = {}  # populated by _CacheEntry below — just a comment marker

class _CacheEntry:
    def __init__(self, alert: Alert, risk: RiskScore):
        self.alert = alert
        self.risk  = risk
        self.ts    = datetime.datetime.utcnow()

    def is_fresh(self) -> bool:
        age = (datetime.datetime.utcnow() - self.ts).total_seconds()
        return age < CACHE_TTL


_cache: dict[str, _CacheEntry] = {}
_cache_lock = threading.Lock()
_refresh_running = False


def _get_or_compute(community_id: str) -> _CacheEntry:
    with _cache_lock:
        entry = _cache.get(community_id)
        if entry and entry.is_fresh():
            return entry

    risk   = compute_risk(community_id)
    alert  = generate_alert(risk)
    entry  = _CacheEntry(alert, risk)
    with _cache_lock:
        _cache[community_id] = entry
    return entry


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/alerts", summary="All active alerts", tags=["alerts"])
def get_all_alerts(
    min_level: str = Query(
        "Watch",
        description="Minimum alert level to return: Watch | Warning | Action",
        regex="^(Watch|Warning|Action)$",
    ),
    include_low_risk: bool = Query(
        False,
        description="Also return communities with no active alert (score < 40)",
    ),
) -> dict[str, Any]:
    """
    Return alerts for every community in supply_corridors.json.

    Communities are returned sorted by risk score (highest first).
    Use `min_level` to filter — e.g. `min_level=Action` returns only Action alerts.
    Set `include_low_risk=true` to include below-threshold communities for dashboard use.
    """
    community_ids = risk_engine.get_all_community_ids()

    alerts = []
    for cid in community_ids:
        try:
            entry = _get_or_compute(cid)
            alerts.append(entry.alert)
        except Exception as e:
            logger.error("Failed to score %s: %s", cid, e)

    level_rank = {"Action": 3, "Warning": 2, "Watch": 1, None: 0}
    min_rank   = level_rank.get(min_level, 1)

    filtered = [
        a for a in alerts
        if (level_rank.get(a.level, 0) >= min_rank)
        or (include_low_risk and a.level is None)
    ]
    filtered.sort(key=lambda a: a.risk_score, reverse=True)

    return {
        "count": len(filtered),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "alerts": [a.to_dict() for a in filtered],
    }


@router.get("/alerts/{community_id}", summary="Single community alert", tags=["alerts"])
def get_community_alert(community_id: str) -> dict[str, Any]:
    """
    Return the current alert for a single community.

    Returns 404 if the community_id is not found in supply_corridors.json.
    """
    try:
        entry = _get_or_compute(community_id)
    except KeyError:
        known = risk_engine.get_all_community_ids()
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Community '{community_id}' not found in supply corridors.",
                "known_communities": known,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return entry.alert.to_dict()


@router.get("/risk", summary="Risk scores for all communities", tags=["risk"])
def get_all_risks() -> dict[str, Any]:
    """
    Return raw composite risk scores and component breakdowns for every community.
    Useful for dashboard rendering and sorting.
    """
    community_ids = risk_engine.get_all_community_ids()
    results = []
    for cid in community_ids:
        try:
            entry = _get_or_compute(cid)
            r = entry.risk
            results.append({
                "community_id":   r.community_id,
                "community_name": r.community_name,
                "corridor_id":    r.corridor_id,
                "risk_score":     r.risk_score,
                "data_quality":   r.data_quality,
                "components": {
                    "crop_health":             r.components.crop_health,
                    "disruption":              r.components.disruption,
                    "corridor_dependency":     r.components.corridor_dependency,
                    "community_vulnerability": r.components.community_vulnerability,
                },
                "top_factors": r.top_factors,
            })
        except Exception as e:
            logger.error("Risk fetch failed for %s: %s", cid, e)

    results.sort(key=lambda x: x["risk_score"], reverse=True)
    return {
        "count": len(results),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "communities": results,
    }


@router.get("/risk/{community_id}", summary="Risk breakdown for one community", tags=["risk"])
def get_community_risk(community_id: str) -> dict[str, Any]:
    """
    Return the full risk breakdown for a single community including raw
    payloads from Builder 1 (crop health) and Builder 2 (disruptions).
    """
    try:
        entry = _get_or_compute(community_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Community '{community_id}' not found.",
        )
    r = entry.risk
    return r.to_dict()


class RefreshRequest(BaseModel):
    community_ids: list[str] | None = None  # None → refresh all


@router.post("/alerts/refresh", summary="Force re-score all communities", tags=["alerts"])
def refresh_alerts(req: RefreshRequest | None = None) -> dict[str, Any]:
    """
    Invalidate the cache and re-compute risk scores.

    Pass `community_ids` to refresh only specific communities; omit to refresh all.
    Runs synchronously — expect 5–15 seconds for a full refresh depending on
    Builder 1 / Builder 2 latency.
    """
    global _refresh_running
    with _cache_lock:
        if _refresh_running:
            raise HTTPException(
                status_code=409,
                detail="A refresh is already running. Try again in a moment.",
            )
        _refresh_running = True

    try:
        ids_to_refresh = (
            req.community_ids if req and req.community_ids
            else risk_engine.get_all_community_ids()
        )

        with _cache_lock:
            for cid in ids_to_refresh:
                _cache.pop(cid, None)

        refreshed = []
        for cid in ids_to_refresh:
            try:
                entry = _get_or_compute(cid)
                refreshed.append({
                    "community_id": cid,
                    "risk_score":   entry.risk.risk_score,
                    "level":        entry.alert.level,
                    "data_quality": entry.risk.data_quality,
                })
            except Exception as e:
                logger.error("Refresh failed for %s: %s", cid, e)

        refreshed.sort(key=lambda x: x["risk_score"], reverse=True)
        return {
            "refreshed": len(refreshed),
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "communities": refreshed,
        }

    finally:
        with _cache_lock:
            _refresh_running = False