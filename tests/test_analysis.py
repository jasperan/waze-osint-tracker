# tests/test_analysis.py
import os
import tempfile
import pytest
from database import Database
from analysis import get_stats, get_recent_events, get_users_summary, get_user_profile

def test_get_stats_returns_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)

        # Insert test events
        events = [
            {"event_hash": "a1", "username": "user1", "latitude": 40.42, "longitude": -3.70,
             "timestamp_utc": "2026-01-24T10:00:00Z", "timestamp_ms": 1737709200000,
             "report_type": "POLICE", "collected_at": "2026-01-24T10:01:00Z", "grid_cell": "test"},
            {"event_hash": "a2", "username": "user1", "latitude": 40.43, "longitude": -3.71,
             "timestamp_utc": "2026-01-24T11:00:00Z", "timestamp_ms": 1737712800000,
             "report_type": "JAM", "collected_at": "2026-01-24T11:01:00Z", "grid_cell": "test"},
            {"event_hash": "a3", "username": "user2", "latitude": 40.44, "longitude": -3.72,
             "timestamp_utc": "2026-01-24T12:00:00Z", "timestamp_ms": 1737716400000,
             "report_type": "POLICE", "collected_at": "2026-01-24T12:01:00Z", "grid_cell": "test"},
        ]
        for event in events:
            db.insert_event(event)

        stats = get_stats(db)

        assert stats["total_events"] == 3
        assert stats["unique_users"] == 2
        assert stats["by_type"]["POLICE"] == 2
        assert stats["by_type"]["JAM"] == 1

        db.close()

def test_get_recent_events():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)

        events = [
            {"event_hash": "a1", "username": "user1", "latitude": 40.42, "longitude": -3.70,
             "timestamp_utc": "2026-01-24T10:00:00Z", "timestamp_ms": 1737709200000,
             "report_type": "POLICE", "collected_at": "2026-01-24T10:01:00Z", "grid_cell": "test"},
            {"event_hash": "a2", "username": "user2", "latitude": 40.43, "longitude": -3.71,
             "timestamp_utc": "2026-01-24T11:00:00Z", "timestamp_ms": 1737712800000,
             "report_type": "JAM", "collected_at": "2026-01-24T11:01:00Z", "grid_cell": "test"},
        ]
        for event in events:
            db.insert_event(event)

        recent = get_recent_events(db, limit=1)

        assert len(recent) == 1
        assert recent[0]["username"] == "user2"  # Most recent

        db.close()

def test_get_user_profile():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)

        events = [
            {"event_hash": "a1", "username": "tracker1", "latitude": 40.42, "longitude": -3.70,
             "timestamp_utc": "2026-01-24T10:00:00Z", "timestamp_ms": 1737709200000,
             "report_type": "POLICE", "collected_at": "2026-01-24T10:01:00Z", "grid_cell": "test"},
            {"event_hash": "a2", "username": "tracker1", "latitude": 40.44, "longitude": -3.72,
             "timestamp_utc": "2026-01-24T11:00:00Z", "timestamp_ms": 1737712800000,
             "report_type": "JAM", "collected_at": "2026-01-24T11:01:00Z", "grid_cell": "test"},
        ]
        for event in events:
            db.insert_event(event)

        profile = get_user_profile(db, "tracker1")

        assert profile is not None
        assert profile["username"] == "tracker1"
        assert profile["event_count"] == 2
        assert "center_location" in profile
        assert profile["type_breakdown"]["POLICE"] == 1
        assert profile["type_breakdown"]["JAM"] == 1

        db.close()

def test_get_user_profile_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)

        profile = get_user_profile(db, "nonexistent")
        assert profile is None

        db.close()
