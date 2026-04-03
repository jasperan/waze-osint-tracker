"""Trip reconstruction engine — connects sparse GPS events into driving routes.

Segments time-ordered events into trips, computes distances, durations, and
classifies trips against known routine locations (home/work/commute).
"""

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils import haversine_km as _haversine_km

# Maximum gap between consecutive events to be considered same trip (seconds)
MAX_TRIP_GAP_S = 7200  # 2 hours

# Speed bounds for plausible driving (km/h)
MIN_SPEED_KMH = 2.0
MAX_SPEED_KMH = 200.0

# Minimum waypoints to form a valid trip
MIN_WAYPOINTS = 2


@dataclass
class Trip:
    """A reconstructed driving trip from event sequence."""

    trip_id: str
    username: str
    started_at: str  # ISO format
    ended_at: str  # ISO format
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    waypoints: List[Dict] = field(default_factory=list)
    distance_km: float = 0.0
    duration_minutes: float = 0.0
    avg_speed_kmh: float = 0.0
    waypoint_count: int = 0
    trip_type: str = "OTHER"

    def to_dict(self) -> Dict:
        return asdict(self)


def _generate_trip_id(username: str, start_ts: int, end_ts: int) -> str:
    """Deterministic trip ID from username + start/end timestamps."""
    raw = f"{username}:{start_ts}:{end_ts}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _segment_events(events: List[Dict], max_gap_s: int = MAX_TRIP_GAP_S) -> List[List[Dict]]:
    """Split time-ordered events into trip segments based on time gaps.

    Parameters
    ----------
    events : list[dict]
        Must have ``timestamp_ms`` key. Assumed sorted by timestamp_ms ASC.
    max_gap_s : int
        Maximum gap in seconds before starting a new segment.

    Returns
    -------
    list[list[dict]]
        Each inner list is a trip segment with >= 1 event.
    """
    if not events:
        return []

    segments = []
    current = [events[0]]

    for i in range(1, len(events)):
        gap_s = (events[i]["timestamp_ms"] - events[i - 1]["timestamp_ms"]) / 1000.0
        if gap_s > max_gap_s:
            segments.append(current)
            current = [events[i]]
        else:
            current.append(events[i])

    segments.append(current)
    return segments


def _compute_segment_distance(waypoints: List[Dict]) -> float:
    """Total distance along waypoint sequence in km."""
    total = 0.0
    for i in range(1, len(waypoints)):
        total += _haversine_km(
            waypoints[i - 1]["latitude"],
            waypoints[i - 1]["longitude"],
            waypoints[i]["latitude"],
            waypoints[i]["longitude"],
        )
    return total


def _classify_trip(
    trip_start: tuple,
    trip_end: tuple,
    routines: Optional[Dict] = None,
    proximity_km: float = 1.0,
) -> str:
    """Classify a trip based on proximity to known routine locations.

    Parameters
    ----------
    trip_start : (lat, lon)
    trip_end : (lat, lon)
    routines : dict or None
        Keys: 'HOME', 'WORK', etc. Values have 'latitude', 'longitude'.
    proximity_km : float
        Max distance to consider "near" a routine location.

    Returns
    -------
    str
        One of: MORNING_COMMUTE, EVENING_COMMUTE, ROUND_TRIP, HOME_DEPARTURE,
        WORK_DEPARTURE, OTHER.
    """
    if not routines:
        return "OTHER"

    def near(point, routine_key):
        if routine_key not in routines:
            return False
        r = routines[routine_key]
        return _haversine_km(point[0], point[1], r["latitude"], r["longitude"]) <= proximity_km

    start_home = near(trip_start, "HOME")
    start_work = near(trip_start, "WORK")
    end_home = near(trip_end, "HOME")
    end_work = near(trip_end, "WORK")

    if start_home and end_work:
        return "MORNING_COMMUTE"
    if start_work and end_home:
        return "EVENING_COMMUTE"
    if start_home and end_home:
        return "ROUND_TRIP"
    if start_home:
        return "HOME_DEPARTURE"
    if start_work:
        return "WORK_DEPARTURE"
    return "OTHER"


def reconstruct_trips(
    events: List[Dict],
    username: str,
    routines: Optional[Dict] = None,
    max_gap_s: int = MAX_TRIP_GAP_S,
    min_waypoints: int = MIN_WAYPOINTS,
) -> List[Trip]:
    """Reconstruct driving trips from a user's event sequence.

    Parameters
    ----------
    events : list[dict]
        Each dict must have: latitude, longitude, timestamp_ms, report_type.
    username : str
        The Waze username.
    routines : dict or None
        Known routine locations (HOME, WORK) for trip classification.
    max_gap_s : int
        Maximum gap in seconds to consider events part of the same trip.
    min_waypoints : int
        Minimum number of waypoints for a valid trip.

    Returns
    -------
    list[Trip]
        Reconstructed trips, sorted by start time.
    """
    if len(events) < min_waypoints:
        return []

    # Sort by timestamp
    sorted_events = sorted(events, key=lambda e: e["timestamp_ms"])

    # Segment into trips
    segments = _segment_events(sorted_events, max_gap_s=max_gap_s)

    trips = []
    for segment in segments:
        if len(segment) < min_waypoints:
            continue

        # Build waypoints
        waypoints = [
            {
                "latitude": e["latitude"],
                "longitude": e["longitude"],
                "timestamp_ms": e["timestamp_ms"],
                "report_type": e.get("report_type", "UNKNOWN"),
            }
            for e in segment
        ]

        # Compute metrics
        distance_km = _compute_segment_distance(waypoints)
        start_ts = segment[0]["timestamp_ms"]
        end_ts = segment[-1]["timestamp_ms"]
        duration_s = (end_ts - start_ts) / 1000.0
        duration_min = duration_s / 60.0

        # Validate speed
        if duration_s > 0:
            avg_speed = (distance_km / duration_s) * 3600
        else:
            avg_speed = 0.0

        # Skip implausible trips (teleportation or stationary)
        if distance_km > 0.1 and (avg_speed < MIN_SPEED_KMH or avg_speed > MAX_SPEED_KMH):
            continue

        # Classify
        trip_start = (segment[0]["latitude"], segment[0]["longitude"])
        trip_end = (segment[-1]["latitude"], segment[-1]["longitude"])
        trip_type = _classify_trip(trip_start, trip_end, routines)

        # Build datetimes
        started_at = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc).isoformat()
        ended_at = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc).isoformat()

        trip = Trip(
            trip_id=_generate_trip_id(username, start_ts, end_ts),
            username=username,
            started_at=started_at,
            ended_at=ended_at,
            start_lat=segment[0]["latitude"],
            start_lon=segment[0]["longitude"],
            end_lat=segment[-1]["latitude"],
            end_lon=segment[-1]["longitude"],
            waypoints=waypoints,
            distance_km=round(distance_km, 2),
            duration_minutes=round(duration_min, 2),
            avg_speed_kmh=round(avg_speed, 2),
            waypoint_count=len(waypoints),
            trip_type=trip_type,
        )
        trips.append(trip)

    return trips


def get_trip_summary(trips: List[Trip]) -> Dict:
    """Summarize a list of trips into aggregate statistics.

    Returns dict with: total_trips, total_distance_km, total_duration_hours,
    avg_trip_distance_km, avg_trip_duration_min, trip_types (count by type),
    most_common_type.
    """
    if not trips:
        return {
            "total_trips": 0,
            "total_distance_km": 0,
            "total_duration_hours": 0,
            "avg_trip_distance_km": 0,
            "avg_trip_duration_min": 0,
            "trip_types": {},
            "most_common_type": None,
        }

    total_dist = sum(t.distance_km for t in trips)
    total_dur_min = sum(t.duration_minutes for t in trips)

    type_counts: Dict[str, int] = {}
    for t in trips:
        type_counts[t.trip_type] = type_counts.get(t.trip_type, 0) + 1

    most_common = max(type_counts, key=lambda key: type_counts[key]) if type_counts else None

    return {
        "total_trips": len(trips),
        "total_distance_km": round(total_dist, 2),
        "total_duration_hours": round(total_dur_min / 60, 2),
        "avg_trip_distance_km": round(total_dist / len(trips), 2),
        "avg_trip_duration_min": round(total_dur_min / len(trips), 2),
        "trip_types": type_counts,
        "most_common_type": most_common,
    }
