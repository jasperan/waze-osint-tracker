"""Tests for velocity_tracker module."""

from velocity_tracker import find_event_waves, summarize_waves


def _make_event(lat, lon, ts_ms, report_type="POLICE"):
    return {
        "latitude": lat,
        "longitude": lon,
        "timestamp_ms": ts_ms,
        "report_type": report_type,
    }


def _police_wave_events():
    """A wave of police reports spreading east along a highway over 20 minutes."""
    base = 1700000000000
    return [
        _make_event(40.42, -3.70, base, "POLICE"),
        _make_event(40.42, -3.68, base + 300_000, "POLICE"),
        _make_event(40.42, -3.66, base + 600_000, "POLICE"),
        _make_event(40.42, -3.64, base + 900_000, "POLICE"),
    ]


def _mixed_type_events():
    """Different event types near each other."""
    base = 1700000000000
    return [
        _make_event(40.42, -3.70, base, "POLICE"),
        _make_event(40.42, -3.69, base + 300_000, "POLICE"),
        _make_event(40.42, -3.70, base + 100_000, "JAM"),
        _make_event(40.42, -3.69, base + 400_000, "JAM"),
    ]


class TestFindEventWaves:
    def test_empty_events(self):
        assert find_event_waves([]) == []

    def test_single_event(self):
        events = [_make_event(40.0, -3.0, 1000)]
        assert find_event_waves(events) == []

    def test_detects_police_wave(self):
        events = _police_wave_events()
        waves = find_event_waves(events, wave_radius_km=5.0, wave_window_s=1800)
        assert len(waves) == 1
        wave = waves[0]
        assert wave["event_type"] == "POLICE"
        assert len(wave["events"]) >= 3
        assert wave["spread_km"] > 0
        assert wave["duration_s"] > 0
        assert wave["velocity_kmh"] > 0

    def test_wave_has_origin(self):
        events = _police_wave_events()
        waves = find_event_waves(events)
        wave = waves[0]
        assert "lat" in wave["origin"]
        assert "lon" in wave["origin"]
        assert abs(wave["origin"]["lat"] - 40.42) < 0.01

    def test_separate_types_form_separate_waves(self):
        events = _mixed_type_events()
        waves = find_event_waves(events, wave_radius_km=5.0, wave_window_s=1800)
        types = {w["event_type"] for w in waves}
        assert "POLICE" in types
        assert "JAM" in types

    def test_events_outside_radius_excluded(self):
        base = 1700000000000
        events = [
            _make_event(40.42, -3.70, base, "POLICE"),
            _make_event(40.42, -3.50, base + 300_000, "POLICE"),
        ]
        waves = find_event_waves(events, wave_radius_km=5.0)
        wave_with_both = [w for w in waves if len(w["events"]) == 2]
        assert len(wave_with_both) == 0

    def test_events_outside_time_window_excluded(self):
        base = 1700000000000
        events = [
            _make_event(40.42, -3.70, base, "POLICE"),
            _make_event(40.42, -3.69, base + 7200_000, "POLICE"),
        ]
        waves = find_event_waves(events, wave_window_s=1800)
        wave_with_both = [w for w in waves if len(w["events"]) == 2]
        assert len(wave_with_both) == 0

    def test_wave_id_is_unique(self):
        events = _mixed_type_events()
        waves = find_event_waves(events)
        ids = [w["wave_id"] for w in waves]
        assert len(ids) == len(set(ids))

    def test_velocity_calculation(self):
        events = _police_wave_events()
        waves = find_event_waves(events)
        wave = waves[0]
        assert 5 < wave["velocity_kmh"] < 40

    def test_missing_fields_skipped(self):
        events = [
            {"timestamp_ms": 1000},
            {"latitude": 40.0, "longitude": -3.0},
            _make_event(40.0, -3.0, 1000, "POLICE"),
        ]
        waves = find_event_waves(events)
        assert isinstance(waves, list)

    def test_custom_radius_and_window(self):
        base = 1700000000000
        events = [
            _make_event(40.42, -3.70, base, "POLICE"),
            _make_event(40.42, -3.60, base + 600_000, "POLICE"),
        ]
        narrow = find_event_waves(events, wave_radius_km=5.0)
        narrow_with_both = [w for w in narrow if len(w["events"]) == 2]
        assert len(narrow_with_both) == 0

        wide = find_event_waves(events, wave_radius_km=10.0)
        wide_with_both = [w for w in wide if len(w["events"]) == 2]
        assert len(wide_with_both) == 1

    def test_wave_fields_structure(self):
        events = _police_wave_events()
        waves = find_event_waves(events)
        assert len(waves) >= 1
        w = waves[0]
        for key in (
            "wave_id",
            "event_type",
            "origin",
            "events",
            "spread_km",
            "duration_s",
            "velocity_kmh",
        ):
            assert key in w

    def test_zero_duration_wave(self):
        base = 1700000000000
        events = [
            _make_event(40.42, -3.70, base, "POLICE"),
            _make_event(40.42, -3.69, base, "POLICE"),
        ]
        waves = find_event_waves(events)
        if waves:
            assert waves[0]["velocity_kmh"] == 0


class TestSummarizeWaves:
    def test_empty_waves(self):
        summary = summarize_waves([])
        assert summary["total_waves"] == 0
        assert summary["total_events_in_waves"] == 0

    def test_basic_summary(self):
        events = _police_wave_events()
        waves = find_event_waves(events)
        summary = summarize_waves(waves)
        assert summary["total_waves"] == 1
        assert summary["total_events_in_waves"] >= 3
        assert summary["avg_wave_size"] >= 3.0
        assert "POLICE" in summary["by_type"]

    def test_mixed_type_summary(self):
        events = _mixed_type_events()
        waves = find_event_waves(events)
        summary = summarize_waves(waves)
        assert summary["total_waves"] >= 2
        assert "POLICE" in summary["by_type"]
