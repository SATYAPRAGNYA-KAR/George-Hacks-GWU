"""
Crop health and drought assessment via NDVI phenology (CSISS WPS) and SMAP soil moisture.

Functions
---------
get_crop_health(region_bbox, date)   -> dict
get_drought_status(region_bbox, date) -> dict

Both accept:
  region_bbox : (min_lon, min_lat, max_lon, max_lat) in WGS84
  date        : "YYYY-MM-DD" str or datetime.date
"""

import io
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
        }
    except Exception:
        return None


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
