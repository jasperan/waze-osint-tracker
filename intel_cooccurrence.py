# intel_cooccurrence.py
"""Co-occurrence graph builder — finds user pairs that appear at the same
place and time, suggesting they may be travelling together or following
similar routines."""

from collections import defaultdict
from typing import Dict, List

from utils import haversine_m as _haversine_m


def find_cooccurrences(
    events: List[Dict],
    spatial_threshold_m: float = 500,
    temporal_threshold_s: float = 300,
    min_count: int = 3,
) -> List[Dict]:
    """Return a list of user-pair co-occurrence records.

    Each record is a dict with keys:
        user_a, user_b   — canonical ordering (min, max of usernames)
        co_count          — number of spatiotemporal co-occurrences
        avg_distance_m    — mean Haversine distance across co-occurrences
        avg_time_gap_s    — mean absolute time gap in seconds

    Parameters
    ----------
    events : list of dict
        Each dict must contain *username*, *latitude*, *longitude*,
        *timestamp_ms* (epoch milliseconds).  An optional *region* key is
        ignored by this function.
    spatial_threshold_m : float
        Maximum Haversine distance (metres) for two events to be considered
        co-located.  Default 500 m.
    temporal_threshold_s : float
        Maximum time gap (seconds) for two events to be considered
        contemporaneous.  Default 300 s (5 min).
    min_count : int
        Minimum number of co-occurrences for a pair to be included in the
        result.  Default 3.
    """
    # 1. Sort by timestamp_ms
    sorted_events = sorted(events, key=lambda e: e["timestamp_ms"])

    # Quick-reject threshold in degrees (approximate)
    degree_threshold = spatial_threshold_m / 111_000
    temporal_threshold_ms = temporal_threshold_s * 1000

    # Accumulator: (user_a, user_b) -> {"distances": [], "time_gaps": []}
    pair_data: Dict[tuple, Dict[str, list]] = defaultdict(
        lambda: {"distances": [], "time_gaps": []}
    )

    n = len(sorted_events)

    # 2. Sweep-line
    for i in range(n):
        ev_i = sorted_events[i]
        ts_i = ev_i["timestamp_ms"]
        user_i = ev_i["username"]
        lat_i = ev_i["latitude"]
        lon_i = ev_i["longitude"]

        for j in range(i + 1, n):
            ev_j = sorted_events[j]
            ts_j = ev_j["timestamp_ms"]

            # Temporal window exhausted — stop inner loop
            if ts_j - ts_i > temporal_threshold_ms:
                break

            # 3. Skip same-username pairs
            user_j = ev_j["username"]
            if user_i == user_j:
                continue

            # 4. Quick pre-filter on lat/lon difference
            lat_j = ev_j["latitude"]
            lon_j = ev_j["longitude"]
            if abs(lat_i - lat_j) > degree_threshold or abs(lon_i - lon_j) > degree_threshold:
                continue

            # 5. Full Haversine check
            dist = _haversine_m(lat_i, lon_i, lat_j, lon_j)
            if dist > spatial_threshold_m:
                continue

            # 6. Canonical pair ordering
            pair = (min(user_i, user_j), max(user_i, user_j))
            time_gap_s = abs(ts_j - ts_i) / 1000
            pair_data[pair]["distances"].append(dist)
            pair_data[pair]["time_gaps"].append(time_gap_s)

    # 7. Filter by min_count and build results
    results: List[Dict] = []
    for (user_a, user_b), data in pair_data.items():
        co_count = len(data["distances"])
        if co_count >= min_count:
            results.append(
                {
                    "user_a": user_a,
                    "user_b": user_b,
                    "co_count": co_count,
                    "avg_distance_m": sum(data["distances"]) / co_count,
                    "avg_time_gap_s": sum(data["time_gaps"]) / co_count,
                }
            )

    return results
