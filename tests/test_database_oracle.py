# tests/test_database_oracle.py
"""Tests for the Oracle Database backend.

All tests are skipped automatically when the Oracle database is not reachable.
Tests use grid_cell='test_cell' / region='madrid' and clean up after themselves.
"""

import os

import pytest

# ---------------------------------------------------------------------------
# Skip the entire module if oracledb is not installed or DB is unreachable
# ---------------------------------------------------------------------------
oracledb = pytest.importorskip("oracledb")

ORACLE_DSN = os.environ.get(
    "ORACLE_DSN",
    "waze/WazeIntel2026@localhost:1521/FREEPDB1",  # pragma: allowlist secret
)


def _oracle_is_reachable() -> bool:
    """Return True if we can connect to Oracle with the configured DSN."""
    try:
        from database_oracle import Database

        db = Database(ORACLE_DSN)
        db.close()
        return True
    except Exception:
        return False


oracle_available = pytest.mark.skipif(
    not _oracle_is_reachable(),
    reason="Oracle database not reachable",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    """Yield an Oracle Database instance and clean up test rows afterwards."""
    from database_oracle import Database

    database = Database(ORACLE_DSN)
    yield database

    # Clean up test data
    cur = database.conn.cursor()
    cur.execute("DELETE FROM events WHERE region = 'madrid' AND username = 'testuser_oracle'")
    cur.execute("DELETE FROM tracked_users WHERE username = 'testuser_oracle'")
    cur.execute("DELETE FROM daily_stats WHERE stat_date = TO_DATE('2099-01-01', 'YYYY-MM-DD')")
    database.conn.commit()
    database.close()


def _make_event(event_hash: str = "oratest_abc123") -> dict:
    """Build a sample event dict for insertion."""
    return {
        "event_hash": event_hash,
        "username": "testuser_oracle",
        "latitude": 40.4168,
        "longitude": -3.7038,
        "timestamp_utc": "2026-01-24T10:00:00Z",
        "timestamp_ms": 1737709200000,
        "report_type": "police",
        "subtype": "visible",
        "raw_json": "{}",
        "collected_at": "2026-01-24T10:01:00Z",
        "grid_cell": "test_cell",
        "region": "madrid",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@oracle_available
class TestOracleConnection:
    def test_connection_works(self, db):
        """Verify we can execute a trivial query."""
        cur = db.execute("SELECT 1 AS val FROM dual")
        row = cur.fetchone()
        assert row is not None
        assert row["val"] == 1


@oracle_available
class TestInsertEvent:
    def test_insert_event_returns_true(self, db):
        event = _make_event()
        assert db.insert_event(event) is True

    def test_duplicate_event_returns_false(self, db):
        event = _make_event()
        db.insert_event(event)
        assert db.insert_event(event) is False

    def test_insert_event_persists(self, db):
        event = _make_event("oratest_persist_001")
        db.insert_event(event)
        cur = db.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM events WHERE event_hash = :1 AND region = :2",
            ["oratest_persist_001", "madrid"],
        )
        row = cur.fetchone()
        assert row[0] == 1


@oracle_available
class TestUpsertTrackedUser:
    def test_upsert_new_user(self, db):
        result = db.upsert_tracked_user("testuser_oracle", "2026-01-24T10:00:00Z")
        assert result is True

    def test_upsert_increments_count(self, db):
        db.upsert_tracked_user("testuser_oracle", "2026-01-24T10:00:00Z")
        db.upsert_tracked_user("testuser_oracle", "2026-01-24T11:00:00Z")
        users = db.get_tracked_users(limit=100)
        match = [u for u in users if u["username"] == "testuser_oracle"]
        assert len(match) == 1
        assert match[0]["total_events"] == 2


@oracle_available
class TestCollectionSummary:
    def test_summary_returns_dict(self, db):
        summary = db.get_collection_summary()
        assert isinstance(summary, dict)
        assert "total_events" in summary
        assert "unique_users" in summary
        assert "days_collected" in summary
        assert "grid_cells_used" in summary

    def test_summary_counts_inserted_event(self, db):
        event = _make_event("oratest_summary_001")
        db.insert_event(event)
        summary = db.get_collection_summary()
        assert summary["total_events"] >= 1


@oracle_available
class TestDailyStats:
    def test_update_and_get_daily_stats(self, db):
        db.update_daily_stats(date="2099-01-01", events=5, users=3, region="madrid")
        stats = db.get_daily_stats(days=5)
        assert isinstance(stats, list)
