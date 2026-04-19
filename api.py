"""
api.py — RootBridge unified API entry point

All endpoints:

Builder 1 (crop health):
  GET  /api/crop-health/{region_id}
  POST /api/analyze
  GET  /api/regions

Builder 3 (alerts + disruptions):
  GET  /api/alerts
  GET  /api/alerts/{community_id}
  GET  /api/risk
  GET  /api/risk/{community_id}
  POST /api/alerts/refresh
  GET  /api/disruptions/{region_id}

State FPI (new — all 50 states):
  GET  /api/fpi/states                         national map data
  GET  /api/fpi/state/{state_abbr}             full state FPI + Gemini weights
  GET  /api/fpi/county/{state_abbr}/{fips}     county FPI + Gemini weights
  GET  /api/weather/{state_abbr}               real-time NASA/NOAA weather

Users + signals (MongoDB):
  POST /api/users/register
  GET  /api/users/{email}
  GET  /api/users
  POST /api/signals
  GET  /api/signals/{state_abbr}
"""
from __future__ import annotations

import sys
import datetime
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Path setup
_root    = Path(__file__).parent
_backend = _root / "backend"
for p in (str(_root), str(_backend)):
    if p not in sys.path:
        sys.path.insert(0, p)

from crop_health import (
    LOUISIANA_BBOX, LOUISIANA_REGION_ID,
    ANOMALY_WARNING_PCT, ANOMALY_CRITICAL_PCT,
    detect_ndvi_anomaly, get_ndvi_observation, get_drought_status,
)
from backend.alerts_api      import router as alerts_router
from backend.disruptions_api import router as disruptions_router
from state_fpi_api           import router as fpi_router
from community_requests_api import router as requests_router
from db                      import close_db

app = FastAPI(
    title="RootBridge API",
    description="Food security risk platform — all 50 US states.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers
app.include_router(alerts_router,      prefix="/api")
app.include_router(disruptions_router, prefix="/api")
app.include_router(fpi_router,         prefix="/api")
app.include_router(requests_router, prefix="/api")


@app.on_event("shutdown")
async def shutdown():
    await close_db()


# ---------------------------------------------------------------------------
# In-memory crop-health store (Builder 1)
# ---------------------------------------------------------------------------
_store:   Dict[str, Dict[str, Any]] = {}
_running: set[str] = set()
_lock   = threading.Lock()

# State bboxes for all 50 states
_STATE_BBOXES: Dict[str, tuple] = {
    "AL": (-88.47, 30.14, -84.89, 35.01), "AK": (-179.99, 51.21, -129.99, 71.35),
    "AZ": (-114.82, 31.33, -109.04, 37.00), "AR": (-94.62, 33.00, -89.64, 36.50),
    "CA": (-124.41, 32.53, -114.13, 42.01), "CO": (-109.06, 36.99, -102.04, 41.00),
    "CT": (-73.73, 40.95, -71.79, 42.05), "DE": (-75.79, 38.45, -75.05, 39.84),
    "FL": (-87.63, 24.52, -80.03, 31.00), "GA": (-85.61, 30.36, -80.84, 35.00),
    "HI": (-160.25, 18.91, -154.81, 22.24), "ID": (-117.24, 41.99, -111.04, 49.00),
    "IL": (-91.51, 36.97, -87.49, 42.51), "IN": (-88.10, 37.77, -84.78, 41.77),
    "IA": (-96.64, 40.37, -90.14, 43.50), "KS": (-102.05, 36.99, -94.59, 40.00),
    "KY": (-89.57, 36.50, -81.96, 39.15), "LA": (-94.04, 28.93, -88.82, 33.02),
    "ME": (-71.08, 43.06, -66.95, 47.46), "MD": (-79.49, 37.89, -75.05, 39.72),
    "MA": (-73.51, 41.24, -69.93, 42.89), "MI": (-90.42, 41.70, -82.41, 48.19),
    "MN": (-97.24, 43.50, -89.49, 49.38), "MS": (-91.65, 30.17, -88.10, 35.01),
    "MO": (-95.77, 35.99, -89.10, 40.61), "MT": (-116.05, 44.36, -104.04, 49.00),
    "NE": (-104.05, 39.99, -95.31, 43.00), "NV": (-120.00, 35.00, -114.03, 42.00),
    "NH": (-72.56, 42.70, -70.70, 45.31), "NJ": (-75.56, 38.93, -73.89, 41.36),
    "NM": (-109.05, 31.33, -103.00, 37.00), "NY": (-79.76, 40.50, -71.86, 45.01),
    "NC": (-84.32, 33.84, -75.46, 36.59), "ND": (-104.05, 45.93, -96.55, 49.00),
    "OH": (-84.82, 38.40, -80.52, 42.00), "OK": (-103.00, 33.62, -94.43, 37.00),
    "OR": (-124.57, 41.99, -116.46, 46.26), "PA": (-80.52, 39.72, -74.69, 42.27),
    "RI": (-71.86, 41.15, -71.12, 42.02), "SC": (-83.35, 32.05, -78.54, 35.21),
    "SD": (-104.06, 42.48, -96.44, 45.94), "TN": (-90.31, 34.98, -81.65, 36.68),
    "TX": (-106.65, 25.84, -93.51, 36.50), "UT": (-114.05, 37.00, -109.04, 42.00),
    "VT": (-73.44, 42.73, -71.46, 45.02), "VA": (-83.68, 36.54, -75.24, 39.47),
    "WA": (-124.73, 45.54, -116.92, 49.00), "WV": (-82.64, 37.20, -77.72, 40.64),
    "WI": (-92.89, 42.49, -86.25, 47.08), "WY": (-111.06, 40.99, -104.05, 45.01),
    "DC": (-77.12, 38.79, -76.91, 38.99),
}


class AnalyzeRequest(BaseModel):
    region_id: str = Field(LOUISIANA_REGION_ID)
    state_abbr: Optional[str] = Field(None, description="Two-letter state code. If provided, bbox is derived automatically.")
    bbox: Optional[List[float]] = Field(None, min_length=4, max_length=4)
    date: Optional[str] = None
    baseline_years: Optional[List[int]] = None
    n_samples: int = Field(9, ge=1, le=64)
    include_drought: bool = True
    fast_mode: bool = Field(False, description="Skip baseline fitting — faster for demos.")


def _summarise(entry: Dict[str, Any]) -> Dict[str, Any]:
    anomaly = entry.get("anomaly", {})
    obs     = entry.get("ndvi_observation", {})
    drought = entry.get("drought", {})
    alert   = anomaly.get("alert") or "data_unavailable"
    summary = {
        "alert":              alert,
        "color":              {"normal": "green", "warning": "yellow", "critical": "red"}.get(alert, "grey"),
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


def _run_analysis(region_id, bbox, date, baseline_years, n_samples, include_drought, fast_mode):
    t0 = time.monotonic()
    if fast_mode:
        observation = get_ndvi_observation(region_bbox=bbox, date=date, region_id=region_id, n_samples=n_samples)
        anomaly = {"region_id": region_id, "date": date, "alert": "data_unavailable",
                   "note": "fast_mode=true — use fast_mode=false for full anomaly detection."}
    else:
        anomaly     = detect_ndvi_anomaly(region_bbox=bbox, date=date, region_id=region_id,
                                          baseline_years=baseline_years, n_samples=n_samples)
        observation = get_ndvi_observation(region_bbox=bbox, date=date, region_id=region_id, n_samples=n_samples)
    drought = get_drought_status(region_bbox=bbox, date=date, n_samples=n_samples) if include_drought else None
    return {
        "region_id": region_id,
        "cached_at": datetime.datetime.utcnow().isoformat() + "Z",
        "duration_s": round(time.monotonic() - t0, 1),
        "anomaly": anomaly,
        "ndvi_observation": observation,
        "drought": drought,
    }


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "rootbridge-api",
        "version": "2.0.0",
        "status":  "ok",
        "docs":    "/docs",
        "coverage": "all 50 US states",
        "new_endpoints": {
            "national_map": "GET /api/fpi/states",
            "state_fpi":    "GET /api/fpi/state/{state_abbr}",
            "county_fpi":   "GET /api/fpi/county/{state_abbr}/{county_fips}",
            "weather":      "GET /api/weather/{state_abbr}",
            "register":     "POST /api/users/register",
            "signals":      "POST /api/signals",
        },
    }


@app.get("/api/regions", tags=["meta"])
def list_regions_endpoint():
    with _lock:
        regions = [
            {"region_id": rid, "cached_at": v["cached_at"],
             "alert": v.get("anomaly", {}).get("alert", "unknown")}
            for rid, v in _store.items()
        ]
    return {"count": len(regions), "regions": regions}


@app.get("/api/crop-health/{region_id}", tags=["health"])
def get_crop_health(region_id: str):
    with _lock:
        is_running = region_id in _running
        entry = _store.get(region_id)
    if is_running and entry is None:
        raise HTTPException(202, f"Analysis for '{region_id}' is running.")
    if entry is None:
        raise HTTPException(404, f"No cached analysis for '{region_id}'. POST /api/analyze first.")
    return _summarise(entry)


@app.post("/api/analyze", tags=["health"], status_code=200)
def run_analysis(req: AnalyzeRequest):
    region_id = req.region_id

    # Derive bbox from state_abbr if provided
    if req.state_abbr and not req.bbox:
        state = req.state_abbr.upper()
        if state in _STATE_BBOXES:
            bbox = _STATE_BBOXES[state]
            region_id = region_id or state.lower()
        else:
            raise HTTPException(404, f"Unknown state: {req.state_abbr}")
    elif req.bbox:
        bbox = tuple(req.bbox)
    else:
        bbox = LOUISIANA_BBOX

    with _lock:
        if region_id in _running:
            raise HTTPException(409, f"Analysis for '{region_id}' is already running.")
        _running.add(region_id)

    try:
        date = req.date or str(datetime.date.today())
        result = _run_analysis(region_id, bbox, date, req.baseline_years,
                               req.n_samples, req.include_drought, req.fast_mode)
        with _lock:
            _store[region_id] = result
        return _summarise(result)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    finally:
        with _lock:
            _running.discard(region_id)


# ---------------------------------------------------------------------------
# Serve React SPA (must come after all API routes)
# ---------------------------------------------------------------------------

_dist = Path(__file__).parent / "rootbridge-project" / "dist"

if _dist.exists():
    _assets = _dist / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        file = _dist / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(_dist / "index.html")