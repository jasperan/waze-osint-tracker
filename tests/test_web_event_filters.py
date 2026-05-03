from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from web.event_filters import build_where, parse_event_filters


def _make_event(
    event_hash: str,
    username: str,
    report_type: str,
    *,
    timestamp_ms: int,
    latitude: float = 40.0,
    longitude: float = -3.0,
    subtype: str | None = None,
    grid_cell: str = "test_cell",
) -> dict:
    timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
    return {
        "event_hash": event_hash,
        "username": username,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp_utc": timestamp,
        "timestamp_ms": timestamp_ms,
        "report_type": report_type,
        "subtype": subtype,
        "raw_json": "{}",
        "collected_at": timestamp,
        "grid_cell": grid_cell,
    }


@pytest.fixture()
def regional_dbs(tmp_path):
    europe = Database(str(tmp_path / "waze_europe.db"))
    americas = Database(str(tmp_path / "waze_americas.db"))

    europe.insert_event(
        _make_event(
            "eu_police",
            "alice",
            "POLICE",
            timestamp_ms=1_700_000_300_000,
            latitude=40.12345,
            longitude=-3.12345,
        )
    )
    europe.insert_event(
        _make_event(
            "eu_jam",
            "bob",
            "JAM",
            timestamp_ms=1_700_000_200_000,
            latitude=40.12346,
            longitude=-3.12346,
        )
    )
    americas.insert_event(
        _make_event(
            "am_police",
            "carol",
            "POLICE",
            timestamp_ms=1_700_000_100_000,
            latitude=41.0,
            longitude=-4.0,
        )
    )

    yield [("europe", europe), ("americas", americas)]

    europe.close()
    americas.close()


def test_parse_event_filters_builds_common_conditions():
    result = parse_event_filters(
        {
            "type": "police",
            "subtype": "visible",
            "user": "alice",
            "from": "2026-01-01",
            "to": "2026-01-02",
            "region": "europe",
        }
    )

    assert result.error_message is None
    assert result.region_filter == "europe"
    assert result.conditions == [
        "report_type = ?",
        "subtype = ?",
        "username = ?",
        "timestamp_utc >= ?",
        "timestamp_utc <= ?",
    ]
    assert result.params == [
        "POLICE",
        "visible",
        "alice",
        "2026-01-01",
        "2026-01-02T23:59:59",
    ]


def test_parse_event_filters_rejects_invalid_since():
    result = parse_event_filters({"since": "abc", "region": "europe"})

    assert result.region_filter == "europe"
    assert result.error_message == "Invalid 'since' parameter, must be integer"


def test_build_where_adds_region_for_oracle_only():
    where, params = build_where(["report_type = ?"], ["POLICE"], "europe", "all")
    assert where == "report_type = ? AND region = ?"
    assert params == ("POLICE", "europe")

    where, params = build_where(["report_type = ?"], ["POLICE"], "europe", "europe")
    assert where == "report_type = ?"
    assert params == ("POLICE",)


def test_api_events_filters_sqlite_regions_and_limit(monkeypatch, regional_dbs):
    import web.app as web_app

    monkeypatch.setattr(web_app, "get_all_dbs", lambda: regional_dbs)
    web_app.app.config["TESTING"] = True

    with web_app.app.test_client() as client:
        response = client.get("/api/events?region=europe&type=POLICE&limit=1")

    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["username"] == "alice"
    assert data[0]["region"] == "europe"
    assert data[0]["type"] == "POLICE"


def test_api_events_clamps_negative_limit(monkeypatch, regional_dbs):
    import web.app as web_app

    monkeypatch.setattr(web_app, "get_all_dbs", lambda: regional_dbs)
    web_app.app.config["TESTING"] = True

    with web_app.app.test_client() as client:
        response = client.get("/api/events?limit=-1")

    assert response.status_code == 200
    assert response.get_json() == []


def test_api_heatmap_filters_sqlite_regions(monkeypatch, regional_dbs):
    import web.app as web_app

    monkeypatch.setattr(web_app, "get_all_dbs", lambda: regional_dbs)
    web_app.app.config["TESTING"] = True

    with web_app.app.test_client() as client:
        response = client.get("/api/heatmap?region=europe&type=POLICE")

    assert response.status_code == 200
    assert response.get_json() == [[40.1234, -3.1235, 1]]


def test_api_events_invalid_since_returns_400(monkeypatch, regional_dbs):
    import web.app as web_app

    monkeypatch.setattr(web_app, "get_all_dbs", lambda: regional_dbs)
    web_app.app.config["TESTING"] = True

    with web_app.app.test_client() as client:
        response = client.get("/api/events?since=abc")

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid 'since' parameter, must be integer"}


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeOracleDb:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _FakeCursor(self.rows)


def test_api_events_applies_oracle_region_filter(monkeypatch):
    import web.app as web_app

    oracle = _FakeOracleDb(
        [
            {
                "id": 7,
                "username": "alice",
                "latitude": 40.1,
                "longitude": -3.1,
                "timestamp_utc": "2026-01-01T00:00:00+00:00",
                "report_type": "POLICE",
                "subtype": None,
                "region": "europe",
            }
        ]
    )
    monkeypatch.setattr(web_app, "get_all_dbs", lambda: [("all", oracle)])
    web_app.app.config["TESTING"] = True

    with web_app.app.test_client() as client:
        response = client.get("/api/events?region=europe&type=police&limit=5")

    assert response.status_code == 200
    assert response.get_json()[0]["region"] == "europe"
    query, params = oracle.calls[0]
    assert "report_type = ? AND region = ?" in query
    assert params == ("POLICE", "europe", 5)


def test_api_heatmap_applies_oracle_region_filter(monkeypatch):
    import web.app as web_app

    oracle = _FakeOracleDb([{"latitude": 40.1, "longitude": -3.1, "weight": 2}])
    monkeypatch.setattr(web_app, "get_all_dbs", lambda: [("all", oracle)])
    web_app.app.config["TESTING"] = True

    with web_app.app.test_client() as client:
        response = client.get("/api/heatmap?region=europe&type=police")

    assert response.status_code == 200
    assert response.get_json() == [[40.1, -3.1, 2]]
    query, params = oracle.calls[0]
    assert "report_type = ? AND region = ?" in query
    assert params == ("POLICE", "europe")
