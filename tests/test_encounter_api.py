# tests/test_encounter_api.py
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
    for week in range(6):
        week_off = week * 7 * 24 * 3600 * 1000
        for username, lat_off in [("alice", 0), ("bob", 0.0012)]:
            ts = base_ts + week_off
            db.execute(
                """INSERT INTO events (username, latitude, longitude, timestamp_ms,
                   timestamp_utc, report_type, subtype, event_hash, raw_json,
                   collected_at, grid_cell)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    username,
                    40.4168 + lat_off,
                    -3.7038,
                    ts,
                    "2023-11-14T08:00:00Z",
                    "POLICE",
                    "",
                    f"enc_{username}_{week}",
                    "{}",
                    "2023-11-14T08:00:00Z",
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


def test_encounters_endpoint(app_client):
    resp = app_client.get("/api/encounters/alice/bob")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)


def test_encounter_hotspots_endpoint(app_client):
    resp = app_client.get("/api/encounters/hotspots")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
