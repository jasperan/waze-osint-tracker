# database.py
import sqlite3
from pathlib import Path
from typing import Optional, List, Any

class Database:
    def __init__(self, db_path: str, check_same_thread: bool = True):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # timeout=30 waits up to 30 seconds for locks instead of failing immediately
        self.conn = sqlite3.connect(db_path, check_same_thread=check_same_thread, timeout=30)
        self.conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent write performance
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_hash TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                timestamp_utc TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                subtype TEXT,
                raw_json TEXT,
                collected_at TEXT NOT NULL,
                grid_cell TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_username ON events(username);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp_ms);
            CREATE INDEX IF NOT EXISTS idx_events_location ON events(latitude, longitude);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(report_type);

            CREATE TABLE IF NOT EXISTS collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                grid_cell TEXT NOT NULL,
                events_found INTEGER DEFAULT 0,
                events_new INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running'
            );

            CREATE TABLE IF NOT EXISTS tracked_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                event_count INTEGER DEFAULT 1,
                notes TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tracked_users_username ON tracked_users(username);

            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                events_collected INTEGER DEFAULT 0,
                unique_users INTEGER DEFAULT 0,
                api_requests INTEGER DEFAULT 0,
                api_errors INTEGER DEFAULT 0,
                grid_cells_scanned INTEGER DEFAULT 0,
                by_type_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date);
        """)
        self.conn.commit()

    def upsert_tracked_user(self, username: str, timestamp: str) -> bool:
        """Track a user, updating last_seen and event_count if exists."""
        try:
            self.conn.execute("""
                INSERT INTO tracked_users (username, first_seen, last_seen, event_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(username) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    event_count = event_count + 1
            """, (username, timestamp, timestamp))
            self.conn.commit()
            return True
        except Exception:
            return False

    def get_tracked_users(self, limit: int = 100):
        """Get tracked users ordered by event count."""
        return self.conn.execute("""
            SELECT * FROM tracked_users
            ORDER BY event_count DESC
            LIMIT ?
        """, (limit,)).fetchall()

    def update_daily_stats(self, date: str, events: int = 0, users: int = 0,
                           requests: int = 0, errors: int = 0, cells: int = 0,
                           by_type: dict = None):
        """Update daily collection statistics."""
        import json
        by_type_json = json.dumps(by_type) if by_type else None

        self.conn.execute("""
            INSERT INTO daily_stats (date, events_collected, unique_users,
                                     api_requests, api_errors, grid_cells_scanned, by_type_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                events_collected = events_collected + excluded.events_collected,
                unique_users = excluded.unique_users,
                api_requests = api_requests + excluded.api_requests,
                api_errors = api_errors + excluded.api_errors,
                grid_cells_scanned = grid_cells_scanned + excluded.grid_cells_scanned,
                by_type_json = excluded.by_type_json
        """, (date, events, users, requests, errors, cells, by_type_json))
        self.conn.commit()

    def get_daily_stats(self, days: int = 30):
        """Get daily stats for the last N days."""
        return self.conn.execute("""
            SELECT * FROM daily_stats
            ORDER BY date DESC
            LIMIT ?
        """, (days,)).fetchall()

    def get_collection_summary(self):
        """Get overall collection summary."""
        result = self.conn.execute("""
            SELECT
                COUNT(*) as total_events,
                COUNT(DISTINCT username) as unique_users,
                COUNT(DISTINCT DATE(timestamp_utc)) as days_collected,
                MIN(timestamp_utc) as first_event,
                MAX(timestamp_utc) as last_event,
                COUNT(DISTINCT grid_cell) as grid_cells_used
            FROM events
        """).fetchone()
        return dict(result) if result else {}

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(query, params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def insert_event(self, event: dict) -> bool:
        """Insert event, return True if inserted, False if duplicate."""
        try:
            self.conn.execute("""
                INSERT INTO events (
                    event_hash, username, latitude, longitude,
                    timestamp_utc, timestamp_ms, report_type, subtype,
                    raw_json, collected_at, grid_cell
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event["event_hash"],
                event["username"],
                event["latitude"],
                event["longitude"],
                event["timestamp_utc"],
                event["timestamp_ms"],
                event["report_type"],
                event.get("subtype"),
                event.get("raw_json"),
                event["collected_at"],
                event["grid_cell"]
            ))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
