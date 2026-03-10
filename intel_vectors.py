# intel_vectors.py
"""Behavioral vector construction for user fingerprinting.

Builds 44-dimensional behavioral fingerprint vectors from user event data.

Vector dimensions:
  0-23:  Hour-of-day histogram (normalized)
  24-30: Day-of-week histogram (normalized)
  31-32: Geographic centroid (min-max normalized within region bbox)
  33:    Geographic spread (log-scaled std dev of distances from centroid in km)
  34-39: Event type distribution (6 types, normalized)
  40:    Reporting cadence mean (log-scaled hours between reports)
  41:    Reporting cadence std (log-scaled)
  42:    Reporting cadence median (log-scaled)
  43:    Total activity (log10 event count, normalized by max_event_count)
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from numpy import ndarray

EVENT_TYPES = ["POLICE", "JAM", "HAZARD", "ACCIDENT", "ROAD_CLOSED", "CHIT_CHAT"]

# Region bounding boxes: {name: (lat_min, lat_max, lon_min, lon_max)}
REGION_BBOXES: Dict[str, tuple] = {
    "madrid": (40.30, 40.55, -3.85, -3.55),
    "barcelona": (41.30, 41.50, 2.05, 2.25),
    "europe_west": (36.0, 55.0, -10.0, 15.0),
    "europe_east": (36.0, 55.0, 15.0, 40.0),
    "north_america": (25.0, 50.0, -130.0, -60.0),
    "south_america": (-55.0, 15.0, -80.0, -35.0),
    "asia_east": (20.0, 50.0, 100.0, 150.0),
    "global": (-90.0, 90.0, -180.0, 180.0),
}


def build_hour_histogram(hours: List[int]) -> List[float]:
    """Build a 24-bin normalized histogram from a list of hour values (0-23).

    Args:
        hours: List of integer hours (0-23).

    Returns:
        List of 24 floats summing to 1.0, or all zeros if input is empty.
    """
    hist = [0.0] * 24
    for h in hours:
        hist[h] += 1.0
    total = sum(hist)
    if total > 0:
        hist = [v / total for v in hist]
    return hist


def build_dow_histogram(dows: List[int]) -> List[float]:
    """Build a 7-bin normalized histogram from day-of-week values (0=Monday .. 6=Sunday).

    Args:
        dows: List of integer day-of-week values (0-6).

    Returns:
        List of 7 floats summing to 1.0, or all zeros if input is empty.
    """
    hist = [0.0] * 7
    for d in dows:
        hist[d] += 1.0
    total = sum(hist)
    if total > 0:
        hist = [v / total for v in hist]
    return hist


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Haversine distance in kilometers between two points.

    Args:
        lat1, lon1: Latitude and longitude of point 1 in degrees.
        lat2, lon2: Latitude and longitude of point 2 in degrees.

    Returns:
        Distance in kilometers.
    """
    earth_radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


def cosine_similarity(a: ndarray, b: ndarray) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a, b: numpy arrays of the same shape.

    Returns:
        Cosine similarity in [-1, 1]. Returns 0.0 if either vector is zero.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _safe_log_norm(value: float, max_value: float) -> float:
    """Log-scale and normalize a non-negative value to [0, 1].

    Uses log1p for the transform and divides by log1p(max_value) to normalize.
    """
    if value <= 0:
        return 0.0
    return math.log1p(value) / math.log1p(max_value)


# Normalization caps for log-scaled dimensions
_MAX_SPREAD_KM = 50.0  # Max expected geographic spread in km
_MAX_CADENCE_HOURS = 720.0  # Max expected gap between reports (~30 days)


def build_behavioral_vector(
    events: List[Dict[str, Any]],
    region_bbox: tuple,
    max_event_count: Optional[int] = None,
) -> np.ndarray:
    """Build a 44-dimensional behavioral fingerprint vector from user events.

    Args:
        events: List of event dicts, each with keys:
            - latitude (float)
            - longitude (float)
            - timestamp_ms (int): Unix timestamp in milliseconds
            - report_type (str): One of EVENT_TYPES
        region_bbox: Tuple of (lat_min, lat_max, lon_min, lon_max) for normalization.
        max_event_count: Optional max event count for normalizing dim 43.
            If None, uses the length of events.

    Returns:
        numpy array of shape (44,) with all finite values.
    """
    vec = np.zeros(44, dtype=np.float64)

    if not events:
        return vec

    lat_min, lat_max, lon_min, lon_max = region_bbox

    # Extract temporal features
    datetimes = []
    for e in events:
        dt = datetime.fromtimestamp(e["timestamp_ms"] / 1000.0, tz=timezone.utc)
        datetimes.append(dt)

    hours = [dt.hour for dt in datetimes]
    dows = [dt.weekday() for dt in datetimes]

    # Dims 0-23: Hour-of-day histogram
    hour_hist = build_hour_histogram(hours)
    vec[0:24] = hour_hist

    # Dims 24-30: Day-of-week histogram
    dow_hist = build_dow_histogram(dows)
    vec[24:31] = dow_hist

    # Geographic features
    lats = [e["latitude"] for e in events]
    lons = [e["longitude"] for e in events]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    # Dims 31-32: Geographic centroid (min-max normalized)
    lat_range = lat_max - lat_min
    lon_range = lon_max - lon_min
    vec[31] = (center_lat - lat_min) / lat_range if lat_range > 0 else 0.5
    vec[32] = (center_lon - lon_min) / lon_range if lon_range > 0 else 0.5

    # Dim 33: Geographic spread (log-scaled std dev of distances from centroid)
    if len(events) > 1:
        distances = [haversine_km(center_lat, center_lon, lat, lon) for lat, lon in zip(lats, lons)]
        spread_std = float(np.std(distances))
        vec[33] = _safe_log_norm(spread_std, _MAX_SPREAD_KM)
    else:
        vec[33] = 0.0

    # Dims 34-39: Event type distribution
    type_counts = [0.0] * len(EVENT_TYPES)
    for e in events:
        rt = e.get("report_type", "")
        if rt in EVENT_TYPES:
            type_counts[EVENT_TYPES.index(rt)] += 1.0
    type_total = sum(type_counts)
    if type_total > 0:
        type_counts = [c / type_total for c in type_counts]
    vec[34:40] = type_counts

    # Reporting cadence (time gaps between consecutive reports)
    if len(events) > 1:
        timestamps_ms = sorted(e["timestamp_ms"] for e in events)
        gaps_hours = [
            (timestamps_ms[i + 1] - timestamps_ms[i]) / 3_600_000.0
            for i in range(len(timestamps_ms) - 1)
        ]
        # Dim 40: Mean cadence (log-scaled, normalized)
        vec[40] = _safe_log_norm(float(np.mean(gaps_hours)), _MAX_CADENCE_HOURS)
        # Dim 41: Std cadence (log-scaled, normalized)
        vec[41] = _safe_log_norm(float(np.std(gaps_hours)), _MAX_CADENCE_HOURS)
        # Dim 42: Median cadence (log-scaled, normalized)
        vec[42] = _safe_log_norm(float(np.median(gaps_hours)), _MAX_CADENCE_HOURS)
    else:
        vec[40] = 0.0
        vec[41] = 0.0
        vec[42] = 0.0

    # Dim 43: Total activity (log10 event count, normalized)
    n = len(events)
    if max_event_count is None:
        max_event_count = n
    if max_event_count > 0:
        vec[43] = math.log10(1 + n) / math.log10(1 + max_event_count)
    else:
        vec[43] = 0.0

    return vec
