# analysis.py
from typing import Dict, Any, List, Optional
from database import Database

def get_stats(db: Database) -> Dict[str, Any]:
    """Get summary statistics from the database."""
    total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    unique_users = db.execute("SELECT COUNT(DISTINCT username) FROM events").fetchone()[0]

    # By type
    type_rows = db.execute(
        "SELECT report_type, COUNT(*) as count FROM events GROUP BY report_type"
    ).fetchall()
    by_type = {row["report_type"]: row["count"] for row in type_rows}

    # Time range
    time_range = db.execute(
        "SELECT MIN(timestamp_utc) as first, MAX(timestamp_utc) as last FROM events"
    ).fetchone()

    return {
        "total_events": total,
        "unique_users": unique_users,
        "by_type": by_type,
        "first_event": time_range["first"],
        "last_event": time_range["last"]
    }

def get_recent_events(db: Database, limit: int = 20) -> List[Dict[str, Any]]:
    """Get most recent events."""
    rows = db.execute(
        "SELECT * FROM events ORDER BY timestamp_ms DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(row) for row in rows]

def get_user_events(db: Database, username: str) -> List[Dict[str, Any]]:
    """Get all events from a specific user."""
    rows = db.execute(
        "SELECT * FROM events WHERE username = ? ORDER BY timestamp_ms",
        (username,)
    ).fetchall()
    return [dict(row) for row in rows]

def get_users_summary(db: Database, limit: int = 50) -> List[Dict[str, Any]]:
    """Get summary of users with event counts."""
    rows = db.execute("""
        SELECT
            username,
            COUNT(*) as event_count,
            MIN(timestamp_utc) as first_seen,
            MAX(timestamp_utc) as last_seen
        FROM events
        GROUP BY username
        ORDER BY event_count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(row) for row in rows]

def get_user_profile(db: Database, username: str) -> Optional[Dict[str, Any]]:
    """Get detailed profile for a user."""
    events = get_user_events(db, username)
    if not events:
        return None

    # Basic stats
    event_count = len(events)
    first_seen = events[0]["timestamp_utc"]
    last_seen = events[-1]["timestamp_utc"]

    # Type breakdown
    type_counts = {}
    for e in events:
        t = e["report_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    # Location analysis (simple centroid)
    lats = [e["latitude"] for e in events]
    lons = [e["longitude"] for e in events]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    return {
        "username": username,
        "event_count": event_count,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "type_breakdown": type_counts,
        "center_location": {"lat": center_lat, "lon": center_lon},
        "events": events
    }
