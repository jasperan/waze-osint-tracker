import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from briefing import build_briefing, render_briefing_markdown, render_briefing_text
from collector import generate_event_hash
from database import Database


def _insert_event(
    db,
    username: str,
    when: datetime,
    *,
    latitude: float,
    longitude: float,
    report_type: str = "POLICE",
    grid_cell: str = "test_cell",
):
    timestamp_ms = int(when.timestamp() * 1000)
    event = {
        "event_hash": generate_event_hash(username, latitude, longitude, timestamp_ms, report_type),
        "username": username,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp_utc": when.isoformat(),
        "timestamp_ms": timestamp_ms,
        "report_type": report_type,
        "subtype": "",
        "raw_json": "{}",
        "collected_at": when.isoformat(),
        "grid_cell": grid_cell,
    }
    db.insert_event(event)


def test_build_briefing_aggregates_regions_and_risk(tmp_path):
    now = datetime(2026, 1, 25, 12, 0, tzinfo=timezone.utc)

    europe = Database(str(tmp_path / "europe.db"))
    americas = Database(str(tmp_path / "americas.db"))

    for offset in range(10):
        _insert_event(
            europe,
            "alpha",
            now - timedelta(hours=offset + 1),
            latitude=40.40,
            longitude=-3.70,
            report_type="POLICE" if offset % 2 == 0 else "HAZARD",
            grid_cell="madrid",
        )

    for offset in range(3):
        _insert_event(
            americas,
            "charlie",
            now - timedelta(hours=offset + 2),
            latitude=34.05,
            longitude=-118.24,
            report_type="JAM",
            grid_cell="la",
        )

    _insert_event(
        americas,
        "old_timer",
        now - timedelta(days=10),
        latitude=34.05,
        longitude=-118.24,
        report_type="ACCIDENT",
        grid_cell="la",
    )

    status_path = tmp_path / "collector_status.json"
    status_path.write_text(json.dumps({"timestamp": now.isoformat(), "status": "scanning"}))

    briefing = build_briefing(
        [("europe", europe), ("americas", americas)],
        status_path=str(status_path),
        recent_hours=48,
        top_users=3,
        risk_users=2,
        now=now,
    )

    assert briefing["totals"]["total_events"] == 14
    assert briefing["regions"][0]["region"] == "europe"
    assert briefing["top_recent_users"][0]["username"] == "alpha"
    assert any(item["username"] == "alpha" for item in briefing["high_risk_users"])
    assert briefing["status"]["status"] == "scanning"

    markdown = render_briefing_markdown(briefing)
    text = render_briefing_text(briefing)
    assert "## Top Recent Users" in markdown
    assert "High-risk recent users:" in text

    europe.close()
    americas.close()
