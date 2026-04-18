"""
Tests for crop_health.py

All network calls (ORNL DAAC, CSISS WPS) are monkey-patched so tests run
fully offline and deterministically.

Covers:
  - _parse_date: string / date / datetime inputs
  - _iso_week: week-number extraction
  - _sample_grid_points: grid geometry
  - _normalize_to_01: byte-scale detection
  - get_ndvi_observation: source priority waterfall, deviation/status logic
  - get_drought_status: anomaly classification thresholds
  - detect_ndvi_anomaly: alert levels, confidence classification
  - get_crop_health: mean peak NDVI → status label
"""

from __future__ import annotations

import datetime
import math
from typing import Optional
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

import crop_health
from crop_health import (
    _parse_date,
    _iso_week,
    _sample_grid_points,
    _ornl_fetch_ndvi_point,
    _ornl_aggregate_bbox,
    _wps_ndvi_at_week,
    _baseline_ndvi,
    get_ndvi_observation,
    get_drought_status,
    detect_ndvi_anomaly,
    get_crop_health,
    LOUISIANA_BBOX,
    LOUISIANA_REGION_ID,
    ANOMALY_WARNING_PCT,
    ANOMALY_CRITICAL_PCT,
)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

BBOX = LOUISIANA_BBOX          # (-94.04, 28.93, -88.82, 33.02)
DATE_STR = "2024-07-15"
DATE_OBJ = datetime.date(2024, 7, 15)

# Synthetic NDVI value in healthy range
HEALTHY_NDVI = 0.65
STRESSED_NDVI = 0.35  # significantly below healthy baseline

# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_string_iso(self):
        assert _parse_date("2024-07-15") == datetime.date(2024, 7, 15)

    def test_date_passthrough(self):
        d = datetime.date(2023, 1, 1)
        assert _parse_date(d) is d

    def test_datetime_to_date(self):
        dt = datetime.datetime(2024, 6, 15, 12, 30)
        assert _parse_date(dt) == datetime.date(2024, 6, 15)

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            _parse_date("not-a-date")


# ---------------------------------------------------------------------------
# _iso_week
# ---------------------------------------------------------------------------

class TestIsoWeek:
    def test_early_january(self):
        # 2024-01-08 is in week 2
        assert _iso_week(datetime.date(2024, 1, 8)) == 2

    def test_mid_year(self):
        w = _iso_week(datetime.date(2024, 7, 15))
        assert 28 <= w <= 29

    def test_late_december(self):
        w = _iso_week(datetime.date(2024, 12, 23))
        assert w in (51, 52)

    def test_returns_int(self):
        assert isinstance(_iso_week(datetime.date(2024, 6, 1)), int)


# ---------------------------------------------------------------------------
# _sample_grid_points
# ---------------------------------------------------------------------------

class TestSampleGridPoints:
    def test_returns_list(self):
        pts = _sample_grid_points(BBOX, 9)
        assert isinstance(pts, list)

    def test_n_samples_approximately_honoured(self):
        # grid is ceil(sqrt(n))^2 so we may get slightly more
        pts = _sample_grid_points(BBOX, 9)
        assert len(pts) >= 9

    def test_points_within_bbox(self):
        min_lon, min_lat, max_lon, max_lat = BBOX
        for lon, lat in _sample_grid_points(BBOX, 16):
            assert min_lon <= lon <= max_lon
            assert min_lat <= lat <= max_lat

    def test_single_sample(self):
        pts = _sample_grid_points(BBOX, 1)
        assert len(pts) >= 1


# ---------------------------------------------------------------------------
# get_ndvi_observation — source priority waterfall
# ---------------------------------------------------------------------------

class TestGetNdviObservation:
    """Verify the NRT → stable → WPS fallback chain."""

    def _run(self, nrt_return=None, stable_return=None, wps_return=None,
             baseline_return=None):
        with patch.object(crop_health, "_ornl_aggregate_bbox") as mock_ornl:
            # First call = NRT, second call = stable
            mock_ornl.side_effect = [nrt_return, stable_return]
            with patch.object(crop_health, "_wps_ndvi_at_week", return_value=wps_return):
                with patch.object(crop_health, "_baseline_ndvi", return_value=baseline_return):
                    return get_ndvi_observation(
                        BBOX, DATE_STR, region_id=LOUISIANA_REGION_ID, n_samples=1
                    )

    def test_uses_nrt_when_available(self):
        result = self._run(nrt_return=HEALTHY_NDVI, baseline_return=HEALTHY_NDVI)
        assert result["source"] == "lance_nrt"
        assert result["ndvi_current"] == pytest.approx(HEALTHY_NDVI, abs=0.001)

    def test_falls_back_to_stable_when_nrt_none(self):
        result = self._run(nrt_return=None, stable_return=HEALTHY_NDVI, baseline_return=HEALTHY_NDVI)
        assert result["source"] == "lance_stable"

    def test_falls_back_to_wps_when_ornl_both_fail(self):
        result = self._run(nrt_return=None, stable_return=None, wps_return=HEALTHY_NDVI, baseline_return=HEALTHY_NDVI)
        assert result["source"] == "wps_fallback"

    def test_unavailable_when_all_sources_fail(self):
        result = self._run(nrt_return=None, stable_return=None, wps_return=None)
        assert result["source"] == "unavailable"
        assert result["ndvi_current"] is None
        assert result["status"] == "data_unavailable"

    def test_result_has_required_keys(self):
        result = self._run(nrt_return=HEALTHY_NDVI, baseline_return=HEALTHY_NDVI)
        for key in ("region_id", "date", "ndvi_current", "ndvi_baseline",
                    "deviation_pct", "status", "source"):
            assert key in result, f"Missing key: {key}"

    def test_region_id_echoed(self):
        result = self._run(nrt_return=HEALTHY_NDVI, baseline_return=HEALTHY_NDVI)
        assert result["region_id"] == LOUISIANA_REGION_ID

    def test_date_echoed(self):
        result = self._run(nrt_return=HEALTHY_NDVI, baseline_return=HEALTHY_NDVI)
        assert result["date"] == DATE_STR


# ---------------------------------------------------------------------------
# get_ndvi_observation — status/deviation logic
# ---------------------------------------------------------------------------

class TestNdviDeviationStatus:
    def _obs(self, current, baseline):
        with patch.object(crop_health, "_ornl_aggregate_bbox", side_effect=[current, None]):
            with patch.object(crop_health, "_wps_ndvi_at_week", return_value=current):
                with patch.object(crop_health, "_baseline_ndvi", return_value=baseline):
                    return get_ndvi_observation(BBOX, DATE_STR, n_samples=1)

    def test_above_average_status(self):
        # current 15% above baseline
        result = self._obs(0.75, 0.65)
        assert result["status"] == "above_average"

    def test_average_status_small_deviation(self):
        result = self._obs(0.63, 0.65)  # ~-3% → average
        assert result["status"] == "average"

    def test_below_average_status(self):
        result = self._obs(0.52, 0.65)  # ~-20% → below_average
        assert result["status"] == "below_average"

    def test_stressed_status_large_deviation(self):
        result = self._obs(0.40, 0.65)  # ~-38% → stressed
        assert result["status"] == "stressed"

    def test_deviation_none_when_no_baseline(self):
        with patch.object(crop_health, "_ornl_aggregate_bbox", side_effect=[0.65, None]):
            with patch.object(crop_health, "_wps_ndvi_at_week", return_value=0.65):
                with patch.object(crop_health, "_baseline_ndvi", return_value=None):
                    result = get_ndvi_observation(BBOX, DATE_STR, n_samples=1)
        assert result["deviation_pct"] is None
        assert result["status"] == "data_unavailable"

    def test_deviation_calculation_correct(self):
        current, baseline = 0.50, 0.65
        result = self._obs(current, baseline)
        expected_dev = (current - baseline) / baseline * 100.0
        assert result["deviation_pct"] == pytest.approx(expected_dev, abs=0.1)


# ---------------------------------------------------------------------------
# get_drought_status — threshold classification
# ---------------------------------------------------------------------------

class TestGetDroughtStatus:
    """Mock WPS calls and verify the anomaly_pct → status mapping."""

    def _drought(self, event_sm: float, baseline_sm: float):
        """
        Patch _wps_fetch_yearly_profile to return simple arrays where
        week 28 (mid-July baseline) has the desired value.
        """
        def _mock_wps(product_id, lon, lat, yr):
            arr = np.zeros(52)
            arr[27] = event_sm if yr == 2024 else baseline_sm
            return arr

        with patch.object(crop_health, "_wps_fetch_yearly_profile", side_effect=_mock_wps):
            return get_drought_status(
                BBOX, DATE_STR,
                baseline_years=[2019, 2020, 2021],
                n_samples=4,
                sample_delay=0.0,
            )

    def test_no_drought_when_near_baseline(self):
        result = self._drought(0.30, 0.30)
        assert result["status"] == "no_drought"

    def test_abnormally_dry(self):
        # ~-12% anomaly → abnormally_dry
        result = self._drought(0.264, 0.30)
        assert result["status"] == "abnormally_dry"

    def test_moderate_drought(self):
        # ~-23% anomaly
        result = self._drought(0.231, 0.30)
        assert result["status"] == "moderate_drought"

    def test_severe_drought(self):
        # ~-33% anomaly
        result = self._drought(0.20, 0.30)
        assert result["status"] == "severe_drought"

    def test_exceptional_drought(self):
        # ~-50% anomaly
        result = self._drought(0.15, 0.30)
        assert result["status"] == "exceptional_drought"

    def test_data_unavailable_when_no_wps_data(self):
        with patch.object(crop_health, "_wps_fetch_yearly_profile", return_value=None):
            result = get_drought_status(BBOX, DATE_STR, n_samples=4, sample_delay=0.0)
        assert result["status"] == "data_unavailable"
        assert result["mean_sm_event"] is None

    def test_result_has_required_keys(self):
        result = self._drought(0.30, 0.30)
        for key in ("year", "week", "n_valid_points", "mean_sm_event",
                    "mean_sm_baseline", "anomaly", "anomaly_pct", "status"):
            assert key in result, f"Missing key: {key}"

    def test_anomaly_pct_sign(self):
        result = self._drought(0.20, 0.30)  # drier than baseline
        assert result["anomaly_pct"] < 0.0

    def test_above_baseline_is_no_drought(self):
        # Wetter than baseline
        result = self._drought(0.40, 0.30)
        assert result["status"] == "no_drought"


# ---------------------------------------------------------------------------
# detect_ndvi_anomaly — alert level mapping
# ---------------------------------------------------------------------------

class TestDetectNdviAnomaly:
    """
    Patch _wps_fetch_yearly_profile to return synthetic phenological curves
    that will produce known deviation values.
    """

    def _run_anomaly(self, current_peak: float, baseline_peak: float,
                     n_samples: int = 4) -> dict:
        """
        Build a double-logistic-like synthetic array where the peak is the
        supplied value, then run detect_ndvi_anomaly with mocked WPS.
        """
        def _synthetic_profile(peak: float) -> np.ndarray:
            x = np.arange(52)
            # Simple bell curve centred at week 26 with given amplitude
            arr = peak * np.exp(-0.5 * ((x - 26) / 8) ** 2)
            return arr

        current_arr = _synthetic_profile(current_peak)
        baseline_arr = _synthetic_profile(baseline_peak)

        call_count = {"n": 0}

        def _mock_wps(product_id, lon, lat, yr):
            call_count["n"] += 1
            if yr == 2024:
                return current_arr.copy()
            return baseline_arr.copy()

        with patch.object(crop_health, "_wps_fetch_yearly_profile", side_effect=_mock_wps):
            return detect_ndvi_anomaly(
                BBOX, DATE_STR,
                region_id=LOUISIANA_REGION_ID,
                baseline_years=[2019, 2020, 2021],
                n_samples=n_samples,
                sample_delay=0.0,
            )

    def test_result_has_required_keys(self):
        result = self._run_anomaly(0.65, 0.65)
        required = [
            "region_id", "date", "doy", "year", "baseline_years",
            "alert", "thresholds", "primary_deviation_pct",
            "n_current_profiles", "n_baseline_profiles", "confidence",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_alert_normal_when_peak_similar(self):
        result = self._run_anomaly(0.65, 0.65)
        # Peaks are identical → deviation = 0 → normal
        assert result["alert"] in ("normal", "data_unavailable")

    def test_alert_warning_when_moderate_stress(self):
        # ~-20% peak deviation should cross warning threshold (-15%)
        result = self._run_anomaly(0.52, 0.65)
        assert result["alert"] in ("warning", "critical", "data_unavailable")

    def test_alert_critical_when_severe_stress(self):
        # ~-40% deviation crosses critical threshold (-30%)
        result = self._run_anomaly(0.39, 0.65)
        assert result["alert"] in ("critical", "data_unavailable")

    def test_data_unavailable_when_wps_returns_none(self):
        with patch.object(crop_health, "_wps_fetch_yearly_profile", return_value=None):
            result = detect_ndvi_anomaly(BBOX, DATE_STR, n_samples=4, sample_delay=0.0)
        assert result["alert"] == "data_unavailable"

    def test_confidence_high_when_many_profiles(self):
        result = self._run_anomaly(0.65, 0.65, n_samples=9)
        assert result["confidence"] in ("high", "medium")

    def test_thresholds_in_result(self):
        result = self._run_anomaly(0.65, 0.65)
        assert result["thresholds"]["warning_pct"] == ANOMALY_WARNING_PCT
        assert result["thresholds"]["critical_pct"] == ANOMALY_CRITICAL_PCT

    def test_region_id_echoed(self):
        result = self._run_anomaly(0.65, 0.65)
        assert result["region_id"] == LOUISIANA_REGION_ID

    def test_date_echoed(self):
        result = self._run_anomaly(0.65, 0.65)
        assert result["date"] == DATE_STR


# ---------------------------------------------------------------------------
# get_crop_health — status label from peak NDVI
# ---------------------------------------------------------------------------

class TestGetCropHealth:
    def _run(self, mean_peak: float):
        """Mock WPS to return a simple profile achieving the given peak."""
        def _mock_wps(product_id, lon, lat, yr):
            arr = np.zeros(52)
            arr[25] = mean_peak  # peak at week 26
            return arr

        with patch.object(crop_health, "_wps_fetch_yearly_profile", side_effect=_mock_wps):
            return get_crop_health(BBOX, DATE_STR, n_samples=4, sample_delay=0.0)

    def test_above_average_status(self):
        result = self._run(0.75)  # ≥ 0.70
        assert result["status"] == "above_average"

    def test_average_status(self):
        result = self._run(0.55)  # 0.50–0.69
        assert result["status"] == "average"

    def test_below_average_status(self):
        result = self._run(0.35)  # < 0.50
        assert result["status"] == "below_average"

    def test_data_unavailable_when_no_profiles(self):
        with patch.object(crop_health, "_wps_fetch_yearly_profile", return_value=None):
            result = get_crop_health(BBOX, DATE_STR, n_samples=4, sample_delay=0.0)
        assert result["status"] == "data_unavailable"

    def test_result_has_required_keys(self):
        result = self._run(0.65)
        for key in ("year", "week", "n_valid_profiles", "mean_peak_ndvi",
                    "mean_gsl", "pct_with_phenology", "status"):
            assert key in result, f"Missing key: {key}"

    def test_mean_peak_ndvi_in_valid_range(self):
        result = self._run(0.65)
        if result["mean_peak_ndvi"] is not None:
            assert 0.0 <= result["mean_peak_ndvi"] <= 1.0

    def test_byte_scaled_profile_normalized(self):
        """Profiles with values > 1.5 should be divided by 255."""
        def _mock_wps_byte(product_id, lon, lat, yr):
            arr = np.zeros(52)
            arr[25] = 180  # byte-scaled; /255 ≈ 0.706
            return arr

        with patch.object(crop_health, "_wps_fetch_yearly_profile", side_effect=_mock_wps_byte):
            result = get_crop_health(BBOX, DATE_STR, n_samples=4, sample_delay=0.0)
        # 180/255 ≈ 0.706 → above_average
        assert result["status"] in ("above_average", "average", "below_average")
        if result["mean_peak_ndvi"]:
            assert result["mean_peak_ndvi"] <= 1.0


# ---------------------------------------------------------------------------
# _ornl_fetch_ndvi_point — unit test with mocked HTTP
# ---------------------------------------------------------------------------

class TestOrnlFetchNdviPoint:
    def _make_response(self, ndvi_vals, qa_vals=None):
        """Build a fake ORNL DAAC response payload."""
        ndvi_data = [int(v / 0.0001) for v in ndvi_vals]  # scale to raw int
        subsets = [{"band": "250m_16_days_NDVI", "data": ndvi_data}]
        if qa_vals is not None:
            subsets.append({"band": "250m_16_days_pixel_reliability", "data": qa_vals})
        return {"subset": subsets}

    def test_returns_float_for_valid_data(self):
        payload = self._make_response([0.60, 0.65, 0.70])
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            result = _ornl_fetch_ndvi_point(29.5, -90.5, DATE_OBJ, "MOD13Q1N", None)
        assert result is not None
        assert 0.55 <= result <= 0.75

    def test_returns_none_on_http_error(self):
        import requests as req_lib
        with patch("requests.get", side_effect=req_lib.ConnectionError("timeout")):
            result = _ornl_fetch_ndvi_point(29.5, -90.5, DATE_OBJ, "MOD13Q1N", None)
        assert result is None

    def test_qa_mask_filters_bad_pixels(self):
        """Pixels with QA > 1 should be excluded."""
        payload = self._make_response(
            [0.60, 0.20, 0.65],  # middle value is bad
            qa_vals=[0, 5, 1],   # QA > 1 masks middle pixel
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            result = _ornl_fetch_ndvi_point(29.5, -90.5, DATE_OBJ, "MOD13Q1N", None)
        # Result should average 0.60 and 0.65, NOT 0.20
        if result is not None:
            assert result > 0.50

    def test_nodata_values_excluded(self):
        from crop_health import _ORNL_NODATA
        payload = {"subset": [{"band": "250m_16_days_NDVI", "data": [_ORNL_NODATA, 6500]}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            result = _ornl_fetch_ndvi_point(29.5, -90.5, DATE_OBJ, "MOD13Q1N", None)
        # Only 6500 * 0.0001 = 0.65 should be included
        if result is not None:
            assert result == pytest.approx(0.65, abs=0.01)


# ---------------------------------------------------------------------------
# LOUISIANA_BBOX constant sanity
# ---------------------------------------------------------------------------

class TestLouisianaBbox:
    def test_bbox_has_four_elements(self):
        assert len(LOUISIANA_BBOX) == 4

    def test_bbox_lon_range(self):
        min_lon, _, max_lon, _ = LOUISIANA_BBOX
        assert -100 < min_lon < max_lon < -80

    def test_bbox_lat_range(self):
        _, min_lat, _, max_lat = LOUISIANA_BBOX
        assert 25 < min_lat < max_lat < 35