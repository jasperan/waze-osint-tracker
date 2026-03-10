#!/usr/bin/env python3
"""
Migrate all data from regional SQLite databases into Oracle 26ai Free.

Usage:
    python scripts/migrate_sqlite_to_oracle.py

Reads ORACLE_DSN from environment (default: waze/WazeIntel2026@localhost:1521/FREEPDB1).
Processes each region's SQLite DB, inserting events and tracked_users into Oracle
with batch inserts (5000 rows) and duplicate handling.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import oracledb

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORACLE_DSN = os.environ.get("ORACLE_DSN", "waze/WazeIntel2026@localhost:1521/FREEPDB1")

BATCH_SIZE = 5000

# Map SQLite DB filenames to region identifiers matching Oracle partitions
REGION_DBS = {
    "madrid": "data/waze_madrid.db",
    "europe": "data/waze_europe.db",
    "americas": "data/waze_americas.db",
    "asia": "data/waze_asia.db",
    "oceania": "data/waze_oceania.db",
    "africa": "data/waze_africa.db",
}

# SQL for inserting events into Oracle
INSERT_EVENT_SQL = """
INSERT INTO events (
    event_hash, event_type, subtype, severity, reliability, confidence,
    latitude, longitude, street, city, country, region, username,
    report_rating, report_mood, timestamp_utc, collected_at,
    speed, road_type, magvar, raw_json
) VALUES (
    :event_hash, :event_type, :subtype, :severity, :reliability, :confidence,
    :latitude, :longitude, :street, :city, :country, :region, :username,
    :report_rating, :report_mood,
    TO_TIMESTAMP(:timestamp_utc, 'YYYY-MM-DD"T"HH24:MI:SS+TZH:TZM'),
    TO_TIMESTAMP(:collected_at,  'YYYY-MM-DD"T"HH24:MI:SS.FF6+TZH:TZM'),
    :speed, :road_type, :magvar, :raw_json
)
"""

# MERGE for tracked_users — insert or update on username match
MERGE_TRACKED_USER_SQL = """
MERGE INTO tracked_users tu
USING (
    SELECT :username AS username,
           TO_TIMESTAMP(:first_seen, 'YYYY-MM-DD"T"HH24:MI:SS+TZH:TZM') AS first_seen,
           TO_TIMESTAMP(:last_seen,  'YYYY-MM-DD"T"HH24:MI:SS+TZH:TZM') AS last_seen,
           :event_count AS event_count,
           :region AS region,
           :notes AS notes
    FROM dual
) src ON (tu.username = src.username)
WHEN MATCHED THEN UPDATE SET
    tu.last_seen    = GREATEST(tu.last_seen, src.last_seen),
    tu.first_seen   = LEAST(tu.first_seen, src.first_seen),
    tu.total_events = tu.total_events + src.event_count,
    tu.region_list  = CASE
        WHEN tu.region_list IS NULL THEN src.region
        WHEN INSTR(tu.region_list, src.region) > 0 THEN tu.region_list
        ELSE tu.region_list || ',' || src.region
    END
WHEN NOT MATCHED THEN INSERT (
    username, first_seen, last_seen, total_events, region_list, notes
) VALUES (
    src.username, src.first_seen, src.last_seen, src.event_count, src.region, src.notes
)
"""

# ---------------------------------------------------------------------------
# Helper: extract enriched fields from raw_json
# ---------------------------------------------------------------------------


def parse_raw_json(raw_json_str: str | None) -> dict:
    """Extract optional fields from the raw Waze alert JSON."""
    defaults = {
        "severity": None,
        "reliability": None,
        "confidence": None,
        "street": None,
        "city": None,
        "country": None,
        "report_rating": None,
        "report_mood": None,
        "speed": None,
        "road_type": None,
        "magvar": None,
    }
    if not raw_json_str:
        return defaults
    try:
        j = json.loads(raw_json_str)
    except (json.JSONDecodeError, TypeError):
        return defaults

    return {
        "severity": j.get("severity"),
        "reliability": j.get("reliability"),
        "confidence": j.get("confidence"),
        "street": (j.get("street") or "")[:500] or None,
        "city": (j.get("city") or "")[:200] or None,
        "country": (j.get("country") or "")[:100] or None,
        "report_rating": j.get("reportRating"),
        "report_mood": j.get("reportMood"),
        "speed": j.get("speed"),
        "road_type": j.get("roadType"),
        "magvar": j.get("magvar"),
    }


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------


def connect_oracle() -> oracledb.Connection:
    """Parse ORACLE_DSN and return an oracledb connection."""
    # Format: user/password@host:port/service
    user_pass, host_svc = ORACLE_DSN.split("@", 1)
    user, password = user_pass.split("/", 1)
    conn = oracledb.connect(user=user, password=password, dsn=host_svc)
    # Set schema so unqualified table names resolve to waze
    with conn.cursor() as cur:
        cur.execute("ALTER SESSION SET CURRENT_SCHEMA = waze")
    return conn


def migrate_events(ora_conn: oracledb.Connection, sqlite_path: str, region: str):
    """Migrate events from a single SQLite DB into Oracle."""
    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row

    total = sq.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print(f"\n  [{region}] Events to migrate: {total:,}")
    if total == 0:
        sq.close()
        return 0, 0

    inserted = 0
    skipped = 0
    batch = []

    cursor = sq.execute(
        "SELECT event_hash, username, latitude, longitude, timestamp_utc, "
        "       report_type, subtype, raw_json, collected_at "
        "FROM events"
    )

    for i, row in enumerate(cursor, 1):
        row_dict = dict(row)
        extra = parse_raw_json(row_dict.get("raw_json"))

        params = {
            "event_hash": row_dict["event_hash"],
            "event_type": row_dict["report_type"],
            "subtype": row_dict["subtype"] or None,
            "latitude": row_dict["latitude"],
            "longitude": row_dict["longitude"],
            "timestamp_utc": row_dict["timestamp_utc"],
            "collected_at": row_dict["collected_at"],
            "region": region,
            "username": row_dict["username"],
            "raw_json": row_dict.get("raw_json"),
            **extra,
        }
        batch.append(params)

        if len(batch) >= BATCH_SIZE:
            ins, skp = _flush_event_batch(ora_conn, batch)
            inserted += ins
            skipped += skp
            print(
                f"    {region}: {i:>10,} / {total:,}  (inserted {inserted:,}, skipped {skipped:,})"
            )
            batch = []

    # Flush remaining
    if batch:
        ins, skp = _flush_event_batch(ora_conn, batch)
        inserted += ins
        skipped += skp

    sq.close()
    print(f"  [{region}] Events done: {inserted:,} inserted, {skipped:,} skipped")
    return inserted, skipped


def _flush_event_batch(ora_conn: oracledb.Connection, batch: list[dict]) -> tuple[int, int]:
    """Insert a batch of event rows, handling duplicates one by one on failure."""
    inserted = 0
    skipped = 0
    try:
        with ora_conn.cursor() as cur:
            cur.executemany(INSERT_EVENT_SQL, batch)
        ora_conn.commit()
        inserted = len(batch)
    except oracledb.IntegrityError:
        # Batch contained duplicates — fall back to row-by-row
        ora_conn.rollback()
        with ora_conn.cursor() as cur:
            for params in batch:
                try:
                    cur.execute(INSERT_EVENT_SQL, params)
                    inserted += 1
                except oracledb.IntegrityError:
                    skipped += 1
        ora_conn.commit()
    return inserted, skipped


def migrate_tracked_users(ora_conn: oracledb.Connection, sqlite_path: str, region: str):
    """Migrate tracked_users from a single SQLite DB using MERGE."""
    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row

    total = sq.execute("SELECT COUNT(*) FROM tracked_users").fetchone()[0]
    print(f"\n  [{region}] Tracked users to migrate: {total:,}")
    if total == 0:
        sq.close()
        return 0

    merged = 0
    batch = []

    cursor = sq.execute(
        "SELECT username, first_seen, last_seen, event_count, notes FROM tracked_users"
    )

    for i, row in enumerate(cursor, 1):
        row_dict = dict(row)
        params = {
            "username": row_dict["username"],
            "first_seen": row_dict["first_seen"],
            "last_seen": row_dict["last_seen"],
            "event_count": row_dict["event_count"] or 1,
            "region": region,
            "notes": row_dict.get("notes"),
        }
        batch.append(params)

        if len(batch) >= BATCH_SIZE:
            _flush_user_batch(ora_conn, batch)
            merged += len(batch)
            print(f"    {region}: {i:>10,} / {total:,}  (merged {merged:,})")
            batch = []

    if batch:
        _flush_user_batch(ora_conn, batch)
        merged += len(batch)

    sq.close()
    print(f"  [{region}] Tracked users done: {merged:,} merged")
    return merged


def _flush_user_batch(ora_conn: oracledb.Connection, batch: list[dict]):
    """Execute MERGE for a batch of tracked users."""
    with ora_conn.cursor() as cur:
        cur.executemany(MERGE_TRACKED_USER_SQL, batch)
    ora_conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    project_root = Path(__file__).resolve().parent.parent

    print("=" * 70)
    print("  Waze SQLite -> Oracle 26ai Migration")
    print("=" * 70)
    print(f"  Oracle DSN: {ORACLE_DSN.split('/')[0]}/***@{ORACLE_DSN.split('@')[1]}")
    print(f"  Batch size: {BATCH_SIZE:,}")
    print(f"  Regions:    {', '.join(REGION_DBS.keys())}")

    # Connect to Oracle
    try:
        ora_conn = connect_oracle()
        print("  Oracle connection: OK")
    except Exception as e:
        print(f"\n  ERROR connecting to Oracle: {e}", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    total_events_inserted = 0
    total_events_skipped = 0
    total_users_merged = 0

    for region, db_rel_path in REGION_DBS.items():
        db_path = project_root / db_rel_path
        if not db_path.exists():
            print(f"\n  [{region}] SKIPPED — {db_path} not found")
            continue

        print(f"\n{'─' * 70}")
        print(f"  Region: {region.upper()}")
        print(f"  Source:  {db_path}")
        print(f"{'─' * 70}")

        # Events
        ins, skp = migrate_events(ora_conn, str(db_path), region)
        total_events_inserted += ins
        total_events_skipped += skp

        # Tracked users
        merged = migrate_tracked_users(ora_conn, str(db_path), region)
        total_users_merged += merged

    elapsed = time.time() - t0

    print(f"\n{'=' * 70}")
    print(f"  Migration complete in {elapsed:.1f}s")
    print(f"  Events inserted: {total_events_inserted:,}")
    print(f"  Events skipped:  {total_events_skipped:,}")
    print(f"  Users merged:    {total_users_merged:,}")
    print(f"{'=' * 70}")

    ora_conn.close()


if __name__ == "__main__":
    main()
