"""Shared event query filter helpers for Flask API routes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class EventFilterResult:
    conditions: list[str] = field(default_factory=list)
    params: list[Any] = field(default_factory=list)
    region_filter: str | None = None
    error_message: str | None = None


def parse_event_filters(
    args: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> EventFilterResult:
    """Parse common event query parameters into SQL fragments."""
    event_type = args.get("type")
    event_subtype = args.get("subtype")
    since = args.get("since")
    date_from = args.get("from")
    date_to = args.get("to")
    username = args.get("user")
    region_filter = args.get("region")

    conditions: list[str] = []
    params: list[Any] = []

    if event_type:
        conditions.append("report_type = ?")
        params.append(str(event_type).upper())

    if event_subtype:
        conditions.append("subtype = ?")
        params.append(event_subtype)

    if username:
        conditions.append("username = ?")
        params.append(username)

    if since:
        try:
            hours = int(since)
        except (ValueError, TypeError):
            return EventFilterResult(
                region_filter=region_filter,
                error_message="Invalid 'since' parameter, must be integer",
            )
        try:
            cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=hours)
        except OverflowError:
            cutoff = datetime(1970, 1, 1, tzinfo=timezone.utc)
        conditions.append("timestamp_utc >= ?")
        params.append(cutoff.isoformat())
    elif date_from:
        conditions.append("timestamp_utc >= ?")
        params.append(date_from)

    if date_to:
        date_to_val = str(date_to)
        if len(date_to_val) == 10:
            date_to_val += "T23:59:59"
        conditions.append("timestamp_utc <= ?")
        params.append(date_to_val)

    return EventFilterResult(
        conditions=conditions,
        params=params,
        region_filter=region_filter,
    )


def build_where(
    conditions: list[str],
    params: list[Any],
    region_filter: str | None,
    region: str,
) -> tuple[str, tuple[Any, ...]]:
    """Copy base conditions and add Oracle region filtering when needed."""
    parts = list(conditions)
    query_params = list(params)
    if region_filter and region == "all":
        parts.append("region = ?")
        query_params.append(region_filter)
    clause = " AND ".join(parts) if parts else "1=1"
    return clause, tuple(query_params)
