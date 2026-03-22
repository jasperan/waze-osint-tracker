"""Predictive presence module — predict where a user will be at a given day/hour."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
from sklearn.cluster import DBSCAN

from utils import haversine_m as _haversine_m

_EARTH_RADIUS_M = 6_371_000


def _to_radians_matrix(coords: np.ndarray) -> np.ndarray:
    """Convert an (N, 2) array of [lat, lon] degrees to radians."""
    return np.deg2rad(coords)


def _haversine_distance_matrix(coords_rad: np.ndarray) -> np.ndarray:
    """Pairwise haversine distance matrix from an (N, 2) radians array."""
    lat = coords_rad[:, 0]
    lon = coords_rad[:, 1]
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def predict_presence(
    events: List[Dict],
    target_dow: int,
    target_hour: int,
    hour_tolerance: int = 1,
) -> Optional[Dict]:
    """Predict a user's location for a given day-of-week and hour.

    Parameters
    ----------
    events : list[dict]
        Each dict must have keys: latitude, longitude, timestamp_ms, report_type.
    target_dow : int
        ISO day-of-week (0 = Monday, 6 = Sunday).
    target_hour : int
        Hour of day (0-23).
    hour_tolerance : int
        Allowed deviation in hours when matching events.

    Returns
    -------
    dict or None
        {latitude, longitude, confidence, radius_km, evidence_count} or None.
    """
    if len(events) < 3:
        return None

    # --- filter events matching target dow and hour (±tolerance) ---
    matching = []
    for ev in events:
        ts = datetime.fromtimestamp(ev["timestamp_ms"] / 1000, tz=timezone.utc)
        dow = ts.weekday()  # 0=Mon … 6=Sun
        hour = ts.hour
        if dow != target_dow:
            continue
        hour_diff = min(abs(hour - target_hour), 24 - abs(hour - target_hour))
        if hour_diff <= hour_tolerance:
            matching.append(ev)

    if len(matching) < 2:
        return None

    # --- DBSCAN clustering (eps in meters, haversine metric) ---
    coords = np.array([[e["latitude"], e["longitude"]] for e in matching])
    coords_rad = _to_radians_matrix(coords)
    dist_matrix = _haversine_distance_matrix(coords_rad)

    db = DBSCAN(eps=500, min_samples=2, metric="precomputed")
    labels = db.fit_predict(dist_matrix)

    # find the largest non-noise cluster
    unique_labels = set(labels)
    unique_labels.discard(-1)
    if not unique_labels:
        return None

    best_label = max(unique_labels, key=lambda lbl: np.sum(labels == lbl))
    cluster_mask = labels == best_label
    cluster_coords = coords[cluster_mask]
    cluster_size = int(cluster_mask.sum())

    # --- centroid ---
    centroid_lat = float(np.mean(cluster_coords[:, 0]))
    centroid_lon = float(np.mean(cluster_coords[:, 1]))

    # --- radius: 2 * std-dev of distances from centroid ---
    dists = np.array(
        [_haversine_m(centroid_lat, centroid_lon, lat, lon) for lat, lon in cluster_coords]
    )
    radius_m = 2 * float(np.std(dists)) if len(dists) > 1 else 500.0
    radius_km = radius_m / 1000

    # --- confidence ---
    # cluster_ratio: fraction of matching events in the best cluster
    cluster_ratio = cluster_size / len(matching)

    # hour histogram weight: how concentrated are events in target hour
    hour_counts: Dict[int, int] = {}
    for ev in events:
        ts = datetime.fromtimestamp(ev["timestamp_ms"] / 1000, tz=timezone.utc)
        hour_counts[ts.hour] = hour_counts.get(ts.hour, 0) + 1
    total_hour_events = sum(hour_counts.values())
    hour_weight = hour_counts.get(target_hour, 0) / total_hour_events if total_hour_events else 0

    # dow histogram weight: how concentrated are events on target day
    dow_counts: Dict[int, int] = {}
    for ev in events:
        ts = datetime.fromtimestamp(ev["timestamp_ms"] / 1000, tz=timezone.utc)
        dow_counts[ts.weekday()] = dow_counts.get(ts.weekday(), 0) + 1
    total_dow_events = sum(dow_counts.values())
    dow_weight = dow_counts.get(target_dow, 0) / total_dow_events if total_dow_events else 0

    # Scale up: geometric-ish combination, clamped to [0, 1]
    raw_confidence = cluster_ratio * (1 + hour_weight) * (1 + dow_weight)
    confidence = min(raw_confidence, 1.0)

    return {
        "latitude": centroid_lat,
        "longitude": centroid_lon,
        "confidence": round(confidence, 4),
        "radius_km": round(radius_km, 4),
        "evidence_count": cluster_size,
    }
