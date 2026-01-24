# database.py
import sqlite3
from pathlib import Path
from typing import Optional, List, Any

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
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
        """)
        self.conn.commit()

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
