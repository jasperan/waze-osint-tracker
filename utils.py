# utils.py
"""Shared utilities — single source of truth for functions used across modules.

Contains: haversine distance, event hashing, config loading.
"""

import hashlib
import math
import os

import yaml

_EARTH_RADIUS_KM = 6371.0
_EARTH_RADIUS_M = 6_371_000

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS-84 points in kilometers."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS-84 points in meters."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def generate_event_hash(
    username: str,
    latitude: float,
    longitude: float,
    timestamp_ms: int,
    report_type: str,
) -> str:
    """Generate unique hash for event deduplication.

    Rounds coordinates to 4 decimals (~11 m) and timestamps to the minute.
    Returns a 16-character hex digest.
    """
    timestamp_minute = timestamp_ms // 60000
    lat_rounded = round(latitude, 4)
    lon_rounded = round(longitude, 4)
    data = f"{username}|{lat_rounded}|{lon_rounded}|{timestamp_minute}|{report_type}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def load_config():
    """Load config, preferring config_oracle.yaml over config.yaml.

    Searches the project root directory for config files.
    """
    for config_file in ("config_oracle.yaml", "config.yaml"):
        full_path = os.path.join(_PROJECT_ROOT, config_file)
        if os.path.exists(full_path):
            with open(full_path) as f:
                return yaml.safe_load(f)
    with open(os.path.join(_PROJECT_ROOT, "config.yaml")) as f:
        return yaml.safe_load(f)
