# tests/test_database.py
import os
import tempfile
import pytest
from database import Database

def test_database_creates_tables():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)

        # Check tables exist
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]

        assert "events" in table_names
        assert "collection_runs" in table_names
        db.close()

def test_insert_event_and_deduplicate():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)

        event = {
            "event_hash": "abc123",
            "username": "testuser",
            "latitude": 40.42,
            "longitude": -3.70,
            "timestamp_utc": "2026-01-24T10:00:00Z",
            "timestamp_ms": 1737709200000,
            "report_type": "police",
            "subtype": "visible",
            "raw_json": "{}",
            "collected_at": "2026-01-24T10:01:00Z",
            "grid_cell": "test_cell"
        }

        # First insert should succeed
        inserted = db.insert_event(event)
        assert inserted == True

        # Duplicate should be rejected
        inserted = db.insert_event(event)
        assert inserted == False

        # Count should be 1
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 1

        db.close()
