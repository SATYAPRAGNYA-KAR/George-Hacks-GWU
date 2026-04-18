"""
Crop Health API — Louisiana focus, extensible to any region.

Endpoints
---------
GET  /                              health check + link to docs
GET  /api/regions                   list all cached region IDs
GET  /api/crop-health/{region_id}   return latest cached analysis for a region
POST /api/analyze                   run a fresh analysis and cache the result

Usage
-----
Start:  uvicorn api:app --host 0.0.0.0 --port 8000
Docs:   http://localhost:8000/docs
"""
from __future__ import annotations

import datetime
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
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

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Crop Health API",
    description=(
        "NDVI phenology + SMAP drought analysis for Louisiana (and any region).\n\n"
        "**Quick demo**\n"
        "1. `POST /api/analyze` with `fast_mode=true` to seed the cache (~30 s).\n"
        "2. `GET /api/crop-health/louisiana` to retrieve the result.\n\n"
        "Full analysis (`fast_mode=false`) runs the 5-year double-logistic baseline "
        "and takes several minutes depending on WPS latency."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# In-memory store  { region_id: { ...result, cached_at, duration_s } }
# ---------------------------------------------------------------------------

_store: Dict[str, Dict[str, Any]] = {}
_running: set[str] = set()
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    region_id: str = Field(
        LOUISIANA_REGION_ID,
        description="Label stored in the cache and returned in every response.",
    )
    bbox: Optional[List[float]] = Field(
        None,
        description=(
            "[min_lon, min_lat, max_lon, max_lat] WGS84. "
            "Omit to use the Louisiana state extent."
        ),
        min_length=4,
        max_length=4,
    )
    date: Optional[str] = Field(
        None,
        description="Observation date YYYY-MM-DD. Omit to use today.",
    )
    baseline_years: Optional[List[int]] = Field(
        None,
        description=(
            "Explicit list of years for the climatological baseline. "
            "Omit to use the 5 years immediately before the observation year."
        ),
    )
    n_samples: int = Field(
        9,
        ge=1,
        le=64,
        description="Number of grid points sampled inside the bbox per API call.",
    )
    include_drought: bool = Field(
        True,
        description="Also run the SMAP soil-moisture drought analysis.",
    )
    fast_mode: bool = Field(
        False,
        description=(
            "When true, skip the full double-logistic baseline computation and "
            "return only the NDVI observation + drought snapshot. "
            "Much faster (~30 s vs several minutes) — good for demos."
        ),
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarise(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Add a top-level `summary` block so the GET response is scannable at a glance."""
    anomaly = entry.get("anomaly", {})
    obs = entry.get("ndvi_observation", {})
    drought = entry.get("drought", {})

    alert = anomaly.get("alert") or "data_unavailable"
    color = {"normal": "green", "warning": "yellow", "critical": "red"}.get(alert, "grey")

    summary = {
        "alert": alert,
        "color": color,
        "ndvi_current": obs.get("ndvi_current"),
        "ndvi_deviation_pct": obs.get("deviation_pct"),
        "ndvi_status": obs.get("status"),
        "drought_status": drought.get("status") if drought else None,
        "source": obs.get("source"),
        "confidence": anomaly.get("confidence"),
        "cached_at": entry.get("cached_at"),
        "analysis_duration_s": entry.get("duration_s"),
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
        # Lightweight path: current NDVI observation only — no baseline curve fitting.
        observation = get_ndvi_observation(
            region_bbox=bbox,
            date=date,
            region_id=region_id,
            n_samples=n_samples,
        )
        anomaly: Dict[str, Any] = {
            "region_id": region_id,
            "date": date,
            "alert": "data_unavailable",
            "note": "fast_mode=true — run with fast_mode=false for full anomaly detection.",
        }
    else:
        anomaly = detect_ndvi_anomaly(
            region_bbox=bbox,
            date=date,
            region_id=region_id,
            baseline_years=baseline_years,
            n_samples=n_samples,
        )
        observation = get_ndvi_observation(
            region_bbox=bbox,
            date=date,
            region_id=region_id,
            n_samples=n_samples,
        )

    drought = None
    if include_drought:
        drought = get_drought_status(
            region_bbox=bbox,
            date=date,
            n_samples=n_samples,
        )

    duration = round(time.monotonic() - t0, 1)

    return {
        "region_id": region_id,
        "cached_at": datetime.datetime.utcnow().isoformat() + "Z",
        "duration_s": duration,
        "anomaly": anomaly,
        "ndvi_observation": observation,
        "drought": drought,
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", tags=["meta"])
def root():
    return {
        "service": "crop-health-api",
        "status": "ok",
        "docs": "/docs",
        "endpoints": {
            "health_check": "GET /api/crop-health/{region_id}",
            "analyze": "POST /api/analyze",
            "regions": "GET /api/regions",
        },
        "default_region": LOUISIANA_REGION_ID,
        "thresholds": {
            "warning_pct": ANOMALY_WARNING_PCT,
            "critical_pct": ANOMALY_CRITICAL_PCT,
        },
    }


@app.get("/api/regions", tags=["meta"])
def list_regions():
    """List all region IDs that have a cached analysis result."""
    with _lock:
        regions = [
            {
                "region_id": rid,
                "cached_at": v["cached_at"],
                "alert": v.get("anomaly", {}).get("alert", "unknown"),
                "duration_s": v.get("duration_s"),
            }
            for rid, v in _store.items()
        ]
    return {"count": len(regions), "regions": regions}


@app.get("/api/crop-health/{region_id}", tags=["health"])
def get_crop_health(region_id: str):
    """
    Return the latest cached analysis for a region.

    Run `POST /api/analyze` first to populate the cache.
    Returns **404** if no analysis has been run yet for this region.
    Returns **202** if an analysis is currently running.
    """
    with _lock:
        is_running = region_id in _running
        entry = _store.get(region_id)

    if is_running and entry is None:
        raise HTTPException(
            status_code=202,
            detail=f"Analysis for '{region_id}' is currently running — try again in a moment.",
        )
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No cached analysis found for region '{region_id}'. "
                f"POST /api/analyze with {{\"region_id\": \"{region_id}\"}} to run one."
            ),
        )

    return _summarise(entry)


@app.post("/api/analyze", tags=["health"], status_code=200)
def run_analysis(req: AnalyzeRequest):
    """
    Run a fresh crop-health analysis and cache the result.

    **fast_mode=false** (default): Full analysis — fits 5-year double-logistic baselines,
    computes DOY-curve and PeakNDVI anomalies, SMAP drought status.
    Expected duration: 2–8 minutes depending on WPS latency and `n_samples`.

    **fast_mode=true**: NDVI observation + drought snapshot only, no baseline curve fitting.
    Expected duration: ~30 seconds. Use this for live demos.

    The result is cached and immediately available via
    `GET /api/crop-health/{region_id}`.
    """
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
