# tests/test_report_generator.py
"""Tests for report_generator module."""

import os
import tempfile

from database import Database
from report_generator import generate_user_report, render_report_html


def _seed_db(db, username="tracker01", n=20):
    """Insert *n* synthetic events for *username*."""
    base_ts_ms = 1700000000000  # ~2023-11-14
    for i in range(n):
        hour = 9 + (i % 9)  # hours 9-17
        ts_utc = f"2026-01-{15 + i % 5:02d}T{hour:02d}:00:00Z"
        ts_ms = base_ts_ms + i * 3600000
        lat = 40.42 + (i % 5) * 0.01
        lon = -3.70 + (i % 4) * 0.01
        report_type = ["police", "jam", "hazard", "accident"][i % 4]
        event_hash = f"hash_{username}_{i:04d}"
        db.conn.execute(
            """INSERT INTO events
               (username, latitude, longitude, timestamp_ms, timestamp_utc,
                report_type, subtype, event_hash, raw_json, collected_at, grid_cell)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                username,
                lat,
                lon,
                ts_ms,
                ts_utc,
                report_type,
                "",
                event_hash,
                "{}",
                ts_utc,
                "test_cell",
            ),
        )
    db.conn.commit()


def _make_db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_report.db")
    return Database(db_path), tmpdir


# ── generate_user_report with seeded events ────────────────────────


def test_report_correct_counts():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 20)
    report = generate_user_report("tracker01", db)

    assert report["total_events"] == 20
    assert report["username"] == "tracker01"
    db.close()


def test_report_has_all_keys():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 20)
    report = generate_user_report("tracker01", db)

    required_keys = [
        "username",
        "generated_at",
        "total_events",
        "event_types",
        "timeline",
        "locations",
        "risk_assessment",
        "active_days",
        "area_km2",
    ]
    for key in required_keys:
        assert key in report, f"Missing key: {key}"
    db.close()


def test_report_event_types_structure():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 20)
    report = generate_user_report("tracker01", db)

    assert len(report["event_types"]) == 4  # police, jam, hazard, accident
    for et in report["event_types"]:
        assert "type" in et
        assert "count" in et
        assert "pct" in et
    type_names = {et["type"] for et in report["event_types"]}
    assert type_names == {"police", "jam", "hazard", "accident"}
    db.close()


def test_report_timeline_max_20():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 30)
    report = generate_user_report("tracker01", db)

    assert len(report["timeline"]) == 20
    db.close()


def test_report_risk_assessment_keys():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 20)
    report = generate_user_report("tracker01", db)

    ra = report["risk_assessment"]
    for key in ["overall", "schedule_predictability", "location_concentration", "trackability"]:
        assert key in ra, f"Missing risk key: {key}"
        assert isinstance(ra[key], (int, float))
    db.close()


# ── Unknown user → total_events=0 ──────────────────────────────────


def test_unknown_user_zero_events():
    db, _ = _make_db()
    report = generate_user_report("nonexistent_user", db)

    assert report["total_events"] == 0
    assert report["username"] == "nonexistent_user"
    assert report["event_types"] == []
    assert report["timeline"] == []
    assert report["locations"] == []
    assert report["active_days"] == 0
    assert report["area_km2"] == 0.0
    assert report["risk_assessment"]["overall"] == 0
    db.close()


# ── render_report_html ──────────────────────────────────────────────


def test_render_contains_username():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 20)
    report = generate_user_report("tracker01", db)
    html = render_report_html(report)

    assert "tracker01" in html
    db.close()


def test_render_contains_html_tag():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 20)
    report = generate_user_report("tracker01", db)
    html = render_report_html(report)

    assert "<html" in html
    db.close()


def test_render_contains_event_type_names():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 20)
    report = generate_user_report("tracker01", db)
    html = render_report_html(report)

    for name in ["police", "jam", "hazard", "accident"]:
        assert name in html, f"Event type '{name}' not found in rendered HTML"
    db.close()


def test_render_no_external_stylesheets():
    db, _ = _make_db()
    _seed_db(db, "tracker01", 20)
    report = generate_user_report("tracker01", db)
    html = render_report_html(report)

    # No <link rel="stylesheet"> tags pointing to external resources
    assert 'rel="stylesheet"' not in html.lower()
    # No external CSS imports
    assert "@import" not in html
    db.close()
