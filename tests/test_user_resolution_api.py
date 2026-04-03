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
    madrid = Database(str(tmp_path / "madrid.db"), check_same_thread=False)
    europe = Database(str(tmp_path / "europe.db"), check_same_thread=False)
    now = datetime.now(timezone.utc)
    _insert_event(madrid, "madrid_user", now - timedelta(hours=2))
    _insert_event(europe, "europe_user", now - timedelta(hours=1), "JAM")
    _insert_event(europe, "europe_user", now, "POLICE")

    import web.app as webapp

    monkeypatch.setattr(webapp, "get_all_dbs", lambda: [("madrid", madrid), ("europe", europe)])
    monkeypatch.setattr(webapp, "_load_web_config", lambda: {"database_type": "sqlite"})

    webapp.app.config["TESTING"] = True
    client = webapp.app.test_client()
    yield client
    madrid.close()
    europe.close()


def test_api_user_resolves_cross_region_user(app_client):
    resp = app_client.get("/api/user/europe_user")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["username"] == "europe_user"
    assert data["region"] == "europe"


def test_api_privacy_score_resolves_cross_region_user(app_client):
    resp = app_client.get("/api/privacy-score/europe_user")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["username"] == "europe_user"
    assert data["region"] == "europe"
    assert data["event_count"] == 2


def test_api_report_resolves_cross_region_user(app_client):
    resp = app_client.get("/api/report/europe_user?format=json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["username"] == "europe_user"
    assert data["region"] == "europe"
