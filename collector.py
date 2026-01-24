# collector.py
import hashlib
import json
import time
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

def generate_event_hash(
    username: str,
    latitude: float,
    longitude: float,
    timestamp_ms: int,
    report_type: str
) -> str:
    """Generate unique hash for event deduplication."""
    # Round timestamp to minute for dedup (same event reported twice in same minute)
    timestamp_minute = timestamp_ms // 60000
    # Round coordinates to 4 decimal places (~11m precision)
    lat_rounded = round(latitude, 4)
    lon_rounded = round(longitude, 4)

    data = f"{username}|{lat_rounded}|{lon_rounded}|{timestamp_minute}|{report_type}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]

def process_alert(alert: Dict[str, Any], grid_cell: str) -> Dict[str, Any]:
    """Process raw Waze alert into event record."""
    username = alert.get("reportBy", "anonymous")
    latitude = alert.get("latitude", 0.0)
    longitude = alert.get("longitude", 0.0)
    timestamp_ms = alert.get("pubMillis", int(time.time() * 1000))
    report_type = alert.get("type", "UNKNOWN")
    subtype = alert.get("subtype")

    timestamp_utc = datetime.fromtimestamp(
        timestamp_ms / 1000, tz=timezone.utc
    ).isoformat()

    event_hash = generate_event_hash(
        username=username,
        latitude=latitude,
        longitude=longitude,
        timestamp_ms=timestamp_ms,
        report_type=report_type
    )

    return {
        "event_hash": event_hash,
        "username": username,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp_utc": timestamp_utc,
        "timestamp_ms": timestamp_ms,
        "report_type": report_type,
        "subtype": subtype,
        "raw_json": json.dumps(alert),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "grid_cell": grid_cell
    }
