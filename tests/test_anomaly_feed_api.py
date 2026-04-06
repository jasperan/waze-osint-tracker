"""Tests for the /api/anomalies endpoint in web/app.py."""

from unittest.mock import patch

import pytest

# Import the Flask app
from web.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestApiAnomalies:
    @patch("web.app._anomaly_feed")
    def test_returns_correct_shape(self, mock_feed, client):
        mock_feed.get_recent.return_value = [
            {
                "username": "user1",
                "anomaly_type": "time",
                "score": 75.0,
                "timestamp": "2025-01-01T00:00:00+00:00",
                "geofence_name": None,
                "lat": 40.4,
                "lon": -3.7,
            }
        ]
        resp = client.get("/api/anomalies")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "anomalies" in data
        assert "count" in data
        assert data["count"] == 1
        assert data["anomalies"][0]["username"] == "user1"

    @patch("web.app._anomaly_feed")
    def test_limit_parameter(self, mock_feed, client):
        mock_feed.get_recent.return_value = []
        resp = client.get("/api/anomalies?limit=10")
        assert resp.status_code == 200
        mock_feed.get_recent.assert_called_once_with(10)

    @patch("web.app._anomaly_feed")
    def test_limit_capped_at_500(self, mock_feed, client):
        mock_feed.get_recent.return_value = []
        resp = client.get("/api/anomalies?limit=9999")
        assert resp.status_code == 200
        mock_feed.get_recent.assert_called_once_with(500)

    @patch("web.app._anomaly_feed")
    def test_no_data_returns_empty(self, mock_feed, client):
        mock_feed.get_recent.return_value = []
        resp = client.get("/api/anomalies")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["anomalies"] == []
        assert data["count"] == 0

    @patch("web.app._anomaly_feed")
    def test_default_limit_is_100(self, mock_feed, client):
        mock_feed.get_recent.return_value = []
        resp = client.get("/api/anomalies")
        assert resp.status_code == 200
        mock_feed.get_recent.assert_called_once_with(100)
