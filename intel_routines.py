# intel_routines.py
"""Detect home, work, and commute patterns from user event locations.

Uses time-stratified DBSCAN clustering to infer routine locations:
- Night events (22:00-07:00) cluster -> HOME
- Work-hour events (09:00-17:00 weekdays) cluster -> WORK
- Events along the home-work corridor -> COMMUTE
"""

from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np
from sklearn.cluster import DBSCAN

from utils import haversine_km as _haversine_km


def _cluster_locations(
    coords: np.ndarray, eps_km: float = 0.5, min_samples: int = 3
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Run DBSCAN on coordinate pairs and return clusters sorted by size (largest first).

    Args:
        coords: Array of shape (N, 2) with [latitude, longitude] rows.
        eps_km: Maximum neighborhood radius in kilometers.
            Approximated as degrees (eps_km / 111.0).
        min_samples: Minimum points to form a cluster.

    Returns:
        List of (centroid, member_coords) tuples, largest cluster first.
        centroid is shape (2,), member_coords is shape (M, 2).
    """
    if len(coords) < min_samples:
        return []

    # Convert km to approximate degrees (1 degree latitude ~ 111 km)
    eps_deg = eps_km / 111.0

    db = DBSCAN(eps=eps_deg, min_samples=min_samples, metric="euclidean")
    labels = db.fit_predict(coords)

    clusters = []
    unique_labels = set(labels)
    unique_labels.discard(-1)  # Remove noise label

    for label in unique_labels:
        mask = labels == label
        members = coords[mask]
        centroid = members.mean(axis=0)
        clusters.append((centroid, members))

    # Sort by cluster size, largest first
    clusters.sort(key=lambda x: len(x[1]), reverse=True)
    return clusters


def infer_routines(events: List[Dict]) -> Dict[str, Dict]:
    """Infer home, work, and commute routines from a list of user events.

    Args:
        events: List of event dicts, each containing at least:
            - latitude (float)
            - longitude (float)
            - timestamp_utc (str, ISO format) or timestamp_ms (int)

    Returns:
        Dict mapping routine type ('HOME', 'WORK', 'COMMUTE') to:
            - latitude (float): centroid latitude
            - longitude (float): centroid longitude
            - confidence (float): cluster_events / total_events_in_time_slice
            - typical_hours (list): hours when events occur
            - typical_days (list): day-of-week indices (0=Monday)
            - evidence_count (int): number of events in cluster
    """
    if len(events) < 10:
        return {}

    # Parse timestamps and extract coordinates with time metadata
    parsed = []
    for event in events:
        lat = event.get("latitude")
        lon = event.get("longitude")
        if lat is None or lon is None:
            continue

        # Parse timestamp
        ts_utc = event.get("timestamp_utc")
        ts_ms = event.get("timestamp_ms")
        if ts_utc:
            try:
                dt = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
        elif ts_ms:
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        else:
            continue

        parsed.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "hour": dt.hour,
                "dow": dt.weekday(),  # 0=Monday
            }
        )

    if len(parsed) < 10:
        return {}

    # Split by time slices
    night_events = [p for p in parsed if p["hour"] >= 22 or p["hour"] < 7]
    work_events = [p for p in parsed if 9 <= p["hour"] < 17 and p["dow"] < 5]

    routines: Dict[str, Dict] = {}

    # Identify HOME from night cluster
    if len(night_events) >= 3:
        night_coords = np.array([[e["lat"], e["lon"]] for e in night_events])
        night_clusters = _cluster_locations(night_coords, eps_km=0.5, min_samples=3)

        if night_clusters:
            centroid, members = night_clusters[0]  # Largest cluster
            hours = [
                night_events[i]["hour"]
                for i in range(len(night_events))
                if any(np.array_equal(night_coords[i], m) for m in members)
            ]
            days = [
                night_events[i]["dow"]
                for i in range(len(night_events))
                if any(np.array_equal(night_coords[i], m) for m in members)
            ]

            routines["HOME"] = {
                "latitude": float(centroid[0]),
                "longitude": float(centroid[1]),
                "confidence": len(members) / len(night_events),
                "typical_hours": sorted(set(hours)),
                "typical_days": sorted(set(days)),
                "evidence_count": len(members),
            }

    # Identify WORK from work-hour cluster
    if len(work_events) >= 3:
        work_coords = np.array([[e["lat"], e["lon"]] for e in work_events])
        work_clusters = _cluster_locations(work_coords, eps_km=0.5, min_samples=3)

        if work_clusters:
            centroid, members = work_clusters[0]  # Largest cluster
            hours = [
                work_events[i]["hour"]
                for i in range(len(work_events))
                if any(np.array_equal(work_coords[i], m) for m in members)
            ]
            days = [
                work_events[i]["dow"]
                for i in range(len(work_events))
                if any(np.array_equal(work_coords[i], m) for m in members)
            ]

            routines["WORK"] = {
                "latitude": float(centroid[0]),
                "longitude": float(centroid[1]),
                "confidence": len(members) / len(work_events),
                "typical_hours": sorted(set(hours)),
                "typical_days": sorted(set(days)),
                "evidence_count": len(members),
            }

    # Identify COMMUTE corridor if home and work are >2km apart
    if "HOME" in routines and "WORK" in routines:
        home = routines["HOME"]
        work = routines["WORK"]
        dist_km = _haversine_km(
            home["latitude"], home["longitude"], work["latitude"], work["longitude"]
        )

        if dist_km > 2.0:
            # Find events along the corridor (within 1km of the home-work line)
            home_lat, home_lon = home["latitude"], home["longitude"]
            work_lat, work_lon = work["latitude"], work["longitude"]

            commute_events = []
            commute_hours = []
            commute_days = []

            for p in parsed:
                # Skip events that are already at home or work
                d_home = _haversine_km(p["lat"], p["lon"], home_lat, home_lon)
                d_work = _haversine_km(p["lat"], p["lon"], work_lat, work_lon)

                if d_home < 0.5 or d_work < 0.5:
                    continue

                # Check if event is along the corridor:
                # distance to home + distance to work should be close to home-work distance
                total_d = d_home + d_work
                if total_d <= dist_km * 1.3:  # Within 30% of direct path
                    commute_events.append(p)
                    commute_hours.append(p["hour"])
                    commute_days.append(p["dow"])

            if commute_events:
                commute_coords = np.array([[e["lat"], e["lon"]] for e in commute_events])
                mid_lat = float(commute_coords[:, 0].mean())
                mid_lon = float(commute_coords[:, 1].mean())

                routines["COMMUTE"] = {
                    "latitude": mid_lat,
                    "longitude": mid_lon,
                    "confidence": len(commute_events) / len(parsed),
                    "typical_hours": sorted(set(commute_hours)),
                    "typical_days": sorted(set(commute_days)),
                    "evidence_count": len(commute_events),
                }

    return routines
