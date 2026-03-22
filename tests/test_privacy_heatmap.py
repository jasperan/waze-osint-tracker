"""Tests for privacy_heatmap module."""

from privacy_heatmap import (
    _cell_center,
    _grid_key,
    _km_per_deg_lon,
    _sigmoid_scale,
    generate_privacy_heatmap,
)


def _make_event(lat, lon, ts_ms, username="user1", report_type="POLICE"):
    return {
        "latitude": lat,
        "longitude": lon,
        "timestamp_ms": ts_ms,
        "username": username,
        "report_type": report_type,
    }


def _madrid_events():
    """Realistic cluster of events across central Madrid with multiple users."""
    events = []
    base = 1700000000000
    users = ["alice", "bob", "carol", "dave", "eve"]
    for day in range(7):
        for i, user in enumerate(users):
            ts = base + day * 86_400_000 + i * 3_600_000
            lat = 40.42 + (i % 3) * 0.002
            lon = -3.70 + (i % 4) * 0.002
            events.append(_make_event(lat, lon, ts, user))
    return events


def _sparse_events():
    """Events spread across a large area, one per cell."""
    events = []
    base = 1700000000000
    for i in range(10):
        events.append(_make_event(40.0 + i * 0.5, -3.0 + i * 0.5, base + i * 3_600_000, f"user{i}"))
    return events


class TestKmPerDegLon:
    def test_equator(self):
        km = _km_per_deg_lon(0.0)
        assert abs(km - 111.0) < 1.0

    def test_pole(self):
        km = _km_per_deg_lon(90.0)
        assert km < 0.1

    def test_mid_latitude(self):
        km = _km_per_deg_lon(40.0)
        assert 80 < km < 90


class TestGridKey:
    def test_positive_coords(self):
        row, col = _grid_key(40.42, -3.70, 0.01, 0.01)
        assert isinstance(row, int)
        assert isinstance(col, int)

    def test_different_cells(self):
        k1 = _grid_key(40.42, -3.70, 0.01, 0.01)
        k2 = _grid_key(40.43, -3.70, 0.01, 0.01)
        assert k1 != k2


class TestCellCenter:
    def test_basic(self):
        lat, lon = _cell_center(4042, -370, 0.01, 0.01)
        assert isinstance(lat, float)
        assert isinstance(lon, float)


class TestSigmoidScale:
    def test_at_midpoint(self):
        val = _sigmoid_scale(5.0, 5.0)
        assert abs(val - 0.5) < 0.01

    def test_high_value(self):
        val = _sigmoid_scale(100.0, 5.0)
        assert val > 0.99

    def test_low_value(self):
        val = _sigmoid_scale(-100.0, 5.0)
        assert val < 0.01


class TestGeneratePrivacyHeatmap:
    def test_empty_events(self):
        result = generate_privacy_heatmap([])
        assert result["total_cells"] == 0
        assert result["cells"] == []

    def test_single_event(self):
        events = [_make_event(40.42, -3.70, 1000)]
        result = generate_privacy_heatmap(events)
        assert result["total_cells"] == 1
        cell = result["cells"][0]
        assert cell["unique_users"] == 1
        assert cell["total_events"] == 1
        assert cell["repeat_ratio"] == 0.0

    def test_repeat_visitors_detected(self):
        events = [_make_event(40.42, -3.70, 1000 + i * 1000, "alice") for i in range(10)]
        result = generate_privacy_heatmap(events, grid_size_km=1.0)
        assert result["total_cells"] >= 1
        cell = result["cells"][0]
        assert cell["unique_users"] == 1
        assert cell["avg_events_per_user"] == 10.0

    def test_multiple_users_same_cell(self):
        events = [
            _make_event(40.42, -3.70, 1000, "alice"),
            _make_event(40.42, -3.70, 2000, "bob"),
            _make_event(40.42, -3.70, 3000, "carol"),
        ]
        result = generate_privacy_heatmap(events, grid_size_km=5.0)
        assert result["total_cells"] >= 1
        cell = result["cells"][0]
        assert cell["unique_users"] == 3

    def test_cells_sorted_by_risk(self):
        events = _madrid_events()
        result = generate_privacy_heatmap(events, grid_size_km=0.5)
        scores = [c["risk_score"] for c in result["cells"]]
        assert scores == sorted(scores, reverse=True)

    def test_bounds_computed(self):
        events = _madrid_events()
        result = generate_privacy_heatmap(events)
        bounds = result["bounds"]
        assert "min_lat" in bounds
        assert "max_lat" in bounds
        assert bounds["min_lat"] <= bounds["max_lat"]

    def test_stats_computed(self):
        events = _madrid_events()
        result = generate_privacy_heatmap(events)
        stats = result["stats"]
        assert "avg_risk_score" in stats
        assert "max_risk_score" in stats
        assert stats["total_events"] == len(events)

    def test_grid_size_affects_cell_count(self):
        events = _madrid_events()
        small = generate_privacy_heatmap(events, grid_size_km=0.1)
        large = generate_privacy_heatmap(events, grid_size_km=10.0)
        assert small["total_cells"] >= large["total_cells"]

    def test_no_coords_skipped(self):
        events = [{"timestamp_ms": 1000, "username": "alice"}]
        result = generate_privacy_heatmap(events)
        assert result["total_cells"] == 0

    def test_anonymous_users_handled(self):
        events = [
            {"latitude": 40.42, "longitude": -3.70, "timestamp_ms": 1000},
            {"latitude": 40.42, "longitude": -3.70, "timestamp_ms": 2000},
        ]
        result = generate_privacy_heatmap(events, grid_size_km=5.0)
        assert result["total_cells"] >= 1
        assert result["cells"][0]["unique_users"] == 1

    def test_risk_score_range(self):
        events = _madrid_events() + _sparse_events()
        result = generate_privacy_heatmap(events, grid_size_km=0.5)
        for cell in result["cells"]:
            assert 0 <= cell["risk_score"] <= 100

    def test_regular_user_ratio(self):
        base = 1700000000000
        events = []
        for day in range(5):
            events.append(_make_event(40.42, -3.70, base + day * 86_400_000, "alice"))
        events.append(_make_event(40.42, -3.70, base + 1000, "bob"))

        result = generate_privacy_heatmap(events, grid_size_km=5.0)
        cell = result["cells"][0]
        assert cell["regular_user_ratio"] == 0.5
