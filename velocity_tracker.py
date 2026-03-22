"""Event velocity tracking for Waze traffic data.

Detects "waves" of same-type events that propagate geographically over time.
Uses a greedy seed-expansion algorithm: pick the earliest unassigned event,
grow the wave by pulling in same-type events within radius and time window.
"""

import uuid
from typing import Dict, List, Optional

from utils import haversine_km as _haversine_km

_DEFAULT_WAVE_RADIUS_KM = 5.0
_DEFAULT_WAVE_WINDOW_S = 1800
_MIN_WAVE_SIZE = 2


def _event_timestamp_s(event: Dict) -> Optional[float]:
    """Extract timestamp in seconds from an event dict."""
    ts_ms = event.get("timestamp_ms")
    if ts_ms is not None:
        return ts_ms / 1000.0
    return None


def _event_coords(event: Dict) -> Optional[tuple]:
    """Extract (lat, lon) from an event, or None if missing."""
    lat = event.get("latitude")
    lon = event.get("longitude")
    if lat is not None and lon is not None:
        return (float(lat), float(lon))
    return None


def find_event_waves(
    events: List[Dict],
    wave_radius_km: float = _DEFAULT_WAVE_RADIUS_KM,
    wave_window_s: int = _DEFAULT_WAVE_WINDOW_S,
) -> List[Dict]:
    """Find clusters of same-type events that spread geographically over time.

    Parameters
    ----------
    events : list[dict]
        Events with latitude, longitude, timestamp_ms, report_type (or type).
    wave_radius_km : float
        Maximum distance from the wave origin for an event to be included.
    wave_window_s : int
        Maximum time window in seconds from the origin event.

    Returns
    -------
    List of wave dicts sorted by size (largest first).
    """
    if not events:
        return []

    valid = []
    for e in events:
        coords = _event_coords(e)
        ts = _event_timestamp_s(e)
        etype = e.get("report_type") or e.get("type")
        if coords is not None and ts is not None and etype:
            valid.append(
                {
                    "event": e,
                    "lat": coords[0],
                    "lon": coords[1],
                    "ts_s": ts,
                    "type": str(etype),
                }
            )

    if len(valid) < _MIN_WAVE_SIZE:
        return []

    valid.sort(key=lambda v: v["ts_s"])

    by_type: Dict[str, List[Dict]] = {}
    for v in valid:
        by_type.setdefault(v["type"], []).append(v)

    waves = []

    for etype, type_events in by_type.items():
        if len(type_events) < _MIN_WAVE_SIZE:
            continue

        assigned = set()

        for i, seed in enumerate(type_events):
            if i in assigned:
                continue

            wave_members = [seed]
            assigned.add(i)

            origin_lat = seed["lat"]
            origin_lon = seed["lon"]
            origin_ts = seed["ts_s"]

            for j in range(i + 1, len(type_events)):
                if j in assigned:
                    continue

                candidate = type_events[j]
                dt = candidate["ts_s"] - origin_ts

                if dt > wave_window_s:
                    break

                if dt < 0:
                    continue

                dist = _haversine_km(origin_lat, origin_lon, candidate["lat"], candidate["lon"])
                if dist <= wave_radius_km:
                    wave_members.append(candidate)
                    assigned.add(j)

            if len(wave_members) < _MIN_WAVE_SIZE:
                continue

            max_dist = 0.0
            for m in wave_members:
                d = _haversine_km(origin_lat, origin_lon, m["lat"], m["lon"])
                if d > max_dist:
                    max_dist = d

            timestamps = [m["ts_s"] for m in wave_members]
            duration_s = int(max(timestamps) - min(timestamps))

            velocity_kmh = 0.0
            if duration_s > 0 and max_dist > 0:
                velocity_kmh = max_dist / (duration_s / 3600.0)

            waves.append(
                {
                    "wave_id": uuid.uuid4().hex[:12],
                    "event_type": etype,
                    "origin": {"lat": origin_lat, "lon": origin_lon},
                    "events": [m["event"] for m in wave_members],
                    "spread_km": round(max_dist, 3),
                    "duration_s": duration_s,
                    "velocity_kmh": round(velocity_kmh, 2),
                }
            )

    waves.sort(key=lambda w: len(w["events"]), reverse=True)
    return waves


def summarize_waves(waves: List[Dict]) -> Dict:
    """Produce a summary of detected waves."""
    if not waves:
        return {
            "total_waves": 0,
            "total_events_in_waves": 0,
            "avg_wave_size": 0,
            "avg_velocity_kmh": 0,
            "by_type": {},
        }

    total_events = sum(len(w["events"]) for w in waves)
    avg_size = total_events / len(waves)
    velocities = [w["velocity_kmh"] for w in waves if w["velocity_kmh"] > 0]
    avg_velocity = sum(velocities) / len(velocities) if velocities else 0.0

    by_type: Dict[str, int] = {}
    for w in waves:
        by_type[w["event_type"]] = by_type.get(w["event_type"], 0) + 1

    return {
        "total_waves": len(waves),
        "total_events_in_waves": total_events,
        "avg_wave_size": round(avg_size, 1),
        "avg_velocity_kmh": round(avg_velocity, 2),
        "by_type": by_type,
    }
