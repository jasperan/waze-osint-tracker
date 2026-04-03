import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import generate_event_hash
from database import Database


def _insert_event(db, username: str, when: datetime, report_type: str = "POLICE"):
    timestamp_ms = int(when.timestamp() * 1000)
    db.insert_event(
        {
            "event_hash": generate_event_hash(
                username, 40.4168, -3.7038, timestamp_ms, report_type
            ),
            "username": username,
            "latitude": 40.4168,
            "longitude": -3.7038,
            "timestamp_utc": when.isoformat(),
            "timestamp_ms": timestamp_ms,
            "report_type": report_type,
            "subtype": "",
            "raw_json": "{}",
            "collected_at": when.isoformat(),
            "grid_cell": "test_cell",
        }
    )


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db = Database(db_path, check_same_thread=False)
    now = datetime.now(timezone.utc)
    for offset in range(5):
        _insert_event(db, "brief_user", now - timedelta(hours=offset + 1), "POLICE")

    status_path = tmp_path / "collector_status.json"
    status_path.write_text(json.dumps({"timestamp": now.isoformat(), "status": "idle"}))

    import briefing as briefing_module
    import web.app as webapp

    monkeypatch.setattr(webapp, "get_all_dbs", lambda: [("test", db)])
    monkeypatch.setattr(webapp, "STATUS_FILE", str(status_path))
    monkeypatch.setattr(webapp, "_load_web_config", lambda: {"database_type": "sqlite"})
    monkeypatch.setattr(
        briefing_module,
        "open_briefing_dbs",
        lambda project_root, config=None: [("test", db)],
    )

    webapp.app.config["TESTING"] = True
    client = webapp.app.test_client()
    yield client
    db.close()


def test_briefing_endpoint(app_client):
    resp = app_client.get("/api/briefing?hours=48&top_users=2")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "headline" in data
    assert "regions" in data
    assert data["top_recent_users"][0]["username"] == "brief_user"
