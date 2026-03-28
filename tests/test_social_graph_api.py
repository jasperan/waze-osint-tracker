# tests/test_social_graph_api.py
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Create a Flask test client with a temporary database."""
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)

    base_ts = 1_700_000_000_000
    for i in range(3):
        ts = base_ts + i * 120_000
        for username, lat_off in [("alice", 0), ("bob", 0.0001)]:
            db.execute(
                """INSERT INTO events (username, latitude, longitude, timestamp_ms,
                   timestamp_utc, report_type, subtype, event_hash, raw_json,
                   collected_at, grid_cell)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    username,
                    40.4168 + lat_off,
                    -3.7038,
                    ts + int(lat_off * 200_000_000),
                    "2023-11-14T12:00:00Z",
                    "POLICE",
                    "",
                    f"hash_{username}_{i}",
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


def test_social_graph_endpoint(app_client):
    resp = app_client.get("/api/social-graph")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "nodes" in data
    assert "edges" in data


def test_social_graph_user_endpoint(app_client):
    resp = app_client.get("/api/social-graph/alice")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "nodes" in data
    node_ids = {n["id"] for n in data["nodes"]}
    assert "alice" in node_ids
