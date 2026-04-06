"""Tests for /api/encounters/schedule endpoint."""

from unittest.mock import patch

import pytest

from web.app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


FAKE_HOTSPOTS = [
    {
        "lat": 40.42,
        "lon": -3.70,
        "users": ["alice", "bob"],
        "probability": 0.85,
        "day_of_week": 1,
        "hour": 9,
        "evidence_count": 12,
    },
    {
        "lat": 41.39,
        "lon": 2.17,
        "users": ["carol", "dave"],
        "probability": 0.45,
        "day_of_week": 4,
        "hour": 17,
        "evidence_count": 5,
    },
]


@patch("encounter_prediction.find_hotspot_encounters", return_value=FAKE_HOTSPOTS)
@patch("web.app.get_all_dbs")
def test_schedule_returns_correct_shape(mock_dbs, mock_hotspots, client):
    mock_dbs.return_value = []
    resp = client.get("/api/encounters/schedule")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "schedule" in data
    assert len(data["schedule"]) == 2
    item = data["schedule"][0]
    for key in ("lat", "lon", "probability", "day_of_week", "hour", "users", "evidence_count"):
        assert key in item, f"Missing key: {key}"


@patch("encounter_prediction.find_hotspot_encounters", return_value=FAKE_HOTSPOTS)
@patch("web.app.get_all_dbs")
def test_schedule_filters_by_day(mock_dbs, mock_hotspots, client):
    mock_dbs.return_value = []
    resp = client.get("/api/encounters/schedule?day=1")
    data = resp.get_json()
    for item in data["schedule"]:
        assert item["day_of_week"] == 1


@patch("encounter_prediction.find_hotspot_encounters", return_value=FAKE_HOTSPOTS)
@patch("web.app.get_all_dbs")
def test_schedule_filters_by_hour(mock_dbs, mock_hotspots, client):
    mock_dbs.return_value = []
    resp = client.get("/api/encounters/schedule?hour=17")
    data = resp.get_json()
    for item in data["schedule"]:
        assert item["hour"] == 17


@patch("encounter_prediction.find_hotspot_encounters", return_value=[])
@patch("web.app.get_all_dbs")
def test_schedule_empty_result(mock_dbs, mock_hotspots, client):
    mock_dbs.return_value = []
    resp = client.get("/api/encounters/schedule")
    data = resp.get_json()
    assert data["schedule"] == []


@patch("encounter_prediction.find_hotspot_encounters", return_value=FAKE_HOTSPOTS)
@patch("web.app.get_all_dbs")
def test_schedule_respects_limit(mock_dbs, mock_hotspots, client):
    mock_dbs.return_value = []
    resp = client.get("/api/encounters/schedule?limit=1")
    data = resp.get_json()
    assert len(data["schedule"]) <= 1
