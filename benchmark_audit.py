#!/usr/bin/env python3
"""Performance benchmark for the 3 critical-path optimizations.

Self-contained script using synthetic data.  Runs each benchmark with the OLD
(pre-optimization) algorithm and the NEW (post-optimization) algorithm, then
prints a summary table with before/after timings.

Usage:
    python benchmark_audit.py
"""

import os
import random
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np
from sklearn.cluster import DBSCAN

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from intel_cooccurrence import find_cooccurrences as _new_find_cooccurrences
from intel_routines import infer_routines as _new_infer_routines
from utils import haversine_m as _haversine_m

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RESULTS: Dict[str, Dict[str, float]] = {}


# ===================================================================
# 1. Co-occurrence detection
# ===================================================================


def _generate_cooccurrence_events(n: int = 10_000, seed: int = 42) -> List[Dict]:
    """Generate synthetic events spread across a city-sized area with some
    co-located clusters to create realistic co-occurrence patterns."""
    rng = random.Random(seed)
    users = [f"user_{i}" for i in range(200)]
    base_ts = 1_700_000_000_000
    events = []
    for _ in range(n):
        events.append(
            {
                "username": rng.choice(users),
                "latitude": 40.40 + rng.gauss(0, 0.02),
                "longitude": -3.70 + rng.gauss(0, 0.02),
                "timestamp_ms": base_ts + rng.randint(0, 600_000),  # 10-min window
            }
        )
    return events


# --- OLD implementation (O(N^2) sweep-line, no spatial index) ---


def _old_find_cooccurrences(events, spatial_threshold_m=500, temporal_threshold_s=300, min_count=3):
    sorted_events = sorted(events, key=lambda e: e["timestamp_ms"])
    degree_threshold = spatial_threshold_m / 111_000
    temporal_threshold_ms = temporal_threshold_s * 1000
    pair_data = defaultdict(lambda: {"distances": [], "time_gaps": []})
    n = len(sorted_events)

    for i in range(n):
        ev_i = sorted_events[i]
        ts_i = ev_i["timestamp_ms"]
        user_i = ev_i["username"]
        lat_i = ev_i["latitude"]
        lon_i = ev_i["longitude"]

        for j in range(i + 1, n):
            ev_j = sorted_events[j]
            ts_j = ev_j["timestamp_ms"]
            if ts_j - ts_i > temporal_threshold_ms:
                break
            user_j = ev_j["username"]
            if user_i == user_j:
                continue
            lat_j = ev_j["latitude"]
            lon_j = ev_j["longitude"]
            if abs(lat_i - lat_j) > degree_threshold or abs(lon_i - lon_j) > degree_threshold:
                continue
            dist = _haversine_m(lat_i, lon_i, lat_j, lon_j)
            if dist > spatial_threshold_m:
                continue
            pair = (min(user_i, user_j), max(user_i, user_j))
            time_gap_s = abs(ts_j - ts_i) / 1000
            pair_data[pair]["distances"].append(dist)
            pair_data[pair]["time_gaps"].append(time_gap_s)

    results = []
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


# --- NEW implementation (imported from optimized module at top of file) ---

# ===================================================================
# 2. Web API aggregation — SQLite connection pool benchmark
# ===================================================================


def _create_test_dbs(tmpdir: str, n_regions: int = 6, rows_per_db: int = 500):
    """Create temporary SQLite databases mimicking regional Waze DBs."""
    from database import Database

    regions = ["madrid", "europe", "americas", "asia", "oceania", "africa"][:n_regions]
    paths = {}
    rng = random.Random(99)
    for region in regions:
        path = os.path.join(tmpdir, f"waze_{region}.db")
        db = Database(path)
        for i in range(rows_per_db):
            db.conn.execute(
                "INSERT OR IGNORE INTO events "
                "(event_hash, username, latitude, longitude, timestamp_utc, "
                "timestamp_ms, report_type, subtype, raw_json, collected_at, grid_cell) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"hash_{region}_{i}",
                    f"user_{rng.randint(0, 50)}",
                    40.0 + rng.random(),
                    -3.0 + rng.random(),
                    "2025-01-01T00:00:00Z",
                    1700000000000 + i * 1000,
                    rng.choice(["POLICE", "JAM", "HAZARD", "ACCIDENT"]),
                    "",
                    "{}",
                    "2025-01-01T00:00:00Z",
                    "cell_0",
                ),
            )
        db.commit()
        db.close()
        paths[region] = path
    return paths


def _old_get_all_dbs_and_query(db_paths: Dict[str, str]):
    """OLD pattern: open + close every call."""
    from database import Database

    total = 0
    for region, path in db_paths.items():
        db = Database(path)
        row = db.execute("SELECT COUNT(*) as count FROM events").fetchone()
        total += row["count"]
        db.close()
    return total


def _new_get_all_dbs_and_query(db_paths: Dict[str, str], pool: dict):
    """NEW pattern: reuse pooled connections."""
    from database import Database

    total = 0
    for region, path in db_paths.items():
        if path not in pool:
            pool[path] = Database(path, check_same_thread=False)
        db = pool[path]
        row = db.execute("SELECT COUNT(*) as count FROM events").fetchone()
        total += row["count"]
    return total


# ===================================================================
# 3. Routine inference — cluster membership lookup
# ===================================================================


def _generate_routine_events(n_night: int = 500, n_work: int = 500, seed: int = 42):
    """Generate synthetic events with clear home/work clusters."""
    rng = random.Random(seed)
    events = []
    # Night events clustered around home (40.42, -3.70)
    for _ in range(n_night):
        hour = rng.choice([22, 23, 0, 1, 2, 3, 4, 5, 6])
        dow = rng.randint(0, 6)
        day = 5 + dow
        events.append(
            {
                "latitude": 40.42 + rng.gauss(0, 0.001),
                "longitude": -3.70 + rng.gauss(0, 0.001),
                "timestamp_utc": f"2026-01-{day:02d}T{hour:02d}:00:00Z",
                "timestamp_ms": None,
                "report_type": "POLICE",
            }
        )
    # Work events clustered around office (40.45, -3.68)
    for _ in range(n_work):
        hour = rng.choice([9, 10, 11, 12, 13, 14, 15, 16])
        dow = rng.randint(0, 4)  # weekdays
        day = 5 + dow
        events.append(
            {
                "latitude": 40.45 + rng.gauss(0, 0.001),
                "longitude": -3.68 + rng.gauss(0, 0.001),
                "timestamp_utc": f"2026-01-{day:02d}T{hour:02d}:00:00Z",
                "timestamp_ms": None,
                "report_type": "JAM",
            }
        )
    # Some noise events
    for _ in range(100):
        hour = rng.randint(0, 23)
        dow = rng.randint(0, 6)
        day = 5 + dow
        events.append(
            {
                "latitude": 40.0 + rng.random() * 0.5,
                "longitude": -3.0 - rng.random() * 0.5,
                "timestamp_utc": f"2026-01-{day:02d}T{hour:02d}:00:00Z",
                "timestamp_ms": None,
                "report_type": "HAZARD",
            }
        )
    return events


# --- OLD routine inference (O(N*M) array comparison) ---


def _old_cluster_locations(coords, eps_km=0.5, min_samples=3):
    if len(coords) < min_samples:
        return []
    eps_deg = eps_km / 111.0
    db = DBSCAN(eps=eps_deg, min_samples=min_samples, metric="euclidean")
    labels = db.fit_predict(coords)
    clusters = []
    unique_labels = set(labels)
    unique_labels.discard(-1)
    for label in unique_labels:
        mask = labels == label
        members = coords[mask]
        centroid = members.mean(axis=0)
        clusters.append((centroid, members))
    clusters.sort(key=lambda x: len(x[1]), reverse=True)
    return clusters


def _old_infer_routines(events):
    if len(events) < 10:
        return {}
    parsed = []
    for event in events:
        lat = event.get("latitude")
        lon = event.get("longitude")
        if lat is None or lon is None:
            continue
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
        parsed.append({"lat": float(lat), "lon": float(lon), "hour": dt.hour, "dow": dt.weekday()})

    if len(parsed) < 10:
        return {}
    night_events = [p for p in parsed if p["hour"] >= 22 or p["hour"] < 7]
    work_events = [p for p in parsed if 9 <= p["hour"] < 17 and p["dow"] < 5]
    routines = {}

    if len(night_events) >= 3:
        night_coords = np.array([[e["lat"], e["lon"]] for e in night_events])
        night_clusters = _old_cluster_locations(night_coords, eps_km=0.5, min_samples=3)
        if night_clusters:
            centroid, members = night_clusters[0]
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

    if len(work_events) >= 3:
        work_coords = np.array([[e["lat"], e["lon"]] for e in work_events])
        work_clusters = _old_cluster_locations(work_coords, eps_km=0.5, min_samples=3)
        if work_clusters:
            centroid, members = work_clusters[0]
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
    return routines


# --- NEW routine inference (imported from optimized module at top of file) ---

# ===================================================================
# Run benchmarks
# ===================================================================


def run_cooccurrence_benchmark():
    print("=" * 60)
    print("BENCHMARK 1: Co-occurrence detection (10,000 events)")
    print("=" * 60)

    events = _generate_cooccurrence_events(10_000)
    print(f"  Generated {len(events)} synthetic events")

    # OLD
    t0 = time.perf_counter()
    old_result = _old_find_cooccurrences(events, min_count=1)
    old_time = time.perf_counter() - t0
    RESULTS["cooccurrence"] = {"before": old_time}
    print(f"  OLD (O(N^2) sweep-line): {old_time:.3f}s  ({len(old_result)} pairs)")

    # NEW
    t0 = time.perf_counter()
    new_result = _new_find_cooccurrences(events, min_count=1)
    new_time = time.perf_counter() - t0
    RESULTS["cooccurrence"]["after"] = new_time
    print(f"  NEW (spatial grid index): {new_time:.3f}s  ({len(new_result)} pairs)")

    speedup = old_time / new_time if new_time > 0 else float("inf")
    print(f"  Speedup: {speedup:.1f}x\n")


def run_db_pool_benchmark():
    print("=" * 60)
    print("BENCHMARK 2: Web API DB aggregation (6 regions, 100 calls)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_paths = _create_test_dbs(tmpdir)
        n_calls = 100

        # OLD: open/close every call
        t0 = time.perf_counter()
        for _ in range(n_calls):
            _old_get_all_dbs_and_query(db_paths)
        old_time = time.perf_counter() - t0
        RESULTS["db_pool"] = {"before": old_time}
        print(f"  OLD (open/close per call): {old_time:.3f}s  ({n_calls} iterations)")

        # NEW: pooled connections
        pool = {}
        t0 = time.perf_counter()
        for _ in range(n_calls):
            _new_get_all_dbs_and_query(db_paths, pool)
        new_time = time.perf_counter() - t0
        RESULTS["db_pool"]["after"] = new_time
        print(f"  NEW (connection pool):     {new_time:.3f}s  ({n_calls} iterations)")

        # Clean up pool
        for db in pool.values():
            db.close()

        speedup = old_time / new_time if new_time > 0 else float("inf")
        print(f"  Speedup: {speedup:.1f}x\n")


def run_routines_benchmark():
    print("=" * 60)
    print("BENCHMARK 3: Routine inference (1100 events, DBSCAN membership)")
    print("=" * 60)

    events = _generate_routine_events(n_night=500, n_work=500)
    print(f"  Generated {len(events)} synthetic events")

    # OLD
    t0 = time.perf_counter()
    old_result = _old_infer_routines(events)
    old_time = time.perf_counter() - t0
    RESULTS["routines"] = {"before": old_time}
    old_keys = sorted(old_result.keys())
    print(f"  OLD (O(N*M) array_equal): {old_time:.3f}s  (routines: {old_keys})")

    # NEW
    t0 = time.perf_counter()
    new_result = _new_infer_routines(events)
    new_time = time.perf_counter() - t0
    RESULTS["routines"]["after"] = new_time
    new_keys = sorted(new_result.keys())
    print(f"  NEW (DBSCAN labels):      {new_time:.3f}s  (routines: {new_keys})")

    speedup = old_time / new_time if new_time > 0 else float("inf")
    print(f"  Speedup: {speedup:.1f}x\n")

    # Validate results match
    for key in old_keys:
        if key in new_result:
            old_lat = old_result[key]["latitude"]
            new_lat = new_result[key]["latitude"]
            assert abs(old_lat - new_lat) < 0.01, f"{key} latitude mismatch: {old_lat} vs {new_lat}"


def print_summary():
    print("=" * 60)
    print("SUMMARY TABLE")
    print("=" * 60)
    print(f"{'Bottleneck':<35} {'Before':>8} {'After':>8} {'Speedup':>8}")
    print("-" * 60)

    labels = {
        "cooccurrence": "Co-occurrence (spatial grid)",
        "db_pool": "DB aggregation (conn pool)",
        "routines": "Routine inference (labels)",
    }
    for key, label in labels.items():
        if key in RESULTS:
            before = RESULTS[key]["before"]
            after = RESULTS[key]["after"]
            speedup = before / after if after > 0 else float("inf")
            print(f"  {label:<33} {before:>7.3f}s {after:>7.3f}s {speedup:>7.1f}x")

    print("-" * 60)


if __name__ == "__main__":
    run_cooccurrence_benchmark()
    run_db_pool_benchmark()
    run_routines_benchmark()
    print_summary()
