"""Tests for trip reconstruction engine."""

from trip_reconstruction import (
    _classify_trip,
    _compute_segment_distance,
    _generate_trip_id,
    _haversine_km,
    _segment_events,
    get_trip_summary,
    reconstruct_trips,
)

# --- Fixtures ---


def _make_event(lat, lon, ts_ms, report_type="POLICE"):
    return {
        "latitude": lat,
        "longitude": lon,
        "timestamp_ms": ts_ms,
        "report_type": report_type,
    }


def _madrid_commute_events():
    """Simulate a morning commute across Madrid: home (south) -> work (north).
    ~10 km over ~30 minutes, 3 waypoints."""
    base_ts = 1700000000000  # some fixed timestamp
    return [
        _make_event(40.38, -3.72, base_ts, "POLICE"),  # Usera (south)
        _make_event(40.42, -3.70, base_ts + 600_000, "JAM"),  # Centro (+10 min)
        _make_event(40.46, -3.69, base_ts + 1_800_000, "POLICE"),  # Chamartin (+30 min)
    ]


def _two_trip_events():
    """Two distinct trips separated by a 3-hour gap."""
    base = 1700000000000
    return [
        # Trip 1: 2 waypoints over 15 min
        _make_event(40.38, -3.72, base, "POLICE"),
        _make_event(40.40, -3.70, base + 900_000, "JAM"),
        # Gap: 3 hours
        # Trip 2: 2 waypoints over 20 min
        _make_event(40.45, -3.68, base + 11_700_000, "HAZARD"),
        _make_event(40.47, -3.66, base + 12_900_000, "POLICE"),
    ]


# --- Unit tests ---


class TestHaversine:
    def test_same_point_is_zero(self):
        assert _haversine_km(40.0, -3.0, 40.0, -3.0) == 0.0

    def test_known_distance(self):
        # Madrid to Barcelona is ~504 km
        dist = _haversine_km(40.4168, -3.7038, 41.3874, 2.1686)
        assert 490 < dist < 520

    def test_short_distance(self):
        # Two points ~1km apart in Madrid
        dist = _haversine_km(40.4168, -3.7038, 40.4258, -3.7038)
        assert 0.5 < dist < 1.5


class TestSegmentation:
    def test_single_segment(self):
        events = _madrid_commute_events()
        segments = _segment_events(events)
        assert len(segments) == 1
        assert len(segments[0]) == 3

    def test_two_segments(self):
        events = _two_trip_events()
        segments = _segment_events(events)
        assert len(segments) == 2
        assert len(segments[0]) == 2
        assert len(segments[1]) == 2

    def test_empty_events(self):
        assert _segment_events([]) == []

    def test_single_event(self):
        events = [_make_event(40.0, -3.0, 1000)]
        segments = _segment_events(events)
        assert len(segments) == 1

    def test_custom_gap(self):
        base = 1000000
        events = [
            _make_event(40.0, -3.0, base),
            _make_event(40.1, -3.1, base + 600_000),  # 10 min gap
        ]
        # With 5-minute max gap, should split
        segments = _segment_events(events, max_gap_s=300)
        assert len(segments) == 2


class TestSegmentDistance:
    def test_zero_for_single_point(self):
        wp = [{"latitude": 40.0, "longitude": -3.0}]
        assert _compute_segment_distance(wp) == 0.0

    def test_positive_for_two_points(self):
        wp = [
            {"latitude": 40.38, "longitude": -3.72},
            {"latitude": 40.46, "longitude": -3.69},
        ]
        dist = _compute_segment_distance(wp)
        assert dist > 0


class TestTripClassification:
    def test_morning_commute(self):
        routines = {
            "HOME": {"latitude": 40.38, "longitude": -3.72},
            "WORK": {"latitude": 40.46, "longitude": -3.69},
        }
        result = _classify_trip((40.38, -3.72), (40.46, -3.69), routines)
        assert result == "MORNING_COMMUTE"

    def test_evening_commute(self):
        routines = {
            "HOME": {"latitude": 40.38, "longitude": -3.72},
            "WORK": {"latitude": 40.46, "longitude": -3.69},
        }
        result = _classify_trip((40.46, -3.69), (40.38, -3.72), routines)
        assert result == "EVENING_COMMUTE"

    def test_round_trip(self):
        routines = {
            "HOME": {"latitude": 40.38, "longitude": -3.72},
            "WORK": {"latitude": 40.46, "longitude": -3.69},
        }
        result = _classify_trip((40.38, -3.72), (40.38, -3.72), routines)
        assert result == "ROUND_TRIP"

    def test_no_routines(self):
        assert _classify_trip((40.0, -3.0), (41.0, -2.0), None) == "OTHER"

    def test_other_when_no_match(self):
        routines = {
            "HOME": {"latitude": 0.0, "longitude": 0.0},
            "WORK": {"latitude": 0.0, "longitude": 0.0},
        }
        result = _classify_trip((40.38, -3.72), (40.46, -3.69), routines)
        assert result == "OTHER"


class TestTripId:
    def test_deterministic(self):
        id1 = _generate_trip_id("alice", 1000, 2000)
        id2 = _generate_trip_id("alice", 1000, 2000)
        assert id1 == id2

    def test_different_for_different_input(self):
        id1 = _generate_trip_id("alice", 1000, 2000)
        id2 = _generate_trip_id("bob", 1000, 2000)
        assert id1 != id2

    def test_length(self):
        tid = _generate_trip_id("user", 100, 200)
        assert len(tid) == 16


class TestReconstructTrips:
    def test_single_commute(self):
        events = _madrid_commute_events()
        trips = reconstruct_trips(events, "testuser")
        assert len(trips) == 1
        trip = trips[0]
        assert trip.username == "testuser"
        assert trip.waypoint_count == 3
        assert trip.distance_km > 0
        assert trip.duration_minutes > 0
        assert trip.avg_speed_kmh > 0

    def test_two_trips(self):
        events = _two_trip_events()
        trips = reconstruct_trips(events, "testuser")
        assert len(trips) == 2

    def test_with_classification(self):
        events = _madrid_commute_events()
        routines = {
            "HOME": {"latitude": 40.38, "longitude": -3.72},
            "WORK": {"latitude": 40.46, "longitude": -3.69},
        }
        trips = reconstruct_trips(events, "testuser", routines=routines)
        assert len(trips) == 1
        assert trips[0].trip_type == "MORNING_COMMUTE"

    def test_insufficient_events(self):
        events = [_make_event(40.0, -3.0, 1000)]
        trips = reconstruct_trips(events, "testuser")
        assert trips == []

    def test_empty_events(self):
        trips = reconstruct_trips([], "testuser")
        assert trips == []

    def test_trip_to_dict(self):
        events = _madrid_commute_events()
        trips = reconstruct_trips(events, "testuser")
        d = trips[0].to_dict()
        assert isinstance(d, dict)
        assert "trip_id" in d
        assert "waypoints" in d


class TestTripSummary:
    def test_summary_with_trips(self):
        events = _two_trip_events()
        trips = reconstruct_trips(events, "testuser")
        summary = get_trip_summary(trips)
        assert summary["total_trips"] == len(trips)
        assert summary["total_distance_km"] > 0
        assert summary["most_common_type"] is not None

    def test_summary_empty(self):
        summary = get_trip_summary([])
        assert summary["total_trips"] == 0
        assert summary["most_common_type"] is None
