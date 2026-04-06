"""Tests for the AnomalyFeed micro-batch streaming adapter."""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from anomaly_feed import AnomalyFeed


def _make_event(username="user1", lat=40.4168, lon=-3.7038, hours_ago=0, report_type="POLICE"):
    """Create a minimal event dict for testing."""
    ts = int((time.time() - hours_ago * 3600) * 1000)
    return {
        "username": username,
        "latitude": lat,
        "longitude": lon,
        "timestamp_ms": ts,
        "report_type": report_type,
    }


def _make_events(n=20, username="user1", lat=40.4168, lon=-3.7038):
    """Generate n events spread over hours for a single user."""
    return [_make_event(username, lat, lon, hours_ago=i) for i in range(n)]


class TestAnomalyFeedInit:
    def test_default_window_size(self):
        feed = AnomalyFeed()
        assert feed._window.maxlen == 1000

    def test_custom_window_size(self):
        feed = AnomalyFeed(window_size=50)
        assert feed._window.maxlen == 50

    def test_recent_anomalies_starts_empty(self):
        feed = AnomalyFeed()
        assert feed.get_recent() == []


class TestCheckBatchEmpty:
    def test_empty_events_returns_empty(self):
        feed = AnomalyFeed()
        assert feed.check_batch([]) == []

    def test_none_like_empty(self):
        feed = AnomalyFeed()
        assert feed.check_batch([]) == []


class TestSlidingWindow:
    def test_window_grows(self):
        feed = AnomalyFeed(window_size=100)
        events = _make_events(10)
        feed.check_batch(events)
        assert len(feed._window) == 10

    def test_window_caps_at_max(self):
        feed = AnomalyFeed(window_size=5)
        events = _make_events(10)
        feed.check_batch(events)
        assert len(feed._window) == 5

    def test_multiple_batches_accumulate(self):
        feed = AnomalyFeed(window_size=100)
        feed.check_batch(_make_events(5))
        feed.check_batch(_make_events(5))
        assert len(feed._window) == 10


class TestCheckBatchWithAnomalies:
    @patch("anomaly_detection.detect_anomalies")
    def test_returns_alerts_for_anomalies(self, mock_detect):
        events = _make_events(5)
        mock_detect.return_value = {
            "anomaly_score": 75.0,
            "anomalies": [
                {
                    "type": "time",
                    "score": 75.0,
                    "details": {"timestamp_ms": events[0]["timestamp_ms"], "hour": 3},
                }
            ],
            "sub_scores": {"time": 75.0, "location": 0.0, "frequency": 0.0},
        }

        feed = AnomalyFeed()
        alerts = feed.check_batch(events)

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["username"] == "user1"
        assert alert["anomaly_type"] == "time"
        assert alert["score"] == 75.0
        assert alert["geofence_name"] is None
        assert "timestamp" in alert
        assert "lat" in alert
        assert "lon" in alert

    @patch("anomaly_detection.detect_anomalies")
    def test_no_anomalies_returns_empty(self, mock_detect):
        mock_detect.return_value = {
            "anomaly_score": 0.0,
            "anomalies": [],
            "sub_scores": {"time": 0.0, "location": 0.0, "frequency": 0.0},
        }
        feed = AnomalyFeed()
        alerts = feed.check_batch(_make_events(3))
        assert alerts == []

    @patch("anomaly_detection.detect_anomalies")
    def test_location_anomaly_matching(self, mock_detect):
        events = [_make_event("bob", lat=41.0, lon=-4.0)]
        mock_detect.return_value = {
            "anomaly_score": 60.0,
            "anomalies": [
                {
                    "type": "location",
                    "score": 60.0,
                    "details": {"latitude": 41.0, "longitude": -4.0, "distance_km": 50.0},
                }
            ],
            "sub_scores": {"time": 0.0, "location": 60.0, "frequency": 0.0},
        }
        feed = AnomalyFeed()
        alerts = feed.check_batch(events)
        assert len(alerts) == 1
        assert alerts[0]["anomaly_type"] == "location"
        assert alerts[0]["username"] == "bob"

    @patch("anomaly_detection.detect_anomalies")
    def test_frequency_anomaly_matching(self, mock_detect):
        events = _make_events(3)
        day_str = datetime.fromtimestamp(
            events[0]["timestamp_ms"] / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d")
        mock_detect.return_value = {
            "anomaly_score": 50.0,
            "anomalies": [
                {
                    "type": "frequency",
                    "score": 50.0,
                    "details": {"date": day_str, "event_count": 100, "direction": "spike"},
                }
            ],
            "sub_scores": {"time": 0.0, "location": 0.0, "frequency": 50.0},
        }
        feed = AnomalyFeed()
        alerts = feed.check_batch(events)
        assert len(alerts) == 1
        assert alerts[0]["anomaly_type"] == "frequency"


class TestGeofenceIntegration:
    @patch("anomaly_detection.detect_anomalies")
    def test_geofence_name_included(self, mock_detect):
        events = [_make_event("alice", lat=40.42, lon=-3.70)]
        mock_detect.return_value = {
            "anomaly_score": 80.0,
            "anomalies": [
                {
                    "type": "time",
                    "score": 80.0,
                    "details": {"timestamp_ms": events[0]["timestamp_ms"], "hour": 2},
                }
            ],
            "sub_scores": {"time": 80.0, "location": 0.0, "frequency": 0.0},
        }

        mock_gfm = MagicMock()
        mock_gfm.check_event.return_value = [{"geofence_name": "Madrid Centro"}]

        feed = AnomalyFeed()
        feed._geofence_mgr = mock_gfm

        alerts = feed.check_batch(events)
        assert len(alerts) == 1
        assert alerts[0]["geofence_name"] == "Madrid Centro"

    @patch("anomaly_detection.detect_anomalies")
    def test_geofence_none_when_not_triggered(self, mock_detect):
        events = [_make_event("bob")]
        mock_detect.return_value = {
            "anomaly_score": 55.0,
            "anomalies": [
                {
                    "type": "location",
                    "score": 55.0,
                    "details": {
                        "latitude": events[0]["latitude"],
                        "longitude": events[0]["longitude"],
                    },
                }
            ],
            "sub_scores": {"time": 0.0, "location": 55.0, "frequency": 0.0},
        }

        mock_gfm = MagicMock()
        mock_gfm.check_event.return_value = []

        feed = AnomalyFeed()
        feed._geofence_mgr = mock_gfm

        alerts = feed.check_batch(events)
        assert len(alerts) == 1
        assert alerts[0]["geofence_name"] is None


class TestGetRecent:
    def test_empty_returns_empty(self):
        feed = AnomalyFeed()
        assert feed.get_recent() == []

    def test_limit_respected(self):
        feed = AnomalyFeed()
        for i in range(10):
            feed._recent_anomalies.append({"score": i})
        result = feed.get_recent(limit=3)
        assert len(result) == 3
        # Should be the last 3
        assert result[0]["score"] == 7
        assert result[2]["score"] == 9

    def test_returns_copy(self):
        feed = AnomalyFeed()
        feed._recent_anomalies.append({"score": 42})
        result = feed.get_recent()
        result.clear()
        assert len(feed._recent_anomalies) == 1


class TestAlertFields:
    @patch("anomaly_detection.detect_anomalies")
    def test_alert_has_required_fields(self, mock_detect):
        events = [_make_event("testuser", lat=40.0, lon=-3.5)]
        mock_detect.return_value = {
            "anomaly_score": 90.0,
            "anomalies": [
                {
                    "type": "time",
                    "score": 90.0,
                    "details": {"timestamp_ms": events[0]["timestamp_ms"], "hour": 4},
                }
            ],
            "sub_scores": {"time": 90.0, "location": 0.0, "frequency": 0.0},
        }
        feed = AnomalyFeed()
        alerts = feed.check_batch(events)
        assert len(alerts) == 1
        required_keys = {
            "username",
            "anomaly_type",
            "score",
            "timestamp",
            "geofence_name",
            "lat",
            "lon",
        }
        assert required_keys.issubset(set(alerts[0].keys()))
