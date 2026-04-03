"""Cross-region intelligence briefing builder."""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from intel_routines import infer_routines
from ops_diagnostics import read_status_file
from privacy_score import compute_privacy_score


class SQLiteReadOnlyDB:
    """Minimal read-only SQLite wrapper for briefing-style queries."""

    db_type = "sqlite"

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(query, params)

    def close(self) -> None:
        self.conn.close()


def _limit_clause(db, limit: int) -> tuple[str, tuple[int, ...]]:
    if hasattr(db, "db_type") and db.db_type == "oracle":
        return " FETCH FIRST :1 ROWS ONLY", (limit,)
    return " LIMIT ?", (limit,)


def _row_count(row: Any, key: str, fallback_index: int = 0) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[fallback_index]


def _query_totals(db) -> dict[str, Any]:
    if getattr(db, "db_type", "") == "sqlite":
        row = db.execute("SELECT MIN(id) AS first_id, MAX(id) AS last_id FROM events").fetchone()
        first_id = _row_count(row, "first_id", 0)
        last_id = _row_count(row, "last_id", 1)
        total_events = int(last_id or 0)
        first_event = None
        last_event = None
        if first_id:
            first_row = db.execute(
                "SELECT timestamp_utc FROM events WHERE id = ?",
                (first_id,),
            ).fetchone()
            first_event = _row_count(first_row, "timestamp_utc", 0)
        if last_id:
            last_row = db.execute(
                "SELECT timestamp_utc FROM events WHERE id = ?",
                (last_id,),
            ).fetchone()
            last_event = _row_count(last_row, "timestamp_utc", 0)
    else:
        row = db.execute(
            "SELECT COUNT(*) AS total_events, "
            "MIN(timestamp_utc) AS first_event, MAX(timestamp_utc) AS last_event "
            "FROM events"
        ).fetchone()
        total_events = _row_count(row, "total_events", 0) or 0
        first_event = _row_count(row, "first_event", 1)
        last_event = _row_count(row, "last_event", 2)
    if getattr(db, "db_type", "") == "sqlite":
        try:
            user_row = db.execute("SELECT MAX(id) AS users FROM tracked_users").fetchone()
            users = _row_count(user_row, "users", 0) or 0
        except Exception:
            user_row = db.execute("SELECT COUNT(DISTINCT username) AS users FROM events").fetchone()
            users = _row_count(user_row, "users", 0) or 0
    else:
        user_row = db.execute("SELECT COUNT(DISTINCT username) AS users FROM events").fetchone()
        users = _row_count(user_row, "users", 0) or 0
    return {
        "total_events": total_events,
        "users": users,
        "first_event": first_event,
        "last_event": last_event,
    }


def _query_recent_region_summary(db, cutoff_ms: int) -> dict[str, Any]:
    row = db.execute(
        "SELECT COUNT(*) AS total_events, COUNT(DISTINCT username) AS users, "
        "MAX(timestamp_utc) AS last_event "
        "FROM events WHERE timestamp_ms >= ?",
        (cutoff_ms,),
    ).fetchone()
    return {
        "events": _row_count(row, "total_events", 0) or 0,
        "users": _row_count(row, "users", 1) or 0,
        "last_event": _row_count(row, "last_event", 2),
    }


def _query_recent_types(db, cutoff_ms: int) -> Counter[str]:
    rows = db.execute(
        "SELECT report_type, COUNT(*) AS count FROM events "
        "WHERE timestamp_ms >= ? GROUP BY report_type",
        (cutoff_ms,),
    ).fetchall()
    counter: Counter[str] = Counter()
    for row in rows:
        if isinstance(row, dict):
            counter[row["report_type"]] += int(row["count"])
        else:
            counter[row[0]] += int(row[1])
    return counter


def _query_recent_events(db, region: str, cutoff_ms: int, limit: int) -> list[dict[str, Any]]:
    limit_sql, params = _limit_clause(db, limit)
    rows = db.execute(
        "SELECT username, latitude, longitude, timestamp_utc, report_type, subtype "
        f"FROM events WHERE timestamp_ms >= ? ORDER BY timestamp_ms DESC{limit_sql}",
        (cutoff_ms, *params),
    ).fetchall()
    events = []
    for row in rows:
        if isinstance(row, dict):
            record = dict(row)
        else:
            record = {
                "username": row[0],
                "latitude": row[1],
                "longitude": row[2],
                "timestamp_utc": row[3],
                "report_type": row[4],
                "subtype": row[5],
            }
        record["region"] = region
        events.append(record)
    return events


def _query_recent_users(db, region: str, cutoff_ms: int, limit: int) -> list[dict[str, Any]]:
    limit_sql, params = _limit_clause(db, limit)
    rows = db.execute(
        "SELECT username, COUNT(*) AS count, MAX(timestamp_ms) AS last_seen_ms "
        "FROM events WHERE timestamp_ms >= ? AND username != ? GROUP BY username "
        f"ORDER BY count DESC{limit_sql}",
        (cutoff_ms, "anonymous", *params),
    ).fetchall()
    users = []
    for row in rows:
        if isinstance(row, dict):
            users.append(
                {
                    "username": row["username"],
                    "count": int(row["count"]),
                    "last_seen_ms": int(row["last_seen_ms"]),
                    "region": region,
                }
            )
        else:
            users.append(
                {
                    "username": row[0],
                    "count": int(row[1]),
                    "last_seen_ms": int(row[2]),
                    "region": region,
                }
            )
    return users


def _load_user_events(
    dbs: list[tuple[str, Any]], username: str, max_events: int = 250
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for region, db in dbs:
        limit_sql, params = _limit_clause(db, max_events)
        rows = db.execute(
            "SELECT latitude, longitude, timestamp_ms, report_type "
            f"FROM events WHERE username = ? ORDER BY timestamp_ms DESC{limit_sql}",
            (username, *params),
        ).fetchall()
        for row in rows:
            if isinstance(row, dict):
                event = dict(row)
            else:
                event = {
                    "latitude": row[0],
                    "longitude": row[1],
                    "timestamp_ms": row[2],
                    "report_type": row[3],
                }
            event["region"] = region
            events.append(event)
    events.sort(key=lambda item: item["timestamp_ms"])
    if len(events) > max_events:
        events = events[-max_events:]
    return events


def _build_alerts(
    region_summaries: list[dict[str, Any]], recent_hours: int
) -> list[dict[str, Any]]:
    alerts = []
    for summary in region_summaries:
        if summary["events"] >= 100:
            alerts.append(
                {
                    "type": "activity_spike",
                    "region": summary["region"],
                    "severity": "high" if summary["events"] >= 500 else "medium",
                    "message": (
                        f"{summary['region']} logged {summary['events']} events "
                        f"in the last {recent_hours}h."
                    ),
                }
            )
    return alerts


def open_briefing_dbs(
    project_root: str | Path, config: dict[str, Any] | None = None
) -> list[tuple[str, Any]]:
    """Open lightweight read-only SQLite databases for briefing queries."""
    root = Path(project_root)
    data_dir = root / "data"
    candidates = {
        "madrid": data_dir / "waze_madrid.db",
        "europe": data_dir / "waze_europe.db",
        "americas": data_dir / "waze_americas.db",
        "asia": data_dir / "waze_asia.db",
        "oceania": data_dir / "waze_oceania.db",
        "africa": data_dir / "waze_africa.db",
    }

    dbs: list[tuple[str, Any]] = []
    for region, path in candidates.items():
        if not path.exists():
            continue
        try:
            dbs.append((region, SQLiteReadOnlyDB(path)))
        except sqlite3.Error:
            continue
    return dbs


def build_briefing(
    dbs: list[tuple[str, Any]],
    *,
    status_path: str | None = None,
    status_file: str | None = None,
    recent_hours: int = 24,
    top_users: int = 5,
    top_events: int = 5,
    risk_users: int = 3,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a cross-region intelligence briefing."""
    current_time = now or datetime.now(timezone.utc)
    resolved_status_path = status_path or status_file or "data/collector_status.json"
    cutoff_ms = int((current_time.timestamp() - recent_hours * 3600) * 1000)

    total_events = 0
    observed_users = 0
    first_event = None
    last_event = None
    recent_type_counts: Counter[str] = Counter()
    region_summaries: list[dict[str, Any]] = []
    freshest_events: list[dict[str, Any]] = []
    recent_user_totals: dict[str, dict[str, Any]] = {}

    for region, db in dbs:
        totals = _query_totals(db)
        total_events += int(totals["total_events"])
        observed_users += int(totals["users"])
        if totals["first_event"] and (first_event is None or totals["first_event"] < first_event):
            first_event = totals["first_event"]
        if totals["last_event"] and (last_event is None or totals["last_event"] > last_event):
            last_event = totals["last_event"]

        recent = _query_recent_region_summary(db, cutoff_ms)
        region_summaries.append(
            {
                "region": region,
                "events": recent["events"],
                "users": recent["users"],
                "last_event": recent["last_event"],
            }
        )
        if recent["events"] == 0:
            continue

        recent_type_counts.update(_query_recent_types(db, cutoff_ms))
        freshest_events.extend(_query_recent_events(db, region, cutoff_ms, limit=5))

        for user in _query_recent_users(db, region, cutoff_ms, limit=top_users):
            current = recent_user_totals.setdefault(
                user["username"],
                {
                    "username": user["username"],
                    "recent_events": 0,
                    "regions": set(),
                    "last_seen_ms": 0,
                },
            )
            current["recent_events"] += user["count"]
            current["regions"].add(region)
            current["last_seen_ms"] = max(current["last_seen_ms"], user["last_seen_ms"])

    region_summaries.sort(key=lambda item: item["events"], reverse=True)
    freshest_events.sort(key=lambda item: item["timestamp_utc"], reverse=True)
    top_recent_users = sorted(
        recent_user_totals.values(),
        key=lambda item: (-item["recent_events"], -item["last_seen_ms"]),
    )[:top_users]

    high_risk_users = []
    for user in top_recent_users[:risk_users]:
        events = _load_user_events(dbs, user["username"])
        routines = infer_routines(events) if len(events) >= 10 else None
        score = compute_privacy_score(events=events, routines=routines)
        high_risk_users.append(
            {
                "username": user["username"],
                "recent_events": user["recent_events"],
                "regions": sorted(user["regions"]),
                "overall_score": score["overall_score"],
                "risk_level": score["risk_level"],
            }
        )

    top_types = [
        {"type": report_type, "count": count}
        for report_type, count in recent_type_counts.most_common(top_events)
    ]
    top_recent_users = [
        {
            "username": item["username"],
            "recent_events": item["recent_events"],
            "regions": sorted(item["regions"]),
        }
        for item in top_recent_users
    ]
    alerts = _build_alerts(region_summaries, recent_hours)
    status = read_status_file(resolved_status_path, now=current_time)
    hottest_region = region_summaries[0] if region_summaries else None
    if hottest_region and hottest_region["events"] > 0:
        headline = (
            f"{hottest_region['region']} leads with {hottest_region['events']} events "
            f"in the last {recent_hours}h."
        )
    else:
        headline = f"No activity detected in the last {recent_hours}h."

    return {
        "generated_at": current_time.isoformat(),
        "headline": headline,
        "status": status,
        "totals": {
            "total_events": total_events,
            "observed_users": observed_users,
            "first_event": first_event,
            "last_event": last_event,
        },
        "recent_window_hours": recent_hours,
        "regions": region_summaries,
        "top_event_types": top_types,
        "freshest_events": freshest_events[:top_events],
        "top_recent_users": top_recent_users,
        "high_risk_users": high_risk_users,
        "alerts": alerts,
    }


def render_briefing_text(briefing: dict[str, Any]) -> str:
    """Render the briefing in a compact plain-text form."""
    lines = [
        "Waze Briefing",
        "=============",
        f"Generated: {briefing['generated_at']}",
        f"Headline: {briefing['headline']}",
        f"Collector status: {briefing['status'].get('status', 'unknown')}",
        "",
        f"Totals: {briefing['totals']['total_events']:,} events, "
        f"{briefing['totals']['observed_users']:,} observed users",
        f"Window: last {briefing['recent_window_hours']}h",
        "",
        "Regions:",
    ]

    for region in briefing["regions"][:5]:
        last_event = region["last_event"] or "n/a"
        lines.append(
            f"  - {region['region']}: {region['events']} events, "
            f"{region['users']} users, last={last_event}"
        )

    lines.append("")
    lines.append("Top event types:")
    for item in briefing["top_event_types"]:
        lines.append(f"  - {item['type']}: {item['count']}")

    lines.append("")
    lines.append("Top recent users:")
    for item in briefing["top_recent_users"]:
        regions = ", ".join(item["regions"])
        lines.append(f"  - {item['username']}: {item['recent_events']} events across {regions}")

    lines.append("")
    lines.append("High-risk recent users:")
    if briefing["high_risk_users"]:
        for item in briefing["high_risk_users"]:
            lines.append(
                f"  - {item['username']}: {item['overall_score']}/100 ({item['risk_level']})"
            )
    else:
        lines.append("  - None")

    lines.append("")
    lines.append("Alerts:")
    if briefing["alerts"]:
        for alert in briefing["alerts"]:
            lines.append(f"  - [{alert['severity']}] {alert['message']}")
    else:
        lines.append("  - None")

    return "\n".join(lines)


def render_briefing_markdown(briefing: dict[str, Any]) -> str:
    """Render the briefing in a compact markdown-friendly form."""
    lines = [
        "# Waze Briefing",
        "",
        f"- Generated: `{briefing['generated_at']}`",
        f"- Headline: {briefing['headline']}",
        f"- Collector status: `{briefing['status'].get('status', 'unknown')}`",
        "",
        "## Totals",
        f"- Total events: {briefing['totals']['total_events']:,}",
        f"- Observed users (regional sum): {briefing['totals']['observed_users']:,}",
        f"- First event: {briefing['totals']['first_event'] or 'n/a'}",
        f"- Last event: {briefing['totals']['last_event'] or 'n/a'}",
        "",
        f"## Recent Activity ({briefing['recent_window_hours']}h)",
    ]

    for region in briefing["regions"][:5]:
        last_event = region["last_event"] or "n/a"
        lines.append(
            f"- {region['region']}: {region['events']} events, "
            f"{region['users']} users, last={last_event}"
        )

    lines.extend(["", "## Top Event Types"])
    for item in briefing["top_event_types"]:
        lines.append(f"- {item['type']}: {item['count']}")

    lines.extend(["", "## Top Recent Users"])
    for item in briefing["top_recent_users"]:
        regions = ", ".join(item["regions"])
        lines.append(f"- {item['username']}: {item['recent_events']} events across {regions}")

    lines.extend(["", "## High-Risk Recent Users"])
    if briefing["high_risk_users"]:
        for item in briefing["high_risk_users"]:
            lines.append(
                f"- {item['username']}: {item['overall_score']}/100 "
                f"({item['risk_level']}), recent={item['recent_events']}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Alerts"])
    if briefing["alerts"]:
        for alert in briefing["alerts"]:
            lines.append(f"- [{alert['severity']}] {alert['message']}")
    else:
        lines.append("- None")

    return "\n".join(lines)
