# report_generator.py
"""Generate per-user OSINT reports from collected Waze events."""

import os
from collections import Counter
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "templates")


def _cluster_locations(events, max_clusters=10):
    """Group events into grid clusters by rounding coords to ~1 km resolution."""
    grid = Counter()
    grid_hours: dict[tuple, list[int]] = {}
    for ev in events:
        key = (round(ev["latitude"], 2), round(ev["longitude"], 2))
        grid[key] += 1
        try:
            ts = datetime.fromisoformat(ev["timestamp_utc"].replace("Z", "+00:00"))
            grid_hours.setdefault(key, []).append(ts.hour)
        except Exception:
            grid_hours.setdefault(key, [])

    clusters = []
    for (lat, lon), count in grid.most_common(max_clusters):
        hours = grid_hours.get((lat, lon), [])
        avg_hour = sum(hours) / len(hours) if hours else 12
        if avg_hour >= 22 or avg_hour < 7:
            label = "possible_home"
        elif 9 <= avg_hour <= 17:
            label = "possible_work"
        else:
            label = "transit"
        clusters.append({"lat": lat, "lon": lon, "count": count, "label": label})
    return clusters


def _risk_assessment(events):
    """Compute risk sub-scores from event patterns."""
    if not events:
        return {
            "overall": 0,
            "schedule_predictability": 0,
            "location_concentration": 0,
            "trackability": 0,
        }

    total = len(events)

    # Schedule predictability: max concentration in any (day_of_week, hour) bucket
    time_buckets = Counter()
    for ev in events:
        try:
            ts = datetime.fromisoformat(ev["timestamp_utc"].replace("Z", "+00:00"))
            time_buckets[(ts.weekday(), ts.hour)] += 1
        except Exception:
            pass
    if time_buckets:
        max_bucket = max(time_buckets.values())
        schedule_predictability = min(round((max_bucket / total) * 100, 1), 100)
    else:
        schedule_predictability = 0

    # Location concentration: 1 - (unique_locations / total)
    unique_locs = len({(round(ev["latitude"], 4), round(ev["longitude"], 4)) for ev in events})
    location_concentration = round((1 - unique_locs / total) * 100, 1) if total > 0 else 0

    # Trackability: min(total / 2, 100)
    trackability = min(round(total / 2, 1), 100)

    # Overall: weighted blend
    overall = round(
        0.35 * schedule_predictability + 0.35 * location_concentration + 0.30 * trackability,
        1,
    )

    return {
        "overall": overall,
        "schedule_predictability": schedule_predictability,
        "location_concentration": location_concentration,
        "trackability": trackability,
    }


def _bounding_box_area_km2(events):
    """Compute bounding-box area in km^2 from event coordinates."""
    if not events:
        return 0.0
    import math

    lats = [ev["latitude"] for ev in events]
    lons = [ev["longitude"] for ev in events]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    dlat_km = (max_lat - min_lat) * 111.32
    avg_lat_rad = math.radians((min_lat + max_lat) / 2)
    dlon_km = (max_lon - min_lon) * 111.32 * math.cos(avg_lat_rad)
    return round(abs(dlat_km * dlon_km), 2)


def generate_user_report(username: str, db) -> dict:
    """Build a full OSINT report dict for *username* from *db*."""
    rows = db.execute(
        "SELECT * FROM events WHERE username = ? ORDER BY timestamp_ms DESC",
        (username,),
    ).fetchall()
    events = [dict(r) for r in rows]

    total = len(events)
    generated_at = datetime.now(timezone.utc).isoformat()

    if total == 0:
        return {
            "username": username,
            "generated_at": generated_at,
            "total_events": 0,
            "event_types": [],
            "timeline": [],
            "locations": [],
            "risk_assessment": _risk_assessment([]),
            "active_days": 0,
            "area_km2": 0.0,
        }

    # Event types breakdown
    type_counter = Counter(ev["report_type"] for ev in events)
    event_types = [
        {"type": t, "count": c, "pct": round(c / total * 100, 1)}
        for t, c in type_counter.most_common()
    ]

    # Timeline: last 20 events (already sorted DESC)
    timeline = [
        {
            "timestamp": ev["timestamp_utc"],
            "type": ev["report_type"],
            "lat": ev["latitude"],
            "lon": ev["longitude"],
        }
        for ev in events[:20]
    ]

    # Active days
    active_dates = set()
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev["timestamp_utc"].replace("Z", "+00:00"))
            active_dates.add(dt.date())
        except Exception:
            pass

    return {
        "username": username,
        "generated_at": generated_at,
        "total_events": total,
        "event_types": event_types,
        "timeline": timeline,
        "locations": _cluster_locations(events),
        "risk_assessment": _risk_assessment(events),
        "active_days": len(active_dates),
        "area_km2": _bounding_box_area_km2(events),
    }


def render_report_html(report: dict) -> str:
    """Render *report* dict to a self-contained HTML string via Jinja2."""
    env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True)
    template = env.get_template("report.html")
    return template.render(report=report)
