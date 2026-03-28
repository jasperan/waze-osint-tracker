# tests/test_geofence_api.py
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    Database(db_path)  # ensure schema exists

    import web.app as webapp

    original_paths = webapp.DB_PATHS.copy()
    original_db_path = webapp.DB_PATH
    webapp.DB_PATHS = {"test": db_path}
    webapp.DB_PATH = db_path
    monkeypatch.setattr(webapp, "_load_web_config", lambda: {"database_type": "sqlite"})

    webapp.app.config["TESTING"] = True
    client = webapp.app.test_client()
    yield client
    webapp.DB_PATHS = original_paths
    webapp.DB_PATH = original_db_path


def test_create_geofence(app_client):
    resp = app_client.post(
        "/api/geofences",
        json={
            "name": "Test Zone",
            "geometry_type": "circle",
            "center_lat": 40.4168,
            "center_lon": -3.7038,
            "radius_m": 500,
        },
    )
    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert data["name"] == "Test Zone"
    assert "geofence_id" in data


def test_list_geofences(app_client):
    app_client.post(
        "/api/geofences",
        json={
            "name": "Zone A",
            "geometry_type": "circle",
            "center_lat": 40.0,
            "center_lon": -3.0,
            "radius_m": 100,
        },
    )
    resp = app_client.get("/api/geofences")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data) >= 1


def test_delete_geofence(app_client):
    resp = app_client.post(
        "/api/geofences",
        json={
            "name": "ToDelete",
            "geometry_type": "circle",
            "center_lat": 40.0,
            "center_lon": -3.0,
            "radius_m": 100,
        },
    )
    gf_id = json.loads(resp.data)["geofence_id"]
    del_resp = app_client.delete(f"/api/geofences/{gf_id}")
    assert del_resp.status_code == 200


def test_geofence_alerts_empty(app_client):
    resp = app_client.get("/api/geofence-alerts")
    assert resp.status_code == 200
    assert json.loads(resp.data) == []
