"""
Crop Health + Alerts API — unified entry point.

Endpoints
---------
Builder 1 (Peyton):
  GET  /                              health check
  GET  /api/regions                   cached region IDs
  GET  /api/crop-health/{region_id}   latest cached crop analysis
  POST /api/analyze                   run a fresh crop analysis

Builder 3 (you):
  GET  /api/alerts                    all active alerts (all communities)
  GET  /api/alerts/{community_id}     single-community alert
  GET  /api/risk                      risk scores for all communities
  GET  /api/risk/{community_id}       risk breakdown for one community
  POST /api/alerts/refresh            force re-score all communities

  GET  /api/disruptions/{region_id}   unified disruption feed (NOAA + FEMA + routes)

Usage
-----
  python start_server.py
  Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make backend/ importable (for fema, noaa, routes)
_backend = Path(__file__).parent / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

# Make project root importable (for risk_engine, alert_logic)
_root = Path(__file__).parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import datetime
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from crop_health import (
    LOUISIANA_BBOX,
    LOUISIANA_REGION_ID,
    ANOMALY_WARNING_PCT,
    ANOMALY_CRITICAL_PCT,
    detect_ndvi_anomaly,
    get_ndvi_observation,
    get_drought_status,
)

# Builder 3 routers
from backend.alerts_api import router as alerts_router
from backend.disruptions_api import router as disruptions_router

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RootBridge — Crop Health & Food Security API",
    description=(
        "Louisiana food-supply risk platform.\n\n"
        "**Builder 1**: crop health (NDVI + drought) via NASA LANCE + SMAP.\n"
        "**Builder 3**: composite risk scoring, graduated alerts, supply-corridor analysis.\n\n"
        "Quick demo flow:\n"
        "1. `POST /api/analyze` with `fast_mode=true` to seed crop cache (~30 s).\n"
        "2. `GET /api/alerts` to see active food-security alerts.\n"
        "3. `GET /api/risk` to see per-community risk breakdowns.\n"
    ),
    version="1.0.0",
)

# Allow Builder 4's frontend to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mount Builder 3 routers
# ---------------------------------------------------------------------------
app.include_router(alerts_router, prefix="/api")
app.include_router(disruptions_router, prefix="/api")

# ---------------------------------------------------------------------------
# In-memory store (Builder 1 crop-health cache)
# ---------------------------------------------------------------------------

_store: Dict[str, Dict[str, Any]] = {}
_running: set[str] = set()
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    region_id: str = Field(LOUISIANA_REGION_ID)
    bbox: Optional[List[float]] = Field(None, min_length=4, max_length=4)
    date: Optional[str] = Field(None)
    baseline_years: Optional[List[int]] = Field(None)
    n_samples: int = Field(9, ge=1, le=64)
    include_drought: bool = Field(True)
    fast_mode: bool = Field(
        False,
        description="Skip baseline curve fitting — much faster, good for demos.",
    )


# ---------------------------------------------------------------------------
# Helpers (unchanged from original api.py)
# ---------------------------------------------------------------------------

def _summarise(entry: Dict[str, Any]) -> Dict[str, Any]:
    anomaly = entry.get("anomaly", {})
    obs     = entry.get("ndvi_observation", {})
    drought = entry.get("drought", {})

    alert = anomaly.get("alert") or "data_unavailable"
    color = {"normal": "green", "warning": "yellow", "critical": "red"}.get(alert, "grey")

    summary = {
        "alert":              alert,
        "color":              color,
        "ndvi_current":       obs.get("ndvi_current"),
        "ndvi_deviation_pct": obs.get("deviation_pct"),
        "ndvi_status":        obs.get("status"),
        "drought_status":     drought.get("status") if drought else None,
        "source":             obs.get("source"),
        "confidence":         anomaly.get("confidence"),
        "cached_at":          entry.get("cached_at"),
        "analysis_duration_s":entry.get("duration_s"),
    }
    return {**entry, "summary": summary}


def _run_analysis(
    region_id: str,
    bbox: tuple,
    date: str,
    baseline_years: Optional[List[int]],
    n_samples: int,
    include_drought: bool,
    fast_mode: bool,
) -> Dict[str, Any]:
    t0 = time.monotonic()

    if fast_mode:
        observation = get_ndvi_observation(
            region_bbox=bbox, date=date,
            region_id=region_id, n_samples=n_samples,
        )
        anomaly: Dict[str, Any] = {
            "region_id": region_id, "date": date,
            "alert": "data_unavailable",
            "note": "fast_mode=true — run with fast_mode=false for full anomaly detection.",
        }
    else:
        anomaly = detect_ndvi_anomaly(
            region_bbox=bbox, date=date, region_id=region_id,
            baseline_years=baseline_years, n_samples=n_samples,
        )
        observation = get_ndvi_observation(
            region_bbox=bbox, date=date,
            region_id=region_id, n_samples=n_samples,
        )

    drought = None
    if include_drought:
        drought = get_drought_status(region_bbox=bbox, date=date, n_samples=n_samples)

    return {
        "region_id": region_id,
        "cached_at": datetime.datetime.utcnow().isoformat() + "Z",
        "duration_s": round(time.monotonic() - t0, 1),
        "anomaly": anomaly,
        "ndvi_observation": observation,
        "drought": drought,
    }


# ---------------------------------------------------------------------------
# Builder 1 routes (unchanged)
# ---------------------------------------------------------------------------

@app.get("/", tags=["meta"])
def root():
    return {
        "service": "rootbridge-api",
        "status": "ok",
        "docs": "/docs",
        "builder1_endpoints": {
            "crop_health": "GET /api/crop-health/{region_id}",
            "analyze":     "POST /api/analyze",
            "regions":     "GET /api/regions",
        },
        "builder3_endpoints": {
            "alerts":       "GET /api/alerts",
            "community_alert": "GET /api/alerts/{community_id}",
            "risk_all":     "GET /api/risk",
            "risk_one":     "GET /api/risk/{community_id}",
            "refresh":      "POST /api/alerts/refresh",
            "disruptions":  "GET /api/disruptions/{region_id}",
        },
        "default_region": LOUISIANA_REGION_ID,
        "thresholds": {
            "warning_pct":  ANOMALY_WARNING_PCT,
            "critical_pct": ANOMALY_CRITICAL_PCT,
            "alert_watch":   40,
            "alert_warning": 60,
            "alert_action":  80,
        },
    }


@app.get("/api/regions", tags=["meta"])
def list_regions():
    with _lock:
        regions = [
            {
                "region_id": rid,
                "cached_at": v["cached_at"],
                "alert":     v.get("anomaly", {}).get("alert", "unknown"),
                "duration_s":v.get("duration_s"),
            }
            for rid, v in _store.items()
        ]
    return {"count": len(regions), "regions": regions}


@app.get("/api/crop-health/{region_id}", tags=["health"])
def get_crop_health(region_id: str):
    with _lock:
        is_running = region_id in _running
        entry = _store.get(region_id)

    if is_running and entry is None:
        raise HTTPException(
            status_code=202,
            detail=f"Analysis for '{region_id}' is currently running.",
        )
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No cached analysis for '{region_id}'. "
                f"POST /api/analyze to run one."
            ),
        )
    return _summarise(entry)


@app.post("/api/analyze", tags=["health"], status_code=200)
def run_analysis(req: AnalyzeRequest):
    region_id = req.region_id
    with _lock:
        if region_id in _running:
            raise HTTPException(
                status_code=409,
                detail=f"Analysis for '{region_id}' is already running.",
            )
        _running.add(region_id)

    try:
        bbox = tuple(req.bbox) if req.bbox else LOUISIANA_BBOX
        date = req.date or str(datetime.date.today())

        result = _run_analysis(
            region_id=region_id,
            bbox=bbox,
            date=date,
            baseline_years=req.baseline_years,
            n_samples=req.n_samples,
            include_drought=req.include_drought,
            fast_mode=req.fast_mode,
        )
        with _lock:
            _store[region_id] = result
        return _summarise(result)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        with _lock:
            _running.discard(region_id)