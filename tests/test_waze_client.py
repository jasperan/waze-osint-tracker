# tests/test_waze_client.py
import pytest
from unittest.mock import patch, Mock
from waze_client import WazeClient

def test_get_traffic_notifications_parses_response():
    mock_response = Mock()
    mock_response.json.return_value = {
        "alerts": [
            {
                "type": "POLICE",
                "subtype": "POLICE_VISIBLE",
                "latitude": 40.42,
                "longitude": -3.70,
                "country": "ES",
                "reportBy": "testuser123"
            }
        ],
        "jams": []
    }
    mock_response.raise_for_status = Mock()

    with patch("requests.get", return_value=mock_response):
        client = WazeClient("http://localhost:8080")
        alerts, jams = client.get_traffic_notifications(
            lat_top=40.46,
            lat_bottom=40.42,
            lon_left=-3.71,
            lon_right=-3.68
        )

        assert len(alerts) == 1
        assert alerts[0]["type"] == "POLICE"
        assert alerts[0]["latitude"] == 40.42

def test_health_check_returns_true_when_server_responds():
    mock_response = Mock()
    mock_response.status_code = 200

    with patch("requests.get", return_value=mock_response):
        client = WazeClient("http://localhost:8080")
        assert client.health_check() == True

def test_health_check_returns_false_on_error():
    with patch("requests.get", side_effect=Exception("Connection refused")):
        client = WazeClient("http://localhost:8080")
        assert client.health_check() == False
