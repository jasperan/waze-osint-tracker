"""Helpers for resolving users across regional databases."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _timestamp_ms_from_iso(value: str | None) -> int:
    if not value:
        return 0
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def find_user_match(username: str, dbs: list[tuple[str, Any]]) -> dict[str, Any] | None:
    """Return the best regional DB match for *username*.

    The best match is the region where the user exists and has the most recent event.
    """
    best: dict[str, Any] | None = None
    for region, db in dbs:
        row = None
        event_count = 0
        last_seen_ms = 0

        try:
            row = db.execute(
                "SELECT event_count, last_seen FROM tracked_users WHERE username = ?",
                (username,),
            ).fetchone()
        except Exception:
            row = None

        if row:
            event_count = int(_row_value(row, "event_count", 0) or 0)
            last_seen_ms = _timestamp_ms_from_iso(_row_value(row, "last_seen", 1))

        if event_count == 0:
            row = db.execute(
                "SELECT COUNT(*) AS event_count, MAX(timestamp_ms) AS last_seen_ms "
                "FROM events WHERE username = ?",
                (username,),
            ).fetchone()
            event_count = int(_row_value(row, "event_count", 0) or 0)
            last_seen_ms = int(_row_value(row, "last_seen_ms", 1) or 0)

        if event_count == 0:
            continue
        candidate = {
            "region": region,
            "db": db,
            "event_count": event_count,
            "last_seen_ms": last_seen_ms,
        }
        if best is None or last_seen_ms > int(best["last_seen_ms"]):
            best = candidate
    return best
