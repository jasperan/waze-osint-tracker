"""Privacy risk heatmap generator for Waze traffic event data.

Divides a geographic area into grid cells and scores each cell on how much
user privacy it leaks. High-risk cells have: many repeat visitors, predictable
patterns, and identifiable (non-anonymous) users.
"""

import math
from collections import Counter, defaultdict
from typing import Dict, List

_KM_PER_DEG_LAT = 111.0

_WEIGHT_REPEAT = 0.35
_WEIGHT_DENSITY = 0.25
_WEIGHT_UNIQUE = 0.20
_WEIGHT_REGULARITY = 0.20


def _km_per_deg_lon(lat: float) -> float:
    """Approximate km per degree of longitude at the given latitude."""
    return _KM_PER_DEG_LAT * math.cos(math.radians(lat))


def _grid_key(lat: float, lon: float, lat_step: float, lon_step: float) -> tuple:
    """Map a coordinate to its grid cell key (row, col indices)."""
    row = int(math.floor(lat / lat_step))
    col = int(math.floor(lon / lon_step))
    return (row, col)


def _cell_center(row: int, col: int, lat_step: float, lon_step: float) -> tuple:
    """Compute the center coordinates of a grid cell."""
    center_lat = (row + 0.5) * lat_step
    center_lon = (col + 0.5) * lon_step
    return (round(center_lat, 6), round(center_lon, 6))


def _sigmoid_scale(value: float, midpoint: float, steepness: float = 1.0) -> float:
    """Soft-clamp a value to [0, 1] using a sigmoid centered at midpoint."""
    x = steepness * (value - midpoint)
    x = max(min(x, 20.0), -20.0)
    return 1.0 / (1.0 + math.exp(-x))


def generate_privacy_heatmap(
    events: List[Dict],
    grid_size_km: float = 1.0,
) -> Dict:
    """Generate a grid-based privacy risk heatmap.

    Parameters
    ----------
    events : list[dict]
        Events with latitude, longitude, timestamp_ms, and optionally username.
    grid_size_km : float
        Approximate cell size in kilometers.

    Returns
    -------
    dict with grid_size_km, total_cells, cells, bounds, stats.
    """
    if not events:
        return {
            "grid_size_km": grid_size_km,
            "total_cells": 0,
            "cells": [],
            "bounds": {},
            "stats": {},
        }

    valid = []
    for e in events:
        lat = e.get("latitude")
        lon = e.get("longitude")
        if lat is not None and lon is not None:
            valid.append(e)

    if not valid:
        return {
            "grid_size_km": grid_size_km,
            "total_cells": 0,
            "cells": [],
            "bounds": {},
            "stats": {},
        }

    lats = [float(e["latitude"]) for e in valid]
    lons = [float(e["longitude"]) for e in valid]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    center_lat = (min_lat + max_lat) / 2.0

    lat_step = grid_size_km / _KM_PER_DEG_LAT
    km_per_lon = _km_per_deg_lon(center_lat)
    lon_step = grid_size_km / km_per_lon if km_per_lon > 0 else lat_step

    cell_data: Dict[tuple, List[tuple]] = defaultdict(list)

    for e in valid:
        lat = float(e["latitude"])
        lon = float(e["longitude"])
        username = e.get("username") or e.get("reporter_name") or "anonymous"
        ts_ms = e.get("timestamp_ms", 0)

        key = _grid_key(lat, lon, lat_step, lon_step)
        cell_data[key].append((username, ts_ms, e))

    cells = []
    all_risk_scores = []

    for (row, col), entries in cell_data.items():
        center_lat_cell, center_lon_cell = _cell_center(row, col, lat_step, lon_step)

        total_events = len(entries)
        usernames = [u for u, _, _ in entries]
        user_counts = Counter(usernames)
        unique_users = len(user_counts)

        repeat_users = sum(1 for c in user_counts.values() if c > 1)
        repeat_ratio = repeat_users / unique_users if unique_users > 0 else 0.0

        avg_events = total_events / unique_users if unique_users > 0 else 0.0

        user_days: Dict[str, set] = defaultdict(set)
        for username, ts_ms, _ in entries:
            if ts_ms:
                day = ts_ms // 86_400_000
                user_days[username].add(day)

        regular_users = sum(1 for days in user_days.values() if len(days) > 1)
        regular_ratio = regular_users / unique_users if unique_users > 0 else 0.0

        repeat_score = _sigmoid_scale(repeat_ratio, 0.3, steepness=5.0)
        density_score = _sigmoid_scale(avg_events, 3.0, steepness=1.0)
        unique_score = _sigmoid_scale(unique_users, 5, steepness=0.5)
        regularity_score = _sigmoid_scale(regular_ratio, 0.2, steepness=5.0)

        risk_score = (
            repeat_score * _WEIGHT_REPEAT
            + density_score * _WEIGHT_DENSITY
            + unique_score * _WEIGHT_UNIQUE
            + regularity_score * _WEIGHT_REGULARITY
        ) * 100.0

        risk_score = round(min(risk_score, 100.0), 2)
        all_risk_scores.append(risk_score)

        cells.append(
            {
                "lat": center_lat_cell,
                "lon": center_lon_cell,
                "risk_score": risk_score,
                "unique_users": unique_users,
                "repeat_ratio": round(repeat_ratio, 4),
                "avg_events_per_user": round(avg_events, 2),
                "total_events": total_events,
                "regular_user_ratio": round(regular_ratio, 4),
            }
        )

    cells.sort(key=lambda c: c["risk_score"], reverse=True)

    avg_risk = sum(all_risk_scores) / len(all_risk_scores) if all_risk_scores else 0.0
    max_risk = max(all_risk_scores) if all_risk_scores else 0.0
    high_risk_cells = sum(1 for s in all_risk_scores if s > 60)

    return {
        "grid_size_km": grid_size_km,
        "total_cells": len(cells),
        "cells": cells,
        "bounds": {
            "min_lat": round(min_lat, 6),
            "max_lat": round(max_lat, 6),
            "min_lon": round(min_lon, 6),
            "max_lon": round(max_lon, 6),
        },
        "stats": {
            "avg_risk_score": round(avg_risk, 2),
            "max_risk_score": round(max_risk, 2),
            "high_risk_cells": high_risk_cells,
            "total_events": len(valid),
            "total_unique_users": len(
                {e.get("username") or e.get("reporter_name") or "anonymous" for e in valid}
            ),
        },
    }
