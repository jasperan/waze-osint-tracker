"""Tests for anomaly_detection module."""

from datetime import datetime, timezone

import pytest

from anomaly_detection import (
    _build_hour_histogram,
    _geo_spread_km,
    _geographic_centroid,
    _std_dev,
    _zscore,
    detect_anomalies,
    detect_frequency_anomalies,
    detect_location_anomalies,
    detect_time_anomalies,
)


def _make_events(n, lat=40.4, lon=-3.7, hour=10, day_spread=1):
    base_ms = int(datetime(2024, 1, 1, hour, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    return [
        {
            "latitude": lat + (i % 3) * 0.001,
            "longitude": lon + (i % 3) * 0.001,
            "timestamp_ms": base_ms + i * 86_400_000 * day_spread,
            "report_type": "POLICE",
        }
        for i in range(n)
    ]


class TestZscore:
    def test_normal(self):
        assert _zscore(10, 10, 2) == 0.0

    def test_deviation(self):
        assert _zscore(14, 10, 2) == pytest.approx(2.0)

    def test_zero_std(self):
        assert _zscore(5, 10, 0) == 0.0

    def test_absolute(self):
        assert _zscore(6, 10, 2) == pytest.approx(2.0)


class TestHistogram:
    def test_basic(self):
        hist = _build_hour_histogram(_make_events(3, hour=14))
        assert hist[14] == 3

    def test_empty(self):
        assert _build_hour_histogram([]) == [0] * 24

    def test_missing_ts(self):
        assert sum(_build_hour_histogram([{"latitude": 40.0}])) == 0


class TestCentroid:
    def test_single(self):
        lat, lon = _geographic_centroid([{"latitude": 40.0, "longitude": -3.0}])
        assert lat == pytest.approx(40.0)

    def test_empty(self):
        assert _geographic_centroid([]) == (None, None)

    def test_missing_coords(self):
        assert _geographic_centroid([{"report_type": "X"}]) == (None, None)


class TestGeoSpread:
    def test_same_point(self):
        evts = [{"latitude": 40.0, "longitude": -3.0}] * 5
        assert _geo_spread_km(evts, 40.0, -3.0) == 0.0

    def test_empty(self):
        assert _geo_spread_km([], 40.0, -3.0) == 0.0


class TestStdDev:
    def test_uniform(self):
        assert _std_dev([5, 5, 5]) == 0.0

    def test_known(self):
        assert _std_dev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.0, abs=0.1)

    def test_empty(self):
        assert _std_dev([]) == 0.0


class TestTimeAnomalies:
    def test_too_few(self):
        r = detect_time_anomalies(_make_events(3))
        assert r["score"] == 0.0
        assert r["anomalies"] == []

    def test_normal(self):
        r = detect_time_anomalies(_make_events(20, hour=10))
        assert isinstance(r, dict)
        assert "score" in r

    def test_anomalous(self):
        evts = _make_events(20, hour=10)
        base_ms = int(datetime(2024, 2, 1, 3, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        evts.append(
            {
                "latitude": 40.4,
                "longitude": -3.7,
                "timestamp_ms": base_ms,
                "report_type": "POLICE",
            }
        )
        r = detect_time_anomalies(evts)
        assert isinstance(r, dict)


class TestLocationAnomalies:
    def test_too_few(self):
        r = detect_location_anomalies(_make_events(2))
        assert r["score"] == 0.0

    def test_outlier(self):
        evts = _make_events(20)
        evts.append(
            {
                "latitude": 51.5,
                "longitude": 0.1,
                "timestamp_ms": 1700000000000,
                "report_type": "X",
            }
        )
        r = detect_location_anomalies(evts)
        assert r["score"] > 0


class TestFrequencyAnomalies:
    def test_too_few(self):
        r = detect_frequency_anomalies(_make_events(3))
        assert r["score"] == 0.0
        assert r["anomalies"] == []

    def test_steady(self):
        r = detect_frequency_anomalies(_make_events(14, day_spread=1))
        assert r["score"] < 50


class TestDetectAnomalies:
    def test_empty(self):
        r = detect_anomalies([])
        assert r["anomaly_score"] == 0
        assert r["anomalies"] == []

    def test_single(self):
        r = detect_anomalies(_make_events(1))
        assert 0 <= r["anomaly_score"] <= 100

    def test_structure(self):
        r = detect_anomalies(_make_events(20))
        assert "anomaly_score" in r
        assert "anomalies" in r
        assert "sub_scores" in r
        for k in ("time", "location", "frequency"):
            assert k in r["sub_scores"]

    def test_with_routines(self):
        routines = {"HOME": {"latitude": 40.4, "longitude": -3.7, "confidence": 0.9}}
        r = detect_anomalies(_make_events(20), routines=routines)
        assert "anomaly_score" in r

    def test_bounds(self):
        r = detect_anomalies(_make_events(50))
        assert 0 <= r["anomaly_score"] <= 100
