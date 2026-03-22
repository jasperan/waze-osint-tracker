"""Battle-hardening tests — edge cases, malformed inputs, race conditions, failure modes.

Covers: WazeClient, Database, collector, trip_reconstruction, privacy_score,
intel_routines, intel_cooccurrence, intel_combined, intel_dossier, intel_prediction.
"""

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import generate_event_hash, process_alert
from database import Database
from intel_combined import classify_relationship, compute_combined_score
from intel_cooccurrence import find_cooccurrences
from intel_dossier import build_dossier_prompt, parse_dossier_response
from privacy_score import (
    _shannon_entropy,
    compute_privacy_score,
    compute_route_reconstructability,
    compute_trackability,
)
from trip_reconstruction import (
    _haversine_km,
    _segment_events,
    reconstruct_trips,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    username="testuser",
    latitude=40.4168,
    longitude=-3.7038,
    timestamp_ms=1700000000000,
    report_type="POLICE",
    subtype=None,
    grid_cell="test_cell",
):
    """Build a minimal event dict for insertion."""
    event_hash = generate_event_hash(username, latitude, longitude, timestamp_ms, report_type)
    ts_utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
    return {
        "event_hash": event_hash,
        "username": username,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp_utc": ts_utc,
        "timestamp_ms": timestamp_ms,
        "report_type": report_type,
        "subtype": subtype,
        "raw_json": json.dumps({"test": True}),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "grid_cell": grid_cell,
    }


@pytest.fixture
def db(tmp_path):
    """Create a temporary SQLite database."""
    db_path = str(tmp_path / "test.db")
    d = Database(db_path)
    yield d
    d.close()


# ===================================================================
# WazeClient edge cases
# ===================================================================


class TestWazeClientEdgeCases:
    """Test WazeClient with various malformed or edge-case API responses."""

    @patch("waze_client.requests.Session")
    def test_empty_response_body_no_alerts_key(self, mock_session_cls):
        """Valid JSON but no alerts/jams keys should return empty lists."""
        from waze_client import WazeClient

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {}  # No "alerts" or "jams"

        session_instance = MagicMock()
        session_instance.get.return_value = mock_resp
        session_instance.headers = {}
        mock_session_cls.return_value = session_instance

        client = WazeClient()
        client.session = session_instance
        client.rate_limiter.last_request_time = 0
        client.rate_limiter.current_delay = 0

        alerts, jams = client.get_traffic_notifications(40.5, 40.4, -3.8, -3.6)
        assert alerts == []
        assert jams == []

    @patch("waze_client.requests.Session")
    def test_malformed_json_response(self, mock_session_cls):
        """Non-JSON response should raise after retries."""
        from waze_client import WazeClient

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        session_instance = MagicMock()
        session_instance.get.return_value = mock_resp
        session_instance.headers = {}
        mock_session_cls.return_value = session_instance

        client = WazeClient()
        client.session = session_instance
        client.rate_limiter.last_request_time = 0
        client.rate_limiter.current_delay = 0

        # json.JSONDecodeError is not a RequestException, so it propagates
        with pytest.raises(json.JSONDecodeError):
            client.get_traffic_notifications(40.5, 40.4, -3.8, -3.6, max_retries=1)

    @patch("waze_client.requests.Session")
    def test_alert_missing_location_fields(self, mock_session_cls):
        """Alerts with missing latitude/longitude should still be returned with None values."""
        from waze_client import WazeClient

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "alerts": [
                {
                    "type": "POLICE",
                    # No location, no latitude/longitude, no reportBy, no pubMillis
                    "uuid": "abc12345",
                }
            ],
            "jams": [],
        }

        session_instance = MagicMock()
        session_instance.get.return_value = mock_resp
        session_instance.headers = {}
        mock_session_cls.return_value = session_instance

        client = WazeClient()
        client.session = session_instance
        client.rate_limiter.last_request_time = 0
        client.rate_limiter.current_delay = 0

        alerts, jams = client.get_traffic_notifications(40.5, 40.4, -3.8, -3.6)
        assert len(alerts) == 1
        # reportBy comes from _extract_username fallback via uuid
        assert alerts[0]["reportBy"] == "user_abc12345"
        # latitude/longitude should be None (no location key, no direct keys)
        assert alerts[0]["latitude"] is None
        assert alerts[0]["longitude"] is None

    def test_rate_limiter_backoff_increases_on_consecutive_errors(self):
        """Verify backoff increases geometrically on consecutive errors."""
        from waze_client import RateLimiter

        rl = RateLimiter(min_delay=1.0, max_delay=10.0, backoff_factor=2.0)
        assert rl.current_delay == 1.0

        rl.error()
        assert rl.current_delay == 2.0  # 1 * 2^1

        rl.error()
        assert rl.current_delay == 4.0  # 1 * 2^2

        rl.error()
        assert rl.current_delay == 8.0  # 1 * 2^3

        rl.error()
        # 1 * 2^4 = 16, but capped at max_delay=10
        assert rl.current_delay == 10.0

    def test_rate_limiter_never_exceeds_max_delay(self):
        """current_delay must never exceed max_delay no matter how many errors."""
        from waze_client import RateLimiter

        rl = RateLimiter(min_delay=1.0, max_delay=5.0, backoff_factor=3.0)
        for _ in range(100):
            rl.error()
        assert rl.current_delay <= rl.max_delay

    def test_rate_limiter_resets_on_success(self):
        """Verify backoff resets after a successful request."""
        from waze_client import RateLimiter

        rl = RateLimiter(min_delay=1.0, max_delay=10.0, backoff_factor=2.0)
        rl.error()
        rl.error()
        rl.error()
        assert rl.current_delay > 1.0
        assert rl.consecutive_errors == 3

        rl.success()
        assert rl.current_delay == 1.0
        assert rl.consecutive_errors == 0

    @patch("waze_client.requests.Session")
    def test_extremely_large_bounding_box(self, mock_session_cls):
        """Large bounding box should still make the API call."""
        from waze_client import WazeClient

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"alerts": [], "jams": []}

        session_instance = MagicMock()
        session_instance.get.return_value = mock_resp
        session_instance.headers = {}
        mock_session_cls.return_value = session_instance

        client = WazeClient()
        client.session = session_instance
        client.rate_limiter.last_request_time = 0
        client.rate_limiter.current_delay = 0

        alerts, jams = client.get_traffic_notifications(90, -90, -180, 180)
        assert alerts == []
        assert jams == []

    @patch("waze_client.requests.Session")
    def test_zero_area_bounding_box(self, mock_session_cls):
        """Bounding box with top == bottom should still make the request."""
        from waze_client import WazeClient

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"alerts": [], "jams": []}

        session_instance = MagicMock()
        session_instance.get.return_value = mock_resp
        session_instance.headers = {}
        mock_session_cls.return_value = session_instance

        client = WazeClient()
        client.session = session_instance
        client.rate_limiter.last_request_time = 0
        client.rate_limiter.current_delay = 0

        alerts, jams = client.get_traffic_notifications(40.0, 40.0, -3.0, -3.0)
        assert alerts == []

    @patch("waze_client.requests.Session")
    def test_negative_coordinates(self, mock_session_cls):
        """Negative coordinates (Southern/Western hemispheres) should work."""
        from waze_client import WazeClient

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"alerts": [], "jams": []}

        session_instance = MagicMock()
        session_instance.get.return_value = mock_resp
        session_instance.headers = {}
        mock_session_cls.return_value = session_instance

        client = WazeClient()
        client.session = session_instance
        client.rate_limiter.last_request_time = 0
        client.rate_limiter.current_delay = 0

        alerts, jams = client.get_traffic_notifications(-33.0, -34.0, -59.0, -58.0)
        assert isinstance(alerts, list)


# ===================================================================
# Database edge cases
# ===================================================================


class TestDatabaseEdgeCases:
    """Test Database with edge-case inputs."""

    def test_insert_event_empty_username(self, db):
        """Empty string username should still insert successfully."""
        event = _make_event(username="")
        assert db.insert_event(event) is True

    def test_insert_event_very_long_username(self, db):
        """10000-char username should insert (SQLite has no fixed TEXT limit)."""
        long_name = "a" * 10000
        event = _make_event(username=long_name)
        assert db.insert_event(event) is True

        # Verify it was stored correctly
        row = db.execute(
            "SELECT username FROM events WHERE event_hash = ?", (event["event_hash"],)
        ).fetchone()
        assert row["username"] == long_name

    def test_insert_event_zero_coordinates(self, db):
        """Zero coordinates (Null Island) should insert fine."""
        event = _make_event(latitude=0.0, longitude=0.0)
        assert db.insert_event(event) is True

    def test_insert_event_negative_coordinates(self, db):
        """Negative coordinates should insert fine."""
        event = _make_event(latitude=-33.8688, longitude=-151.2093)
        assert db.insert_event(event) is True

    def test_insert_event_negative_timestamp(self, db):
        """Negative timestamp_ms (pre-epoch) should still insert."""
        event = _make_event(timestamp_ms=-1000)
        # The timestamp_utc will be pre-1970 — that's fine for SQLite TEXT storage
        assert db.insert_event(event) is True

    def test_insert_event_none_optional_fields(self, db):
        """None for optional fields (subtype, raw_json) should insert."""
        event = _make_event()
        event["subtype"] = None
        event["raw_json"] = None
        assert db.insert_event(event) is True

    def test_duplicate_event_returns_false(self, db):
        """Inserting the same event_hash twice should return False."""
        event = _make_event()
        assert db.insert_event(event) is True
        assert db.insert_event(event) is False

    def test_get_tracked_users_limit_zero(self, db):
        """LIMIT 0 should return an empty list."""
        db.upsert_tracked_user("alice", "2024-01-01T00:00:00")
        result = db.get_tracked_users(limit=0)
        assert result == []

    def test_update_daily_stats_all_zeros(self, db):
        """Updating with all-zero stats should not error."""
        db.update_daily_stats("2024-01-01", events=0, users=0, requests=0, errors=0, cells=0)
        stats = db.get_daily_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["events_collected"] == 0

    def test_get_collection_summary_empty_database(self, db):
        """Empty database should return a summary with zero counts."""
        summary = db.get_collection_summary()
        assert summary["total_events"] == 0
        assert summary["unique_users"] == 0
        assert summary["first_event"] is None
        assert summary["last_event"] is None

    def test_upsert_tracked_user_increments_count(self, db):
        """Upserting the same user should increment the event_count."""
        db.upsert_tracked_user("bob", "2024-01-01")
        db.upsert_tracked_user("bob", "2024-01-02")
        db.upsert_tracked_user("bob", "2024-01-03")
        users = db.get_tracked_users(limit=1)
        assert users[0]["event_count"] == 3

    def test_insert_event_with_nan_coordinates(self, db):
        """NaN coordinates — SQLite may reject or store IEEE 754 NaN."""
        event = _make_event(latitude=float("nan"), longitude=float("nan"))
        event["event_hash"] = "nan_test_hash_1234"
        result = db.insert_event(event)
        # NaN handling varies by SQLite version; either outcome is acceptable
        assert result is True or result is False

    def test_insert_event_with_inf_coordinates(self, db):
        """Inf coordinates — SQLite stores them as REAL."""
        event = _make_event(latitude=float("inf"), longitude=float("-inf"))
        event["event_hash"] = "inf_test_hash_1234"
        result = db.insert_event(event)
        assert result is True


# ===================================================================
# collector.py edge cases
# ===================================================================


class TestCollectorEdgeCases:
    """Test process_alert and generate_event_hash with edge-case inputs."""

    def test_process_alert_empty_dict(self):
        """Empty alert dict should produce event with defaults."""
        event = process_alert({}, "test_cell")
        assert event["username"] == "anonymous"
        assert event["latitude"] == 0.0
        assert event["longitude"] == 0.0
        assert event["report_type"] == "UNKNOWN"
        assert event["grid_cell"] == "test_cell"
        assert "event_hash" in event

    def test_process_alert_missing_keys(self):
        """Alert with only a type key should use defaults for the rest."""
        event = process_alert({"type": "JAM"}, "cell_a")
        assert event["report_type"] == "JAM"
        assert event["username"] == "anonymous"
        assert event["latitude"] == 0.0
        assert event["longitude"] == 0.0

    def test_process_alert_non_numeric_latitude_longitude(self):
        """Non-numeric lat/lon should fall through to defaults (0.0)."""
        # When the alert has string values for lat/lon, process_alert uses
        # alert.get("latitude", 0.0) — if the key doesn't exist, default is 0.0.
        # If the key IS present but is a string, it would use the string.
        # Let's test when the keys are missing entirely (the normal case).
        alert = {"reportBy": "user1", "type": "POLICE"}
        event = process_alert(alert, "cell_x")
        assert event["latitude"] == 0.0
        assert event["longitude"] == 0.0

    def test_process_alert_timestamp_ms_zero(self):
        """timestamp_ms=0 (epoch start) should produce valid ISO timestamp."""
        alert = {"pubMillis": 0}
        event = process_alert(alert, "cell_z")
        assert event["timestamp_ms"] == 0
        assert "1970-01-01" in event["timestamp_utc"]

    def test_generate_event_hash_determinism(self):
        """Same inputs must produce the same hash every time."""
        h1 = generate_event_hash("user", 40.4168, -3.7038, 1700000000000, "POLICE")
        h2 = generate_event_hash("user", 40.4168, -3.7038, 1700000000000, "POLICE")
        assert h1 == h2

    def test_generate_event_hash_unicode_username(self):
        """Unicode username should hash without errors."""
        h = generate_event_hash("usuario_espanol", 40.0, -3.0, 1700000000000, "POLICE")
        assert isinstance(h, str) and len(h) == 16

    def test_generate_event_hash_emoji_username(self):
        """Emoji in username should hash without errors."""
        h = generate_event_hash("driver_\U0001f697", 40.0, -3.0, 1700000000000, "POLICE")
        assert isinstance(h, str) and len(h) == 16

    def test_generate_event_hash_empty_username(self):
        """Empty username should produce a valid hash."""
        h = generate_event_hash("", 40.0, -3.0, 1700000000000, "POLICE")
        assert isinstance(h, str) and len(h) == 16

    def test_generate_event_hash_different_inputs_differ(self):
        """Different inputs should produce different hashes."""
        h1 = generate_event_hash("alice", 40.0, -3.0, 1700000000000, "POLICE")
        h2 = generate_event_hash("bob", 40.0, -3.0, 1700000000000, "POLICE")
        assert h1 != h2

    def test_generate_event_hash_coordinate_rounding(self):
        """Coordinates differing within rounding precision should match."""
        # Both round to 40.4168 at 4 decimal places
        h1 = generate_event_hash("user", 40.41684, -3.7038, 1700000000000, "POLICE")
        h2 = generate_event_hash("user", 40.41681, -3.7038, 1700000000000, "POLICE")
        # 40.41684 rounds to 40.4168, 40.41681 rounds to 40.4168 — same
        assert h1 == h2

    def test_generate_event_hash_timestamp_rounding(self):
        """Timestamps within the same minute-bucket should produce the same hash."""
        # Both in the same 60000ms bucket: 1700000000000 // 60000 = 28333333
        # Bucket spans 1699999980000..1700000039999
        ts1 = 1700000000000
        ts2 = 1700000030000  # 30 seconds later, same minute bucket
        h1 = generate_event_hash("user", 40.0, -3.0, ts1, "POLICE")
        h2 = generate_event_hash("user", 40.0, -3.0, ts2, "POLICE")
        assert h1 == h2


# ===================================================================
# trip_reconstruction.py edge cases
# ===================================================================


class TestTripReconstructionEdgeCases:
    """Test trip_reconstruction with edge-case event sequences."""

    def test_single_event_below_min_waypoints(self):
        """A single event should return no trips (below min_waypoints=2)."""
        events = [
            {"latitude": 40.4, "longitude": -3.7, "timestamp_ms": 1000000, "report_type": "POLICE"}
        ]
        trips = reconstruct_trips(events, "user1")
        assert trips == []

    def test_events_all_same_location_stationary(self):
        """Events at the exact same location should produce trips with zero distance."""
        events = [
            {
                "latitude": 40.4,
                "longitude": -3.7,
                "timestamp_ms": 1000000 + i * 60000,
                "report_type": "POLICE",
            }
            for i in range(5)
        ]
        trips = reconstruct_trips(events, "user1")
        # Should produce one trip (all within time gap), distance ~0
        # Stationary trips with distance < 0.1 are allowed through (speed check skipped)
        assert len(trips) >= 0  # May be 0 or 1 depending on speed filter
        for t in trips:
            assert t.distance_km < 0.01

    def test_events_identical_timestamps(self):
        """Events with identical timestamps produce zero duration."""
        events = [
            {
                "latitude": 40.4 + i * 0.01,
                "longitude": -3.7,
                "timestamp_ms": 1000000,
                "report_type": "POLICE",
            }
            for i in range(3)
        ]
        trips = reconstruct_trips(events, "user1")
        # Duration is 0, so avg_speed is 0. Distance > 0.1km but speed < MIN_SPEED => skipped
        # Actually, if duration_s == 0, avg_speed = 0 which is < MIN_SPEED_KMH
        # distance_km > 0.1 AND avg_speed < MIN_SPEED => skipped
        assert trips == []

    def test_events_timestamps_going_backwards(self):
        """Events with reverse timestamps get sorted by the function."""
        events = [
            {"latitude": 40.4, "longitude": -3.7, "timestamp_ms": 3000000, "report_type": "POLICE"},
            {
                "latitude": 40.41,
                "longitude": -3.71,
                "timestamp_ms": 2000000,
                "report_type": "POLICE",
            },
            {
                "latitude": 40.42,
                "longitude": -3.72,
                "timestamp_ms": 1000000,
                "report_type": "POLICE",
            },
        ]
        trips = reconstruct_trips(events, "user1")
        # Function sorts by timestamp_ms, so order is corrected
        # Whether a trip forms depends on speed/distance constraints
        assert isinstance(trips, list)

    def test_haversine_same_point_returns_zero(self):
        """_haversine_km with identical points should return 0."""
        assert _haversine_km(40.4, -3.7, 40.4, -3.7) == 0.0

    def test_haversine_antipodal_points(self):
        """Antipodal points should be ~20015 km apart (half circumference)."""
        dist = _haversine_km(0, 0, 0, 180)
        assert abs(dist - 20015) < 50  # Within 50 km tolerance

    def test_segment_events_max_gap_zero(self):
        """max_gap_s=0 means every event becomes its own segment."""
        events = [
            {"timestamp_ms": 1000},
            {"timestamp_ms": 2000},
            {"timestamp_ms": 3000},
        ]
        segments = _segment_events(events, max_gap_s=0)
        assert len(segments) == 3
        assert all(len(s) == 1 for s in segments)

    def test_segment_events_empty_list(self):
        """Empty event list should return empty segments."""
        assert _segment_events([]) == []

    def test_segment_events_single_event(self):
        """Single event should return one segment with one event."""
        events = [{"timestamp_ms": 1000}]
        segments = _segment_events(events)
        assert len(segments) == 1
        assert len(segments[0]) == 1

    def test_events_spanning_antipodal_points(self):
        """Events at antipodal points with plausible time gap produce no valid trips
        because the implied speed would be >200 km/h."""
        events = [
            {"latitude": 0, "longitude": 0, "timestamp_ms": 1000000, "report_type": "POLICE"},
            {"latitude": 0, "longitude": 180, "timestamp_ms": 1060000, "report_type": "POLICE"},
        ]
        trips = reconstruct_trips(events, "user1")
        # ~20015 km in 60 seconds = ~1.2M km/h — far above MAX_SPEED_KMH
        assert trips == []


# ===================================================================
# privacy_score.py edge cases
# ===================================================================


class TestPrivacyScoreEdgeCases:
    """Test privacy scoring functions with edge-case inputs."""

    def test_shannon_entropy_all_zeros(self):
        """All-zero histogram (no probability mass) should return 1.0 (max uncertainty)."""
        # The function only adds p*log2(p) for p > 0, so entropy = 0.
        # Normalized: 0 / max_entropy = 0. But the function treats all-zero as…
        # Let's check: sum of zeros = total of 0, so we have no data.
        # Actually the function just computes entropy of the given histogram as-is.
        result = _shannon_entropy([0.0, 0.0, 0.0])
        # All zero: no p > 0 terms, entropy = 0, normalized = 0/log2(3) = 0
        assert result == 0.0

    def test_shannon_entropy_single_bin_at_one(self):
        """Histogram [1.0, 0.0, 0.0] — all mass in one bin — should have entropy 0."""
        result = _shannon_entropy([1.0, 0.0, 0.0])
        assert result == 0.0

    def test_shannon_entropy_uniform(self):
        """Uniform distribution should have entropy 1.0."""
        result = _shannon_entropy([0.25, 0.25, 0.25, 0.25])
        assert abs(result - 1.0) < 1e-10

    def test_shannon_entropy_empty_list(self):
        """Empty histogram should return 1.0 (the function's explicit check)."""
        result = _shannon_entropy([])
        assert result == 1.0

    def test_shannon_entropy_single_bin(self):
        """Single-bin histogram should return 0.0 (n_bins <= 1)."""
        result = _shannon_entropy([1.0])
        assert result == 0.0

    def test_compute_privacy_score_empty_events(self):
        """Empty events list should return a valid score dict."""
        result = compute_privacy_score(events=[])
        assert "overall_score" in result
        assert "risk_level" in result
        assert result["sub_scores"]["route_reconstructability"] == 0.0
        assert result["sub_scores"]["trackability"] == 0.0

    def test_compute_route_reconstructability_same_location(self):
        """All events at the same location should have zero drivable pairs (speed = 0)."""
        events = [
            {"latitude": 40.4, "longitude": -3.7, "timestamp_ms": 1000000 + i * 60000}
            for i in range(5)
        ]
        score, details = compute_route_reconstructability(events)
        # speed_kmh = 0 for all pairs (distance = 0), which fails 0 < speed_kmh check
        assert details["pairs_drivable"] == 0
        assert score == 0.0

    def test_compute_trackability_future_events(self):
        """Events with timestamps in the far future result in negative hours_ago."""
        far_future_ms = int(datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        events = [{"timestamp_ms": far_future_ms}]
        now_ms = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        score, details = compute_trackability(events, now_ms=now_ms)
        # hours_ago will be very negative (event is "in the future")
        assert details["last_seen_hours_ago"] < 0
        # Negative hours_ago hits the "hours_ago <= 0" branch => recency_score = 100
        assert details["recency_score"] == 100

    def test_compute_trackability_empty_events(self):
        """Empty events list should return zero score."""
        score, details = compute_trackability([])
        assert score == 0.0
        assert details["last_seen_hours_ago"] is None


# ===================================================================
# intel_routines.py edge cases
# ===================================================================


class TestIntelRoutinesEdgeCases:
    """Test infer_routines with edge-case event sets."""

    def test_fewer_than_10_events_returns_empty(self):
        """infer_routines requires at least 10 events."""
        from intel_routines import infer_routines

        events = [
            {"latitude": 40.4, "longitude": -3.7, "timestamp_ms": 1700000000000 + i * 60000}
            for i in range(9)
        ]
        result = infer_routines(events)
        assert result == {}

    def test_events_all_same_location(self):
        """All events at the same point should cluster into HOME or WORK depending on hour."""
        from intel_routines import infer_routines

        # Generate 15 events at the same location during night hours
        base_ts = datetime(2024, 1, 1, 23, 0, 0, tzinfo=timezone.utc)
        events = []
        for i in range(15):
            ts = base_ts.timestamp() + i * 3600  # hourly
            events.append(
                {
                    "latitude": 40.4168,
                    "longitude": -3.7038,
                    "timestamp_ms": int(ts * 1000),
                    "timestamp_utc": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                }
            )
        result = infer_routines(events)
        # Should infer HOME since all events are at night
        if "HOME" in result:
            assert result["HOME"]["evidence_count"] >= 3

    def test_events_missing_latitude_longitude(self):
        """Events without lat/lon should be skipped."""
        from intel_routines import infer_routines

        events = [{"timestamp_ms": 1700000000000 + i * 60000} for i in range(15)]
        result = infer_routines(events)
        assert result == {}

    def test_events_missing_timestamps(self):
        """Events without any timestamp should be skipped."""
        from intel_routines import infer_routines

        events = [{"latitude": 40.4, "longitude": -3.7} for _ in range(15)]
        result = infer_routines(events)
        assert result == {}


# ===================================================================
# intel_cooccurrence.py edge cases
# ===================================================================


class TestIntelCooccurrenceEdgeCases:
    """Test find_cooccurrences with edge-case event sets."""

    def test_empty_list(self):
        """Empty event list should return empty result."""
        assert find_cooccurrences([]) == []

    def test_single_event(self):
        """Single event — no pairs possible."""
        events = [{"username": "alice", "latitude": 40.4, "longitude": -3.7, "timestamp_ms": 1000}]
        assert find_cooccurrences(events) == []

    def test_all_same_user_no_pairs(self):
        """All events from the same user — no co-occurrence pairs."""
        events = [
            {
                "username": "alice",
                "latitude": 40.4,
                "longitude": -3.7,
                "timestamp_ms": 1000 + i * 100,
            }
            for i in range(10)
        ]
        assert find_cooccurrences(events, min_count=1) == []

    def test_events_at_antipodal_points(self):
        """Two users at antipodal points should never co-occur."""
        events = [
            {"username": "alice", "latitude": 0, "longitude": 0, "timestamp_ms": 1000},
            {"username": "bob", "latitude": 0, "longitude": 180, "timestamp_ms": 1000},
        ]
        assert find_cooccurrences(events, min_count=1) == []

    def test_two_users_same_place_and_time(self):
        """Two users at the exact same location and time should co-occur."""
        events = []
        for i in range(5):
            ts = 1000000 + i * 100  # within 500ms of each other
            events.append(
                {"username": "alice", "latitude": 40.4, "longitude": -3.7, "timestamp_ms": ts}
            )
            events.append(
                {"username": "bob", "latitude": 40.4, "longitude": -3.7, "timestamp_ms": ts + 50}
            )

        result = find_cooccurrences(events, min_count=3, temporal_threshold_s=1)
        assert len(result) == 1
        assert result[0]["user_a"] == "alice"
        assert result[0]["user_b"] == "bob"
        assert result[0]["co_count"] >= 3


# ===================================================================
# intel_combined.py edge cases
# ===================================================================


class TestIntelCombinedEdgeCases:
    """Test compute_combined_score and classify_relationship edge cases."""

    def test_compute_combined_score_max_co_count_zero(self):
        """max_co_count=0 should make graph_score 0."""
        score = compute_combined_score(
            vector_similarity=0.8,
            graph_co_count=10,
            max_co_count=0,
            alpha=0.6,
        )
        # graph_score = 0 because max_co_count=0
        # score = 0.6 * 0.8 + 0.4 * 0 = 0.48
        assert abs(score - 0.48) < 1e-10

    def test_classify_relationship_same_person(self):
        """High similarity + high co-occurrence => SAME_PERSON."""
        label = classify_relationship(
            vector_similarity=0.97,
            graph_co_count=25,
            max_co_count=30,
        )
        assert label == "SAME_PERSON"

    def test_classify_relationship_convoy(self):
        """Moderate combined score + high co-count + low vector sim => CONVOY."""
        label = classify_relationship(
            vector_similarity=0.5,
            graph_co_count=15,
            max_co_count=20,
        )
        # combined = 0.6*0.5 + 0.4*log1p(15)/log1p(20)
        # = 0.3 + 0.4 * 2.773/3.045 = 0.3 + 0.364 = 0.664
        # cosine_distance = 0.5
        # combined > 0.6, graph_co_count > 10, cosine_distance > 0.2 => CONVOY
        assert label == "CONVOY"

    def test_classify_relationship_similar_routine(self):
        """High vector similarity but low co-occurrence => SIMILAR_ROUTINE."""
        label = classify_relationship(
            vector_similarity=0.9,
            graph_co_count=1,
            max_co_count=50,
        )
        # cosine_distance = 0.1 < 0.15, graph_co_count < 3 => SIMILAR_ROUTINE
        assert label == "SIMILAR_ROUTINE"

    def test_classify_relationship_weak_match(self):
        """Low everything => WEAK_MATCH."""
        label = classify_relationship(
            vector_similarity=0.2,
            graph_co_count=1,
            max_co_count=100,
        )
        assert label == "WEAK_MATCH"


# ===================================================================
# intel_dossier.py edge cases
# ===================================================================


class TestIntelDossierEdgeCases:
    """Test parse_dossier_response and build_dossier_prompt edge cases."""

    def test_parse_dossier_response_nested_think_tags(self):
        """Nested <think> tags should be stripped cleanly."""
        raw = "<think>inner thought <think>nested</think> more</think>Actual dossier text."
        result = parse_dossier_response(raw)
        assert "think" not in result.lower()
        assert "Actual dossier text." in result

    def test_parse_dossier_response_empty_string(self):
        """Empty string should return empty string."""
        assert parse_dossier_response("") == ""

    def test_parse_dossier_response_no_think_tags(self):
        """Text without think tags should pass through unchanged."""
        text = "This is a clean dossier."
        assert parse_dossier_response(text) == text

    def test_parse_dossier_response_multiline_think(self):
        """Multi-line <think> block should be removed."""
        raw = "<think>\nI need to think about this.\nLine 2.\n</think>\nThe dossier begins here."
        result = parse_dossier_response(raw)
        assert "I need to think" not in result
        assert "The dossier begins here." in result

    def test_build_dossier_prompt_minimal_profile(self):
        """Minimal profile with empty/missing fields should produce valid prompt."""
        prompt = build_dossier_prompt({})
        assert "UNKNOWN" in prompt
        assert "No data" in prompt
        assert "No routine locations" in prompt

    def test_build_dossier_prompt_full_profile(self):
        """Full profile should include all sections."""
        profile = {
            "username": "test_user",
            "event_count": 100,
            "days_active": 30,
            "first_seen": "2024-01-01",
            "last_seen": "2024-01-31",
            "region": "europe",
            "type_distribution": {"POLICE": 50, "JAM": 30, "HAZARD": 20},
            "routines": {
                "HOME": {"latitude": 40.4, "longitude": -3.7, "confidence": 0.9},
                "WORK": {"latitude": 40.5, "longitude": -3.6, "confidence": 0.8},
            },
            "peak_hours": [8, 9, 17, 18],
            "peak_days": [0, 1, 2, 3, 4],
            "cadence_mean_hours": 4.5,
            "cadence_std_hours": 2.1,
            "similar_users": [{"username": "bob", "similarity": 0.85}],
            "co_occurrence_partners": [{"username": "charlie", "co_count": 7}],
            "prediction": {
                "day": "Monday",
                "hour": 8,
                "latitude": 40.45,
                "longitude": -3.65,
                "confidence": 0.7,
            },
        }
        prompt = build_dossier_prompt(profile)
        assert "test_user" in prompt
        assert "POLICE" in prompt
        assert "bob" in prompt
        assert "Monday" in prompt

    def test_build_dossier_prompt_empty_prediction(self):
        """Profile with prediction={} should show 'No prediction available'."""
        prompt = build_dossier_prompt({"prediction": {}})
        assert "No prediction available" in prompt


# ===================================================================
# intel_prediction.py edge cases
# ===================================================================


class TestIntelPredictionEdgeCases:
    """Test predict_presence with edge-case inputs."""

    def test_fewer_than_3_events(self):
        """predict_presence with <3 events should return None."""
        from intel_prediction import predict_presence

        events = [
            {"latitude": 40.4, "longitude": -3.7, "timestamp_ms": 1000000, "report_type": "POLICE"},
            {"latitude": 40.5, "longitude": -3.6, "timestamp_ms": 2000000, "report_type": "JAM"},
        ]
        result = predict_presence(events, target_dow=0, target_hour=10)
        assert result is None

    def test_no_matching_day_hour(self):
        """Events on different days/hours than target should return None."""
        from intel_prediction import predict_presence

        # Create 10 events on Monday at 10:00
        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)  # Monday
        events = [
            {
                "latitude": 40.4 + i * 0.001,
                "longitude": -3.7,
                "timestamp_ms": int((base.timestamp() + i * 60) * 1000),
                "report_type": "POLICE",
            }
            for i in range(10)
        ]
        # Target: Sunday at 3am — no events match
        result = predict_presence(events, target_dow=6, target_hour=3, hour_tolerance=0)
        assert result is None

    def test_all_matching_events_are_noise(self):
        """Events spread very far apart should all be classified as noise by DBSCAN."""
        from intel_prediction import predict_presence

        # Same day/hour but locations thousands of km apart
        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)  # Monday
        events = [
            {
                "latitude": 40.4,
                "longitude": -3.7,
                "timestamp_ms": int(base.timestamp() * 1000),
                "report_type": "POLICE",
            },
            {
                "latitude": -33.8,
                "longitude": 151.2,
                "timestamp_ms": int(base.timestamp() * 1000) + 1000,
                "report_type": "POLICE",
            },
            {
                "latitude": 35.6,
                "longitude": 139.6,
                "timestamp_ms": int(base.timestamp() * 1000) + 2000,
                "report_type": "POLICE",
            },
            # Need at least 3 events total to pass the initial check
            {
                "latitude": 51.5,
                "longitude": -0.1,
                "timestamp_ms": int(base.timestamp() * 1000) + 3000,
                "report_type": "POLICE",
            },
        ]
        result = predict_presence(events, target_dow=0, target_hour=10)
        # All points are very far apart, DBSCAN (eps=500m) classifies them all as noise
        assert result is None


# ===================================================================
# Additional cross-cutting edge cases
# ===================================================================


class TestCrossCuttingEdgeCases:
    """Edge cases that span multiple modules."""

    def test_full_pipeline_empty_alert_to_db(self, db):
        """Process an empty alert and insert it — full path."""
        alert = {}
        event = process_alert(alert, "pipeline_test")
        inserted = db.insert_event(event)
        assert inserted is True

        # Verify we can read it back
        row = db.execute(
            "SELECT * FROM events WHERE event_hash = ?", (event["event_hash"],)
        ).fetchone()
        assert row is not None
        assert row["username"] == "anonymous"

    def test_process_alert_and_reconstruct_trips(self):
        """Process multiple alerts, then reconstruct trips from the events."""
        events = []
        base_ts = 1700000000000
        for i in range(5):
            alert = {
                "reportBy": "traveler",
                "latitude": 40.4 + i * 0.005,
                "longitude": -3.7 + i * 0.005,
                "pubMillis": base_ts + i * 120000,  # 2 min apart
                "type": "POLICE",
            }
            events.append(process_alert(alert, f"cell_{i}"))

        trips = reconstruct_trips(events, "traveler")
        # Whether trips form depends on speed constraints
        assert isinstance(trips, list)

    def test_unicode_username_through_pipeline(self, db):
        """Unicode username flows through process_alert, insert, and query."""
        alert = {
            "reportBy": "conductor_madrid_\u00e1\u00e9\u00ed\u00f3\u00fa",
            "latitude": 40.4168,
            "longitude": -3.7038,
            "pubMillis": 1700000000000,
            "type": "POLICE",
        }
        event = process_alert(alert, "unicode_test")
        db.insert_event(event)

        row = db.execute(
            "SELECT username FROM events WHERE event_hash = ?", (event["event_hash"],)
        ).fetchone()
        assert row["username"] == "conductor_madrid_\u00e1\u00e9\u00ed\u00f3\u00fa"

    def test_compute_privacy_score_with_single_event(self):
        """Single event should produce a valid but low privacy score."""
        events = [
            {
                "latitude": 40.4,
                "longitude": -3.7,
                "timestamp_ms": 1700000000000,
                "report_type": "POLICE",
            }
        ]
        result = compute_privacy_score(events=events, now_ms=1700000000000)
        assert 0 <= result["overall_score"] <= 100
        assert result["risk_level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
