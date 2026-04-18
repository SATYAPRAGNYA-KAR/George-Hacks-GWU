"""
Crop health and drought assessment via NDVI phenology (CSISS WPS) and SMAP soil moisture.
NDVI observations via NASA LANCE/MODIS (ORNL DAAC) with WPS fallback.

Primary focus: Louisiana (FIPS 22).  All functions accept any WGS84 bounding box,
so coverage can be expanded to other states by swapping the bbox argument.

Louisiana crop context
----------------------
Primary commodities: sugarcane, rice, cotton, soybeans, corn.
Growing season: rice/cotton Apr–Oct; sugarcane year-round harvest Nov–Jan;
soybeans May–Oct.  Drought risk is tied to Gulf moisture and hurricane-season
precipitation anomalies rather than Great-Plains dry patterns.

Quick-start (Louisiana defaults)
---------------------------------
    from crop_health import LOUISIANA_BBOX, get_crop_health, get_drought_status, get_ndvi_observation

    health  = get_crop_health(LOUISIANA_BBOX, "2024-07-15")
    drought = get_drought_status(LOUISIANA_BBOX, "2024-07-15")
    obs     = get_ndvi_observation(LOUISIANA_BBOX, "2024-07-15", region_id="louisiana")

Functions
---------
get_crop_health(region_bbox, date)    -> dict
get_drought_status(region_bbox, date) -> dict
get_ndvi_observation(region_bbox, date, region_id) -> dict  (LANCE primary, WPS fallback)

Both accept:
  region_bbox : (min_lon, min_lat, max_lon, max_lat) in WGS84
  date        : "YYYY-MM-DD" str or datetime.date

EARTHDATA_TOKEN env var enables MOD13Q1N (LANCE NRT); falls back to MOD13Q1 without it.
"""

import io
import os
import re
import time
import datetime
from typing import Optional, Tuple, Union

import numpy as np
import pandas as pd
import requests
from scipy.optimize import curve_fit
from scipy.signal import savgol_filter

# ---------------------------------------------------------------------------
# Service constants
# ---------------------------------------------------------------------------

_WPS_BASE = "https://cloud.csiss.gmu.edu/smap_service"
_NDVI_PRODUCT_ID = "NDVI-WEEKLY"
_SMAP_PRODUCT_ID = "SMAP-L4-SM"          # swap if the service uses a different ID
_DEFAULT_BASELINE_YEARS = list(range(2016, 2022))

# Anomaly detection thresholds (deviation from 5-year baseline mean)
ANOMALY_WARNING_PCT: float = -15.0   # ≤ this → "warning"
ANOMALY_CRITICAL_PCT: float = -30.0  # ≤ this → "critical"

# ---------------------------------------------------------------------------
# Louisiana defaults  (swap bbox to scale to any other region)
# ---------------------------------------------------------------------------

LOUISIANA_BBOX: tuple = (-94.04, 28.93, -88.82, 33.02)  # (min_lon, min_lat, max_lon, max_lat) WGS84
LOUISIANA_FIPS: str = "22"
LOUISIANA_REGION_ID: str = "louisiana"

# ---------------------------------------------------------------------------
# ORNL DAAC MODIS Web Service (NASA LANCE)
# ---------------------------------------------------------------------------

_ORNL_BASE = "https://modis.ornl.gov/rst/api/v1"
_LANCE_NRT_PRODUCT = "MOD13Q1N"   # LANCE near-real-time Terra NDVI 16-day 250 m
_LANCE_STABLE_PRODUCT = "MOD13Q1" # stable Terra NDVI — used for baseline years
_ORNL_NDVI_BAND = "250m_16_days_NDVI"
_ORNL_QA_BAND = "250m_16_days_pixel_reliability"
_ORNL_NDVI_SCALE = 0.0001          # raw integer × scale → NDVI (0–1)
_ORNL_NODATA = -28672

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(date: Union[str, datetime.date, datetime.datetime]) -> datetime.date:
    if isinstance(date, datetime.datetime):
        return date.date()
    if isinstance(date, str):
        return datetime.date.fromisoformat(date)
    return date


def _iso_week(d: datetime.date) -> int:
    return d.isocalendar()[1]


def _sample_grid_points(bbox: Tuple[float, float, float, float], n: int) -> list:
    """Return n points on a uniform grid within bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    side = int(np.ceil(np.sqrt(n)))
    lons = np.linspace(min_lon, max_lon, side)
    lats = np.linspace(min_lat, max_lat, side)
    return [(float(lon), float(lat)) for lon in lons for lat in lats]


def _wps_fetch_yearly_profile(product_id: str, lon: float, lat: float, year: int) -> Optional[np.ndarray]:
    """
    Fetch a 52-week time-series from the CSISS WPS endpoint.
    Returns a float array or None on failure.
    """
    url = (
        f"{_WPS_BASE}?service=WPS&version=1.0.0&request=Execute"
        f"&identifier=GetProfileByWeek"
        f"&DataInputs=productId={product_id};x={lon};y={lat}"
        f";startWeek={year}_01;endWeek={year}_52"
    )
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()

        # Response may link to a CSV or embed data inline
        match = re.search(r'(https?://[^\s<>\'"]+\.csv)', r.text)
        if match:
            csv_r = requests.get(match.group(1), timeout=60)
            csv_r.raise_for_status()
            df = pd.read_csv(io.StringIO(csv_r.text))
        elif "value" in r.text.lower() and "," in r.text:
            m = re.search(r'>\s*([^<]+,[^<]+)\s*<', r.text)
            if not m:
                return None
            df = pd.read_csv(io.StringIO(m.group(1).strip()))
        else:
            return None

        if df.empty or len(df.columns) < 2:
            return None

        time_like = {"week", "date", "time", "doy"}
        data_col = next(
            (c for c in df.columns if c.lower() not in time_like), df.columns[-1]
        )
        return df[data_col].values.astype(float)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# NASA LANCE / ORNL DAAC MODIS helpers
# ---------------------------------------------------------------------------

def _to_modis_doy(d: datetime.date) -> str:
    """Return MODIS date string A{YYYY}{DDD} for the given date."""
    return f"A{d.year}{d.timetuple().tm_yday:03d}"


def _safe_replace_year(d: datetime.date, year: int) -> datetime.date:
    """Replace year, clamping Feb-29 to Feb-28 on non-leap years."""
    try:
        return d.replace(year=year)
    except ValueError:
        return d.replace(year=year, day=28)


def _ornl_fetch_ndvi_point(
    lat: float,
    lon: float,
    date: datetime.date,
    product: str,
    token: Optional[str],
    km_buffer: float = 1.0,
) -> Optional[float]:
    """
    Query ORNL DAAC MODIS Web Service for mean NDVI at a single point.

    Searches the 16-day composite window ending on `date`. Returns
    a quality-filtered mean NDVI (0–1) or None on any failure.
    """
    # Use a 16-day lookback so the composite that covers `date` is returned.
    start = date - datetime.timedelta(days=16)
    params = {
        "latitude": lat,
        "longitude": lon,
        "startDate": _to_modis_doy(start),
        "endDate": _to_modis_doy(date),
        "kmAboveBelow": int(km_buffer),
        "kmLeftRight": int(km_buffer),
    }
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"{_ORNL_BASE}/{product}/subset"
    try:
        r = requests.get(url, params=params, headers=headers, timeout=60)
        r.raise_for_status()
        payload = r.json()
    except Exception:
        return None

    subsets = payload.get("subset", [])

    # Build a per-pixel QA mask from the reliability band (0=good, 1=useful)
    qa_mask: Optional[np.ndarray] = None
    for entry in subsets:
        if entry.get("band") == _ORNL_QA_BAND:
            qa_arr = np.array(entry["data"], dtype=np.int16)
            qa_mask = qa_arr <= 1  # True where pixel is usable
            break

    ndvi_vals: list[float] = []
    for entry in subsets:
        if entry.get("band") != _ORNL_NDVI_BAND:
            continue
        raw = np.array(entry["data"], dtype=np.int32)

        # Apply fill-value and valid-range filters
        valid = (raw != _ORNL_NODATA) & (raw >= -2000) & (raw <= 10000)
        if qa_mask is not None and qa_mask.shape == raw.shape:
            valid &= qa_mask

        scaled = raw[valid].astype(float) * _ORNL_NDVI_SCALE
        # Final sanity clip: NDVI physically bounded to [-0.2, 1.0]
        scaled = scaled[(scaled >= -0.2) & (scaled <= 1.0)]
        ndvi_vals.extend(scaled.tolist())

    return float(np.mean(ndvi_vals)) if ndvi_vals else None


def _ornl_aggregate_bbox(
    bbox: Tuple[float, float, float, float],
    date: datetime.date,
    product: str,
    n_samples: int,
    token: Optional[str],
    delay: float,
) -> Optional[float]:
    """Sample grid points within bbox and return mean NDVI via ORNL DAAC."""
    points = _sample_grid_points(bbox, n_samples)
    vals: list[float] = []
    for lon, lat in points:
        v = _ornl_fetch_ndvi_point(lat, lon, date, product, token)
        if v is not None:
            vals.append(v)
        time.sleep(delay)
    return float(np.mean(vals)) if vals else None


def _wps_ndvi_at_week(
    bbox: Tuple[float, float, float, float],
    date: datetime.date,
    n_samples: int,
    delay: float,
) -> Optional[float]:
    """WPS fallback: return mean NDVI for the target week across sampled points."""
    year, week = date.year, _iso_week(date)
    points = _sample_grid_points(bbox, n_samples)
    vals: list[float] = []
    for lon, lat in points:
        raw = _wps_fetch_yearly_profile(_NDVI_PRODUCT_ID, lon, lat, year)
        if raw is None or len(raw) < week:
            time.sleep(delay)
            continue
        v = float(raw[week - 1])
        if not np.isnan(v):
            # Normalize byte-scaled values to 0–1 if needed
            vals.append(v / 255.0 if v > 1.5 else v)
        time.sleep(delay)
    return float(np.mean(vals)) if vals else None


def _baseline_ndvi(
    bbox: Tuple[float, float, float, float],
    date: datetime.date,
    baseline_years: list,
    n_samples: int,
    token: Optional[str],
    delay: float,
) -> Optional[float]:
    """
    Compute climatological mean NDVI for the same DOY across baseline_years.

    Tries ORNL stable product first; falls back to WPS per year if ORNL fails.
    """
    year_means: list[float] = []
    for yr in baseline_years:
        bl_date = _safe_replace_year(date, yr)
        v = _ornl_aggregate_bbox(bbox, bl_date, _LANCE_STABLE_PRODUCT, n_samples, token, delay)
        if v is None:
            # WPS fallback for this baseline year
            v = _wps_ndvi_at_week(bbox, bl_date, n_samples, delay)
        if v is not None:
            year_means.append(v)
    return float(np.mean(year_means)) if year_means else None


# ---------------------------------------------------------------------------
# NDVI phenology
# ---------------------------------------------------------------------------

def _double_logistic(x, base, amp, sos, rise_rate, eos, fall_rate):
    return base + amp * (
        1 / (1 + np.exp(-rise_rate * (x - sos)))
        - 1 / (1 + np.exp(-fall_rate * (eos - x)))
    )


def _extract_phenometrics(ndvi_series: np.ndarray) -> Optional[dict]:
    """Fit a double-logistic model to a 52-value NDVI series. Returns metrics or None."""
    if len(ndvi_series) < 10:
        return None
    if np.isnan(ndvi_series).all() or np.count_nonzero(~np.isnan(ndvi_series)) < 10:
        return None

    doy = np.arange(1, len(ndvi_series) + 1) * 7
    filled = np.nan_to_num(ndvi_series, nan=float(np.nanmedian(ndvi_series)))
    window = min(11, len(filled) // 2 * 2 + 1)
    if window < 3:
        return None

    smooth = np.clip(savgol_filter(filled, window_length=window, polyorder=3), 0, 1)

    base_g = float(np.percentile(smooth, 10))
    peak_g = float(np.percentile(smooth, 95))
    amp_g = peak_g - base_g
    peak_doy = float(doy[int(np.argmax(smooth))])

    p0 = [base_g, amp_g, peak_doy - 60, 0.05, peak_doy + 50, 0.04]
    bounds = ([0, 0, 60, 0.001, 150, 0.001], [0.9, 1.0, 200, 0.15, 340, 0.15])

    try:
        popt, _ = curve_fit(
            _double_logistic, doy, smooth, p0=p0, bounds=bounds, maxfev=5000
        )
        base, amp, sos, rise_rate, eos, fall_rate = popt
        fitted = _double_logistic(np.arange(1, 366), *popt)
        peak_ndvi = float(fitted.max())
        pos = int(np.argmax(fitted)) + 1

        threshold = base + 0.2 * amp
        above = np.where(fitted > threshold)[0]
        sos_doy = int(above[0]) + 1 if len(above) else int(sos)
        eos_doy = int(above[-1]) + 1 if len(above) else int(eos)

        return {
            "SOS": sos_doy,
            "POS": pos,
            "EOS": eos_doy,
            "GSL": eos_doy - sos_doy,
            "PeakNDVI": peak_ndvi,
            "Amplitude": float(amp),
            "Base": float(base),
            # Raw curve parameters stored so the full fitted curve can be
            # reconstructed at any DOY without refitting.
            "_popt": [float(base), float(amp), float(sos),
                      float(rise_rate), float(eos), float(fall_rate)],
        }
    except Exception:
        return None


def _metrics_to_curve(metrics: dict) -> np.ndarray:
    """Reconstruct the fitted double-logistic as a 365-element array (index = DOY-1)."""
    return _double_logistic(np.arange(1, 366), *metrics["_popt"])


def _mean_curve(metrics_list: list) -> Optional[np.ndarray]:
    """
    Average fitted curves across a list of phenometric dicts.

    Each year/point gets equal weight.  Averaging the 365-point curve
    arrays (rather than the 6 nonlinear parameters) produces a shape-
    preserving mean that handles inter-annual variation correctly.
    """
    curves = [_metrics_to_curve(m) for m in metrics_list if m is not None and "_popt" in m]
    return np.mean(curves, axis=0) if curves else None


def _mean_scalar_metrics(metrics_list: list) -> Optional[dict]:
    """Average the scalar phenometrics (SOS, POS, EOS, GSL, PeakNDVI, Amplitude, Base)."""
    valid = [m for m in metrics_list if m is not None]
    if not valid:
        return None
    keys = ["SOS", "POS", "EOS", "GSL", "PeakNDVI", "Amplitude", "Base"]
    return {k: float(np.mean([m[k] for m in valid])) for k in keys}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_crop_health(
    region_bbox: Tuple[float, float, float, float],
    date: Union[str, datetime.date],
    n_samples: int = 16,
    sample_delay: float = 0.3,
) -> dict:
    """
    Assess crop health via NDVI phenology for an arbitrary region.

    Parameters
    ----------
    region_bbox : (min_lon, min_lat, max_lon, max_lat) in WGS84
    date        : "YYYY-MM-DD" string or datetime.date — sets the analysis year
    n_samples   : number of grid points sampled within the bbox
    sample_delay: seconds between WPS requests (rate limiting)

    Returns
    -------
    dict
        year, week, n_valid_profiles,
        mean_peak_ndvi, mean_gsl, mean_sos, mean_eos,
        pct_with_phenology  (0.0–1.0),
        status  ("above_average" | "average" | "below_average" | "data_unavailable")
    """
    d = _parse_date(date)
    year, week = d.year, _iso_week(d)
    points = _sample_grid_points(region_bbox, n_samples)

    profiles: list[np.ndarray] = []
    for lon, lat in points:
        raw = _wps_fetch_yearly_profile(_NDVI_PRODUCT_ID, lon, lat, year)
        if raw is not None and len(raw) >= 4:
            # Normalize byte-scaled values (0–255) to 0–1 if needed
            profiles.append(raw / 255.0 if raw.max() > 1.5 else raw)
        time.sleep(sample_delay)

    base_result = {"year": year, "week": week}

    if not profiles:
        return {**base_result, "n_valid_profiles": 0, "mean_peak_ndvi": None,
                "mean_gsl": None, "mean_sos": None, "mean_eos": None,
                "pct_with_phenology": 0.0, "status": "data_unavailable"}

    metrics = [_extract_phenometrics(p) for p in profiles]
    valid = [m for m in metrics if m is not None]
    pct = len(valid) / len(profiles)

    if not valid:
        mean_peak = float(np.nanmean([np.nanmax(p) for p in profiles]))
        return {**base_result, "n_valid_profiles": len(profiles),
                "mean_peak_ndvi": round(mean_peak, 4), "mean_gsl": None,
                "mean_sos": None, "mean_eos": None,
                "pct_with_phenology": round(pct, 3), "status": "data_unavailable"}

    mean_peak = float(np.mean([m["PeakNDVI"] for m in valid]))
    status = (
        "above_average" if mean_peak >= 0.70
        else "average"  if mean_peak >= 0.50
        else "below_average"
    )

    return {
        **base_result,
        "n_valid_profiles": len(profiles),
        "mean_peak_ndvi": round(mean_peak, 4),
        "mean_gsl": round(float(np.mean([m["GSL"] for m in valid])), 1),
        "mean_sos": round(float(np.mean([m["SOS"] for m in valid])), 1),
        "mean_eos": round(float(np.mean([m["EOS"] for m in valid])), 1),
        "pct_with_phenology": round(pct, 3),
        "status": status,
    }


def get_drought_status(
    region_bbox: Tuple[float, float, float, float],
    date: Union[str, datetime.date],
    baseline_years: Optional[list] = None,
    n_samples: int = 16,
    sample_delay: float = 0.3,
    smap_product_id: str = _SMAP_PRODUCT_ID,
) -> dict:
    """
    Assess drought conditions via SMAP soil moisture anomaly for an arbitrary region.

    Parameters
    ----------
    region_bbox     : (min_lon, min_lat, max_lon, max_lat) in WGS84
    date            : "YYYY-MM-DD" string or datetime.date — event date to assess
    baseline_years  : years used to compute climatological mean (default 2016–2021)
    n_samples       : number of grid points sampled within the bbox
    sample_delay    : seconds between WPS requests
    smap_product_id : WPS product identifier for soil moisture

    Returns
    -------
    dict
        year, week, n_valid_points,
        mean_sm_event    (soil moisture for the event week),
        mean_sm_baseline (climatological mean for the same week),
        anomaly          (event − baseline; negative = drier than normal),
        anomaly_pct      (anomaly as % of baseline),
        status  ("no_drought" | "abnormally_dry" | "moderate_drought" |
                 "severe_drought" | "exceptional_drought" | "data_unavailable")
    """
    d = _parse_date(date)
    year, week = d.year, _iso_week(d)
    if baseline_years is None:
        baseline_years = _DEFAULT_BASELINE_YEARS
    points = _sample_grid_points(region_bbox, n_samples)

    def _sm_at_week(yr: int, wk: int, lon: float, lat: float) -> Optional[float]:
        raw = _wps_fetch_yearly_profile(smap_product_id, lon, lat, yr)
        if raw is None or len(raw) < wk:
            return None
        val = float(raw[wk - 1])
        return None if np.isnan(val) else val

    event_vals: list[float] = []
    baseline_vals: list[float] = []

    for lon, lat in points:
        ev = _sm_at_week(year, week, lon, lat)
        if ev is not None:
            event_vals.append(ev)

        bl = [_sm_at_week(by, week, lon, lat) for by in baseline_years]
        bl = [v for v in bl if v is not None]
        if bl:
            baseline_vals.append(float(np.mean(bl)))

        time.sleep(sample_delay)

    base_result = {"year": year, "week": week}

    if not event_vals or not baseline_vals:
        return {**base_result, "n_valid_points": 0, "mean_sm_event": None,
                "mean_sm_baseline": None, "anomaly": None, "anomaly_pct": None,
                "status": "data_unavailable"}

    mean_event = float(np.mean(event_vals))
    mean_baseline = float(np.mean(baseline_vals))
    anomaly = mean_event - mean_baseline
    anomaly_pct = (anomaly / mean_baseline * 100.0) if mean_baseline else None

    if anomaly_pct is None:
        status = "data_unavailable"
    elif anomaly_pct <= -40:
        status = "exceptional_drought"
    elif anomaly_pct <= -30:
        status = "severe_drought"
    elif anomaly_pct <= -20:
        status = "moderate_drought"
    elif anomaly_pct <= -10:
        status = "abnormally_dry"
    else:
        status = "no_drought"

    return {
        **base_result,
        "n_valid_points": len(event_vals),
        "mean_sm_event": round(mean_event, 5),
        "mean_sm_baseline": round(mean_baseline, 5),
        "anomaly": round(anomaly, 5),
        "anomaly_pct": round(anomaly_pct, 2) if anomaly_pct is not None else None,
        "status": status,
    }


def get_ndvi_observation(
    region_bbox: Tuple[float, float, float, float],
    date: Union[str, datetime.date],
    region_id: str = LOUISIANA_REGION_ID,
    baseline_years: Optional[list] = None,
    n_samples: int = 9,
    nasa_token: Optional[str] = None,
    sample_delay: float = 0.3,
) -> dict:
    """
    Return a current-vs-baseline NDVI snapshot for any region.

    Data source priority
    --------------------
    1. NASA LANCE NRT (MOD13Q1N, 250 m, ~hours latency) via ORNL DAAC Web Service.
       Requires ``EARTHDATA_TOKEN`` env var or ``nasa_token`` argument.
    2. NASA MODIS stable (MOD13Q1) — same API, no auth, slightly higher latency.
       Used automatically when NRT product returns no data.
    3. CSISS WPS NDVI-WEEKLY profile — the existing CropSmart fallback.

    Baseline is the climatological mean for the same day-of-year across
    ``baseline_years`` (default 2016–2021), computed from the same source
    tier that succeeded for the current observation, with per-year WPS
    fallback if ORNL fails for a given year.

    Parameters
    ----------
    region_bbox    : (min_lon, min_lat, max_lon, max_lat) in WGS84
    date           : "YYYY-MM-DD" string or datetime.date
    region_id      : caller-supplied label included verbatim in output
    baseline_years : list of int years for climatological mean
    n_samples      : grid points sampled within bbox
                     (total ORNL calls ≈ n_samples × (1 + len(baseline_years)))
    nasa_token     : NASA Earthdata bearer token; falls back to EARTHDATA_TOKEN env var
    sample_delay   : seconds between requests (rate limiting)

    Returns
    -------
    JSON-serialisable dict
        region_id      : str
        date           : "YYYY-MM-DD"
        ndvi_current   : float | null   — mean NDVI for the observation date
        ndvi_baseline  : float | null   — climatological mean NDVI
        deviation_pct  : float | null   — (current − baseline) / baseline × 100
        status         : "above_average" | "average" | "below_average" |
                         "stressed" | "data_unavailable"
        source         : "lance_nrt" | "lance_stable" | "wps_fallback" | "unavailable"
    """
    d = _parse_date(date)
    token: Optional[str] = nasa_token or os.environ.get("EARTHDATA_TOKEN")
    bl_years = baseline_years if baseline_years is not None else _DEFAULT_BASELINE_YEARS

    # ---- 1. Try LANCE NRT ----
    current = _ornl_aggregate_bbox(region_bbox, d, _LANCE_NRT_PRODUCT, n_samples, token, sample_delay)
    source = "lance_nrt"

    # ---- 2. Degrade to stable MODIS if NRT unavailable ----
    if current is None:
        current = _ornl_aggregate_bbox(region_bbox, d, _LANCE_STABLE_PRODUCT, n_samples, token, sample_delay)
        source = "lance_stable"

    # ---- 3. Fall back to WPS ----
    if current is None:
        current = _wps_ndvi_at_week(region_bbox, d, n_samples, sample_delay)
        source = "wps_fallback"

    if current is None:
        return {
            "region_id": region_id,
            "date": str(d),
            "ndvi_current": None,
            "ndvi_baseline": None,
            "deviation_pct": None,
            "status": "data_unavailable",
            "source": "unavailable",
        }

    # ---- Baseline (uses same ORNL path + per-year WPS fallback internally) ----
    baseline = _baseline_ndvi(region_bbox, d, bl_years, n_samples, token, sample_delay)

    # ---- Deviation and status ----
    if baseline and baseline != 0.0:
        deviation_pct = (current - baseline) / baseline * 100.0
    else:
        deviation_pct = None

    if deviation_pct is None:
        status = "data_unavailable"
    elif deviation_pct > 10.0:
        status = "above_average"
    elif deviation_pct >= -10.0:
        status = "average"
    elif deviation_pct >= -20.0:
        status = "below_average"
    else:
        status = "stressed"

    return {
        "region_id": region_id,
        "date": str(d),
        "ndvi_current": round(current, 4),
        "ndvi_baseline": round(baseline, 4) if baseline is not None else None,
        "deviation_pct": round(deviation_pct, 2) if deviation_pct is not None else None,
        "status": status,
        "source": source,
    }


def detect_ndvi_anomaly(
    region_bbox: Tuple[float, float, float, float],
    date: Union[str, datetime.date],
    region_id: str = LOUISIANA_REGION_ID,
    baseline_years: Optional[list] = None,
    n_samples: int = 16,
    sample_delay: float = 0.3,
) -> dict:
    """
    Compare current-year NDVI phenology against a 5-year baseline using
    double-logistic curve parameters, and flag anomalies at two severity levels.

    Deviation signals
    -----------------
    Two independent signals are computed from the fitted curves:

    1. **DOY-curve deviation** — evaluates both the current and baseline
       fitted curves at today's day-of-year.  Captures in-season stress even
       before peak NDVI is reached.

    2. **PeakNDVI deviation** — compares the projected seasonal maximum.
       Reliable once enough of the season has been observed (≳ 20 weeks).

    The alert is raised on whichever signal is more negative (worst case).

    Thresholds
    ----------
    - ``deviation_pct ≤ -15 %`` → **warning**
    - ``deviation_pct ≤ -30 %`` → **critical**
    - otherwise                 → **normal**

    Baseline
    --------
    Defaults to the 5 calendar years immediately preceding the observation year
    (e.g. observation 2024 → baseline [2019, 2020, 2021, 2022, 2023]).
    Pass ``baseline_years`` to override.

    Confidence
    ----------
    Reported as ``"high" / "medium" / "low"`` based on the fraction of sample
    points that produced a successful double-logistic fit for the current year.

    Parameters
    ----------
    region_bbox    : (min_lon, min_lat, max_lon, max_lat) in WGS84
    date           : "YYYY-MM-DD" string or datetime.date
    region_id      : label included verbatim in output
    baseline_years : list of int years; default = 5 years prior to observation
    n_samples      : grid points sampled within bbox (WPS calls = n × (1 + n_baseline_years))
    sample_delay   : seconds between WPS requests

    Returns
    -------
    dict
        region_id, date, doy, year, baseline_years,
        alert               ("normal" | "warning" | "critical" | "data_unavailable"),
        thresholds          {"warning_pct": -15.0, "critical_pct": -30.0},
        primary_deviation_pct   (the signal that triggered the alert),
        primary_signal          ("doy_curve" | "peak_ndvi" | null),
        doy_ndvi_current,   doy_ndvi_baseline,   doy_ndvi_deviation_pct,
        peak_ndvi_current,  peak_ndvi_baseline,  peak_ndvi_deviation_pct,
        amplitude_deviation_pct,
        gsl_deviation_pct,
        sos_current,  sos_baseline,
        eos_current,  eos_baseline,
        n_current_profiles, n_baseline_profiles,
        confidence          ("high" | "medium" | "low")
    """
    d = _parse_date(date)
    year = d.year
    doy = d.timetuple().tm_yday

    # Default: the 5 years immediately before the observation year
    if baseline_years is None:
        baseline_years = [year - i for i in range(5, 0, -1)]

    points = _sample_grid_points(region_bbox, n_samples)

    def _fetch_and_fit(yr: int) -> list:
        """Fetch NDVI profiles for all sample points in `yr`, return fitted metrics."""
        fitted = []
        for lon, lat in points:
            raw = _wps_fetch_yearly_profile(_NDVI_PRODUCT_ID, lon, lat, yr)
            if raw is not None and len(raw) >= 4:
                profile = raw / 255.0 if raw.max() > 1.5 else raw
                m = _extract_phenometrics(profile)
                if m is not None:
                    fitted.append(m)
            time.sleep(sample_delay)
        return fitted

    # ---- Current year ----
    current_fits = _fetch_and_fit(year)

    # ---- Baseline years ----
    # Compute a per-year mean curve, then average those curves so each year
    # has equal weight regardless of how many points had successful fits.
    baseline_year_curves: list[np.ndarray] = []
    baseline_year_scalars: list[dict] = []
    n_baseline_profiles = 0

    for yr in baseline_years:
        yr_fits = _fetch_and_fit(yr)
        n_baseline_profiles += len(yr_fits)
        if not yr_fits:
            continue
        curve = _mean_curve(yr_fits)
        scalars = _mean_scalar_metrics(yr_fits)
        if curve is not None:
            baseline_year_curves.append(curve)
        if scalars is not None:
            baseline_year_scalars.append(scalars)

    # ---- Unavailable guard ----
    if not current_fits or not baseline_year_curves:
        return {
            "region_id": region_id,
            "date": str(d),
            "doy": doy,
            "year": year,
            "baseline_years": baseline_years,
            "alert": "data_unavailable",
            "thresholds": {"warning_pct": ANOMALY_WARNING_PCT, "critical_pct": ANOMALY_CRITICAL_PCT},
            "primary_deviation_pct": None,
            "primary_signal": None,
            "doy_ndvi_current": None, "doy_ndvi_baseline": None, "doy_ndvi_deviation_pct": None,
            "peak_ndvi_current": None, "peak_ndvi_baseline": None, "peak_ndvi_deviation_pct": None,
            "amplitude_deviation_pct": None, "gsl_deviation_pct": None,
            "sos_current": None, "sos_baseline": None,
            "eos_current": None, "eos_baseline": None,
            "n_current_profiles": len(current_fits),
            "n_baseline_profiles": n_baseline_profiles,
            "confidence": "low",
        }

    # ---- Mean curves ----
    current_curve = _mean_curve(current_fits)           # shape (365,) or None
    baseline_curve = np.mean(baseline_year_curves, axis=0)  # equal-weight year average

    current_scalars = _mean_scalar_metrics(current_fits)
    baseline_scalars = _mean_scalar_metrics(baseline_year_scalars) if baseline_year_scalars else None

    # ---- DOY-curve deviation ----
    doy_current = doy_baseline = doy_dev = None
    if current_curve is not None:
        doy_current = float(current_curve[doy - 1])
        doy_baseline = float(baseline_curve[doy - 1])
        if doy_baseline > 0:
            doy_dev = (doy_current - doy_baseline) / doy_baseline * 100.0

    # ---- PeakNDVI deviation ----
    peak_current = peak_baseline = peak_dev = None
    amp_dev = gsl_dev = None
    sos_current = sos_baseline = eos_current = eos_baseline = None

    if current_scalars and baseline_scalars:
        peak_current = current_scalars["PeakNDVI"]
        peak_baseline = baseline_scalars["PeakNDVI"]
        if peak_baseline > 0:
            peak_dev = (peak_current - peak_baseline) / peak_baseline * 100.0

        if baseline_scalars["Amplitude"] > 0:
            amp_dev = (current_scalars["Amplitude"] - baseline_scalars["Amplitude"]) / baseline_scalars["Amplitude"] * 100.0
        if baseline_scalars["GSL"] > 0:
            gsl_dev = (current_scalars["GSL"] - baseline_scalars["GSL"]) / baseline_scalars["GSL"] * 100.0

        sos_current = round(current_scalars["SOS"], 1)
        sos_baseline = round(baseline_scalars["SOS"], 1)
        eos_current = round(current_scalars["EOS"], 1)
        eos_baseline = round(baseline_scalars["EOS"], 1)

    # ---- Primary signal: whichever deviation is more negative ----
    candidates: list[tuple[float, str]] = []
    if doy_dev is not None:
        candidates.append((doy_dev, "doy_curve"))
    if peak_dev is not None:
        candidates.append((peak_dev, "peak_ndvi"))

    if candidates:
        primary_dev, primary_signal = min(candidates, key=lambda t: t[0])
    else:
        primary_dev, primary_signal = None, None

    # ---- Alert level ----
    if primary_dev is None:
        alert = "data_unavailable"
    elif primary_dev <= ANOMALY_CRITICAL_PCT:
        alert = "critical"
    elif primary_dev <= ANOMALY_WARNING_PCT:
        alert = "warning"
    else:
        alert = "normal"

    # ---- Confidence ----
    fit_rate = len(current_fits) / max(len(points), 1)
    confidence = "high" if fit_rate >= 0.6 else ("medium" if fit_rate >= 0.3 else "low")

    def _r(v, ndigits=4):
        return round(v, ndigits) if v is not None else None

    return {
        "region_id": region_id,
        "date": str(d),
        "doy": doy,
        "year": year,
        "baseline_years": baseline_years,
        "alert": alert,
        "thresholds": {"warning_pct": ANOMALY_WARNING_PCT, "critical_pct": ANOMALY_CRITICAL_PCT},
        "primary_deviation_pct": _r(primary_dev, 2),
        "primary_signal": primary_signal,
        "doy_ndvi_current": _r(doy_current),
        "doy_ndvi_baseline": _r(doy_baseline),
        "doy_ndvi_deviation_pct": _r(doy_dev, 2),
        "peak_ndvi_current": _r(peak_current),
        "peak_ndvi_baseline": _r(peak_baseline),
        "peak_ndvi_deviation_pct": _r(peak_dev, 2),
        "amplitude_deviation_pct": _r(amp_dev, 2),
        "gsl_deviation_pct": _r(gsl_dev, 2),
        "sos_current": sos_current,
        "sos_baseline": sos_baseline,
        "eos_current": eos_current,
        "eos_baseline": eos_baseline,
        "n_current_profiles": len(current_fits),
        "n_baseline_profiles": n_baseline_profiles,
        "confidence": confidence,
    }
