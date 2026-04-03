"""Anomaly detection engine for Waze user behavior.

Detects three types of anomalous behavior:
  - Time anomaly: reporting at unusual hours (z-score on hour histogram)
  - Location anomaly: appearing far from geographic centroid
  - Frequency anomaly: sudden spikes or drops in reporting cadence

Each anomaly is scored individually, then combined into an overall 0-100 score.
"""

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from utils import haversine_km as _haversine_km

# Minimum events needed for meaningful anomaly detection
_MIN_EVENTS_TIME = 5
_MIN_EVENTS_LOCATION = 3
_MIN_EVENTS_FREQUENCY = 7  # need at least a week of daily buckets

# Z-score threshold above which an observation is "anomalous"
_ZSCORE_THRESHOLD = 2.0


def _zscore(value: float, mean: float, std: float) -> float:
    """Compute z-score, returning 0.0 when std is zero."""
    if std == 0:
        return 0.0
    return abs(value - mean) / std


def _build_hour_histogram(events: List[Dict]) -> List[int]:
    """Build a 24-bin raw count histogram of reporting hours."""
    hist = [0] * 24
    for e in events:
        ts_ms = e.get("timestamp_ms")
        if ts_ms is None:
            continue
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        hist[dt.hour] += 1
    return hist


def _geographic_centroid(events: List[Dict]) -> tuple:
    """Compute mean latitude and longitude from events.

    Returns (lat, lon) or (None, None) if no valid coordinates exist.
    """
    lats, lons = [], []
    for e in events:
        lat = e.get("latitude")
        lon = e.get("longitude")
        if lat is not None and lon is not None:
            lats.append(float(lat))
            lons.append(float(lon))
    if not lats:
        return None, None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _geo_spread_km(events: List[Dict], centroid_lat: float, centroid_lon: float) -> float:
    """Compute mean distance (km) of events from centroid."""
    distances = []
    for e in events:
        lat = e.get("latitude")
        lon = e.get("longitude")
        if lat is not None and lon is not None:
            distances.append(_haversine_km(float(lat), float(lon), centroid_lat, centroid_lon))
    if not distances:
        return 0.0
    return sum(distances) / len(distances)


def _std_dev(values: Sequence[float | int]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def detect_time_anomalies(
    events: List[Dict],
    recent_events: Optional[List[Dict]] = None,
) -> Dict:
    """Detect events at unusual hours based on the user's historical hour histogram.

    Returns dict with score (0-100) and anomalies list.
    """
    empty: Dict = {"score": 0.0, "anomalies": []}

    if len(events) < _MIN_EVENTS_TIME:
        return empty

    hist = _build_hour_histogram(events)
    total = sum(hist)
    if total == 0:
        return empty

    probs = [h / total for h in hist]
    mean_prob = sum(probs) / 24
    std_prob = _std_dev(probs)

    if recent_events is None:
        cutoff = max(1, len(events) * 4 // 5)
        recent_events = events[cutoff:]

    anomalies: List[Dict] = []
    for e in recent_events:
        ts_ms = e.get("timestamp_ms")
        if ts_ms is None:
            continue
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        hour = dt.hour
        hour_prob = probs[hour]
        z = _zscore(hour_prob, mean_prob, std_prob)

        if hour_prob < mean_prob and z > _ZSCORE_THRESHOLD:
            score = min(z / 4.0 * 100, 100.0)
            anomalies.append(
                {
                    "type": "time",
                    "score": round(score, 2),
                    "details": {
                        "hour": hour,
                        "hour_probability": round(hour_prob, 4),
                        "mean_probability": round(mean_prob, 4),
                        "z_score": round(z, 2),
                        "timestamp_ms": ts_ms,
                    },
                }
            )

    max_score = max((a["score"] for a in anomalies), default=0.0)
    return {"score": round(max_score, 2), "anomalies": anomalies}


def detect_location_anomalies(
    events: List[Dict],
    recent_events: Optional[List[Dict]] = None,
) -> Dict:
    """Detect events far from the user's geographic centroid.

    Returns dict with score (0-100) and anomalies list.
    """
    empty: Dict = {"score": 0.0, "anomalies": []}

    geo_events = [
        e for e in events if e.get("latitude") is not None and e.get("longitude") is not None
    ]
    if len(geo_events) < _MIN_EVENTS_LOCATION:
        return empty

    centroid_lat, centroid_lon = _geographic_centroid(geo_events)
    if centroid_lat is None:
        return empty

    spread = _geo_spread_km(geo_events, centroid_lat, centroid_lon)
    distances: List[float] = []
    for e in geo_events:
        distances.append(
            _haversine_km(float(e["latitude"]), float(e["longitude"]), centroid_lat, centroid_lon)
        )
    std_dist = _std_dev(distances)

    if recent_events is None:
        cutoff = max(1, len(events) * 4 // 5)
        recent_events = events[cutoff:]

    anomalies: List[Dict] = []
    for e in recent_events:
        lat = e.get("latitude")
        lon = e.get("longitude")
        if lat is None or lon is None:
            continue

        dist = _haversine_km(float(lat), float(lon), centroid_lat, centroid_lon)
        z = _zscore(dist, spread, std_dist)

        if dist > spread and z > _ZSCORE_THRESHOLD:
            score = min(z / 4.0 * 100, 100.0)
            anomalies.append(
                {
                    "type": "location",
                    "score": round(score, 2),
                    "details": {
                        "distance_km": round(dist, 2),
                        "centroid_lat": round(centroid_lat, 4),
                        "centroid_lon": round(centroid_lon, 4),
                        "geo_spread_km": round(spread, 2),
                        "z_score": round(z, 2),
                        "latitude": float(lat),
                        "longitude": float(lon),
                    },
                }
            )

    max_score = max((a["score"] for a in anomalies), default=0.0)
    return {"score": round(max_score, 2), "anomalies": anomalies}


def detect_frequency_anomalies(
    events: List[Dict],
    window_days: int = 7,
) -> Dict:
    """Detect sudden spikes or drops in daily reporting frequency.

    Returns dict with score (0-100) and anomalies list.
    """
    empty: Dict = {"score": 0.0, "anomalies": []}

    if len(events) < _MIN_EVENTS_FREQUENCY:
        return empty

    day_counts: Counter = Counter()
    for e in events:
        ts_ms = e.get("timestamp_ms")
        if ts_ms is None:
            continue
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        day_key = dt.strftime("%Y-%m-%d")
        day_counts[day_key] += 1

    if len(day_counts) < 3:
        return empty

    sorted_days = sorted(day_counts.keys())
    counts = [day_counts[d] for d in sorted_days]

    overall_mean = sum(counts) / len(counts)
    overall_std = _std_dev(counts)

    anomalies: List[Dict] = []
    for i, day in enumerate(sorted_days):
        count = counts[i]

        if i >= window_days:
            window = counts[i - window_days : i]
            w_mean = sum(window) / len(window)
            w_std = _std_dev(window)
        else:
            w_mean = overall_mean
            w_std = overall_std

        z = _zscore(count, w_mean, w_std)

        if z > _ZSCORE_THRESHOLD:
            direction = "spike" if count > w_mean else "drop"
            score = min(z / 4.0 * 100, 100.0)
            anomalies.append(
                {
                    "type": "frequency",
                    "score": round(score, 2),
                    "details": {
                        "date": day,
                        "event_count": count,
                        "baseline_mean": round(w_mean, 2),
                        "baseline_std": round(w_std, 2),
                        "z_score": round(z, 2),
                        "direction": direction,
                    },
                }
            )

    max_score = max((a["score"] for a in anomalies), default=0.0)
    return {"score": round(max_score, 2), "anomalies": anomalies}


def detect_anomalies(
    events: List[Dict],
    routines: Optional[Dict] = None,
) -> Dict:
    """Run all anomaly detectors and return a combined result.

    Returns dict with anomaly_score (0-100), anomalies list, and sub_scores dict.
    """
    if not events:
        return {
            "anomaly_score": 0.0,
            "anomalies": [],
            "sub_scores": {"time": 0.0, "location": 0.0, "frequency": 0.0},
        }

    sorted_events = sorted(events, key=lambda e: e.get("timestamp_ms", 0))

    time_result = detect_time_anomalies(sorted_events)
    location_result = detect_location_anomalies(sorted_events)
    frequency_result = detect_frequency_anomalies(sorted_events)

    all_anomalies = (
        time_result["anomalies"] + location_result["anomalies"] + frequency_result["anomalies"]
    )

    max_time = time_result["score"]
    max_location = location_result["score"]
    max_frequency = frequency_result["score"]

    composite = max_location * 0.4 + max_frequency * 0.35 + max_time * 0.25
    composite = round(min(composite, 100.0), 2)

    return {
        "anomaly_score": composite,
        "anomalies": all_anomalies,
        "sub_scores": {
            "time": round(max_time, 2),
            "location": round(max_location, 2),
            "frequency": round(max_frequency, 2),
        },
    }
