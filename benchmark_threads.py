#!/usr/bin/env python3
"""Benchmark different thread counts for the Waze collector."""

import os
import sqlite3
import subprocess
import time
from datetime import datetime

# Configuration
THREAD_COUNTS = [4, 8, 16, 32]
BENCHMARK_DURATION = 90  # seconds per test
DATA_DIR = "./data"
WARMUP_TIME = 10  # seconds to let the collector stabilize

DB_PATHS = [
    "waze_europe.db",
    "waze_americas.db",
    "waze_asia.db",
    "waze_oceania.db",
    "waze_africa.db",
]


def get_total_events():
    """Get total event count across all databases."""
    total = 0
    for db_name in DB_PATHS:
        db_path = os.path.join(DATA_DIR, db_name)
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM events")
                total += cursor.fetchone()[0]
                conn.close()
            except Exception as e:
                print(f"  Error reading {db_name}: {e}")
    return total


def stop_collector():
    """Stop any running collector."""
    subprocess.run(["python", "cli.py", "stop"], capture_output=True)
    time.sleep(2)


def start_collector(threads):
    """Start collector with specified thread count."""
    cmd = ["python", "cli.py", "start", "-b", "--no-web", "-t", str(threads)]
    subprocess.run(cmd, capture_output=True)


def run_benchmark(threads):
    """Run benchmark for a specific thread count."""
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {threads} threads per region")
    print(f"{'='*60}")

    # Stop any existing collector
    stop_collector()

    # Record starting event count
    start_events = get_total_events()
    print(f"Starting events: {start_events:,}")

    # Start collector with specified threads
    print(f"Starting collector with {threads} threads per region...")
    start_collector(threads)

    # Warmup period
    print(f"Warming up for {WARMUP_TIME}s...")
    time.sleep(WARMUP_TIME)

    # Record events after warmup
    warmup_events = get_total_events()
    print(f"After warmup: {warmup_events:,} (+{warmup_events - start_events} during warmup)")

    # Main benchmark period
    print(f"Running benchmark for {BENCHMARK_DURATION}s...")
    benchmark_start = time.time()
    start_count = warmup_events

    # Progress updates every 15 seconds
    intervals = []
    last_count = start_count
    for i in range(BENCHMARK_DURATION // 15):
        time.sleep(15)
        current = get_total_events()
        interval_events = current - last_count
        intervals.append(interval_events)
        elapsed = (i + 1) * 15
        print(f"  [{elapsed:3}s] +{interval_events:4} events (total: {current:,})")
        last_count = current

    # Final count
    remaining = BENCHMARK_DURATION % 15
    if remaining > 0:
        time.sleep(remaining)

    end_count = get_total_events()
    elapsed = time.time() - benchmark_start

    # Stop collector
    stop_collector()

    # Calculate results
    events_collected = end_count - start_count
    events_per_minute = (events_collected / elapsed) * 60

    print(f"\nResults for {threads} threads:")
    print(f"  Events collected: {events_collected:,}")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Throughput: {events_per_minute:.1f} events/minute")

    return {
        "threads": threads,
        "events": events_collected,
        "duration": elapsed,
        "events_per_minute": events_per_minute,
        "intervals": intervals,
    }


def main():
    print("=" * 60)
    print("WAZE COLLECTOR THREAD BENCHMARK")
    print(f"Testing thread counts: {THREAD_COUNTS}")
    print(f"Benchmark duration: {BENCHMARK_DURATION}s per test")
    print(f"Machine: {os.popen('nproc').read().strip()} cores")
    print("=" * 60)

    results = []

    for threads in THREAD_COUNTS:
        result = run_benchmark(threads)
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'Threads':>10} | {'Events':>10} | {'Events/min':>12} | {'Relative':>10}")
    print("-" * 50)

    baseline = results[0]["events_per_minute"] if results else 1
    best = max(results, key=lambda x: x["events_per_minute"])

    for r in results:
        relative = r["events_per_minute"] / baseline * 100
        marker = " <-- BEST" if r["threads"] == best["threads"] else ""
        print(f"{r['threads']:>10} | {r['events']:>10,} | {r['events_per_minute']:>12.1f} | {relative:>9.1f}%{marker}")

    print("\n" + "=" * 60)
    print(f"OPTIMAL: {best['threads']} threads ({best['events_per_minute']:.1f} events/min)")
    print("=" * 60)

    # Save results to file
    with open("benchmark_results.txt", "w") as f:
        f.write("Waze Collector Thread Benchmark Results\n")
        f.write(f"Date: {datetime.now().isoformat()}\n")
        f.write(f"Duration per test: {BENCHMARK_DURATION}s\n\n")
        for r in results:
            f.write(f"{r['threads']} threads: {r['events_per_minute']:.1f} events/min\n")
        f.write(f"\nOptimal: {best['threads']} threads\n")

    print("\nResults saved to benchmark_results.txt")
    return best["threads"]


if __name__ == "__main__":
    optimal = main()
    print("\nTo use the optimal setting, run:")
    print(f"  python cli.py start -b -t {optimal}")
