# tests/test_report_api.py
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    base_ts = 1_700_000_000_000
    for i in range(10):
        db.execute(
            """INSERT INTO events (username, latitude, longitude, timestamp_ms,
               timestamp_utc, report_type, subtype, event_hash, raw_json,
               collected_at, grid_cell)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "reportuser",
                40.4168,
                -3.7038,
                base_ts + i * 3600_000,
                "2023-11-14T12:00:00Z",
                "POLICE",
                "",
                f"rpt_{i}",
                "{}",
                "2023-11-14T12:00:00Z",
                "test_cell",
            ),
        )
    db.conn.commit()

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


def test_report_html_endpoint(app_client):
    resp = app_client.get("/api/report/reportuser")
    assert resp.status_code == 200
    assert b"reportuser" in resp.data
    assert b"<html" in resp.data


def test_report_json_endpoint(app_client):
    resp = app_client.get("/api/report/reportuser?format=json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["username"] == "reportuser"


def test_report_unknown_user(app_client):
    resp = app_client.get("/api/report/nobody?format=json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["total_events"] == 0
