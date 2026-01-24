# tests/test_waze_client.py
import pytest
from unittest.mock import patch, Mock, MagicMock
from waze_client import WazeClient

def test_get_traffic_notifications_parses_response():
    mock_response = Mock()
    mock_response.json.return_value = {
        "alerts": [
            {
                "type": "POLICE",
                "subtype": "POLICE_VISIBLE",
                "location": {"x": -3.70, "y": 40.42},
                "country": "ES",
                "wazeData": "testuser123,-3.70,40.42,abc123",
                "uuid": "abc123"
            }
        ],
        "jams": []
    }
    mock_response.raise_for_status = Mock()

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch.object(WazeClient, '__init__', lambda self, *args, **kwargs: None):
        client = WazeClient()
        client.session = mock_session
        client.timeout = 30
        client.WAZE_API_URL = "https://www.waze.com/live-map/api/georss"

        alerts, jams = client.get_traffic_notifications(
            lat_top=40.46,
            lat_bottom=40.42,
            lon_left=-3.71,
            lon_right=-3.68
        )

        assert len(alerts) == 1
        assert alerts[0]["type"] == "POLICE"
        assert alerts[0]["latitude"] == 40.42
        assert alerts[0]["longitude"] == -3.70

def test_health_check_returns_true_when_server_responds():
    mock_response = Mock()
    mock_response.status_code = 200

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch.object(WazeClient, '__init__', lambda self, *args, **kwargs: None):
        client = WazeClient()
        client.session = mock_session
        client.timeout = 5
        client.WAZE_API_URL = "https://www.waze.com/live-map/api/georss"

        assert client.health_check() == True

def test_health_check_returns_false_on_error():
    import requests
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.RequestException("Connection refused")

    with patch.object(WazeClient, '__init__', lambda self, *args, **kwargs: None):
        client = WazeClient()
        client.session = mock_session
        client.timeout = 5
        client.WAZE_API_URL = "https://www.waze.com/live-map/api/georss"

        assert client.health_check() == False

def test_extract_username_from_waze_data():
    client = WazeClient()

    # Test with wazeData containing username
    alert = {"wazeData": "customuser,-3.70,40.42,abc123"}
    assert client._extract_username(alert) == "customuser"

    # Test with world prefix (anonymous)
    alert = {"wazeData": "world,-3.70,40.42,abc12345"}
    assert client._extract_username(alert) == "world_abc12345"

    # Test fallback to uuid
    alert = {"uuid": "uuid12345678"}
    assert client._extract_username(alert) == "user_uuid1234"

    # Test completely anonymous
    alert = {}
    assert client._extract_username(alert) == "anonymous"
