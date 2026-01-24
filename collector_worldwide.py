#!/usr/bin/env python3
# collector_worldwide.py
"""Worldwide autonomous Waze data collector - all continents."""

import hashlib
import json
import time
import os
import signal
import yaml
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

# Status file for real-time UI updates
STATUS_FILE = "./data/collector_status.json"
CHECKPOINT_FILE = "./data/collector_checkpoint.json"
status_lock = threading.Lock()
checkpoint_lock = threading.Lock()


def write_status(region: str, cell_name: str, country: str, cell_idx: int, total_cells: int,
                 alerts_count: int, new_count: int, event_types: List[str] = None):
    """Write current collector status to file for UI consumption (thread-safe)."""
    try:
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "region": region,
            "cell_name": cell_name,
            "country": country,
            "cell_idx": cell_idx,
            "total_cells": total_cells,
            "alerts_found": alerts_count,
            "new_events": new_count,
            "event_types": event_types or [],
            "status": "scanning"
        }
        with status_lock:
            with open(STATUS_FILE, "w") as f:
                json.dump(status, f)
    except Exception:
        pass  # Don't crash on status write failures


def load_checkpoint() -> Dict[str, Any]:
    """Load checkpoint from file. Returns empty dict if no checkpoint exists."""
    try:
        if os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"cycle": 0, "scanned": {}}


def save_checkpoint(cycle: int, scanned: Dict[str, List[str]]):
    """Save checkpoint to file (thread-safe)."""
    try:
        checkpoint = {
            "cycle": cycle,
            "scanned": scanned,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with checkpoint_lock:
            with open(CHECKPOINT_FILE, "w") as f:
                json.dump(checkpoint, f)
    except Exception:
        pass


def clear_checkpoint():
    """Clear checkpoint file when cycle completes."""
    try:
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
    except Exception:
        pass


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/worldwide_collector.log')
    ]
)
logger = logging.getLogger("worldwide")


def generate_event_hash(username: str, latitude: float, longitude: float,
                        timestamp_ms: int, report_type: str) -> str:
    timestamp_minute = timestamp_ms // 60000
    data = f"{username}|{round(latitude, 4)}|{round(longitude, 4)}|{timestamp_minute}|{report_type}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def process_alert(alert: Dict[str, Any], grid_cell: str) -> Dict[str, Any]:
    username = alert.get("reportBy", "anonymous")
    latitude = alert.get("latitude", 0.0)
    longitude = alert.get("longitude", 0.0)
    timestamp_ms = alert.get("pubMillis", int(time.time() * 1000))
    report_type = alert.get("type", "UNKNOWN")
    subtype = alert.get("subtype")

    timestamp_utc = datetime.fromtimestamp(
        timestamp_ms / 1000, tz=timezone.utc
    ).isoformat()

    return {
        "event_hash": generate_event_hash(username, latitude, longitude, timestamp_ms, report_type),
        "username": username,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp_utc": timestamp_utc,
        "timestamp_ms": timestamp_ms,
        "report_type": report_type,
        "subtype": subtype,
        "raw_json": json.dumps(alert),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "grid_cell": grid_cell
    }


class RegionScanner:
    """Scanner for a specific region."""

    def __init__(self, name: str, config_path: str, db, client):
        self.name = name
        self.config_path = config_path
        self.db = db
        self.client = client
        self.logger = logging.getLogger(name)
        self.cells_by_priority = {}
        self._load_cells()

    def _load_cells(self):
        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        for cell in config.get("grid_cells", []):
            p = cell.get("priority", 2)
            if p not in self.cells_by_priority:
                self.cells_by_priority[p] = []
            self.cells_by_priority[p].append(cell)

    def get_cell_counts(self) -> Dict[int, int]:
        return {p: len(cells) for p, cells in self.cells_by_priority.items()}

    def scan(self, priority: int, running_flag, already_scanned: set = None,
             on_cell_scanned: callable = None) -> Dict[str, Any]:
        """Scan cells of given priority, skipping already-scanned cells.

        Args:
            priority: Priority level to scan (1 or 3)
            running_flag: Callable that returns False to stop scanning
            already_scanned: Set of cell names to skip
            on_cell_scanned: Callback called with cell_name after each cell is scanned
        """
        cells = self.cells_by_priority.get(priority, [])
        stats = {"requests": 0, "errors": 0, "events": 0, "cells": len(cells), "scanned_cells": []}
        total_cells = len(cells)
        already_scanned = already_scanned or set()

        # Filter out already-scanned cells
        remaining_cells = [(idx, cell) for idx, cell in enumerate(cells, 1)
                          if cell["name"] not in already_scanned]

        if len(remaining_cells) < len(cells):
            skipped = len(cells) - len(remaining_cells)
            self.logger.info(f"Resuming: skipping {skipped} already-scanned cells, {len(remaining_cells)} remaining")

        for idx, cell in remaining_cells:
            if not running_flag():
                break

            try:
                stats["requests"] += 1
                cell_name = cell["name"]
                country = cell.get("country", "??")

                alerts, _ = self.client.get_traffic_notifications(
                    lat_top=cell["lat_top"],
                    lat_bottom=cell["lat_bottom"],
                    lon_left=cell["lon_left"],
                    lon_right=cell["lon_right"]
                )

                new_count = 0
                new_types = []
                for alert in alerts:
                    event = process_alert(alert, cell_name)
                    if self.db.insert_event(event):
                        new_count += 1
                        new_types.append(event["report_type"])
                        self.db.upsert_tracked_user(event["username"], event["timestamp_utc"])

                stats["events"] += new_count
                stats["scanned_cells"].append(cell_name)

                # Notify callback that cell was scanned (for checkpoint saving)
                if on_cell_scanned:
                    on_cell_scanned(cell_name)

                # Only log and write status when there are alerts or new events
                if len(alerts) > 0 or new_count > 0:
                    type_summary = ""
                    if new_types:
                        from collections import Counter
                        counts = Counter(new_types)
                        type_summary = " | " + ", ".join(f"{t}:{c}" for t, c in counts.most_common(3))

                    status = f"+{new_count}" if new_count > 0 else "0"
                    self.logger.info(f"[{idx:3}/{total_cells}] {cell_name:25} ({country}) -> {len(alerts):3} alerts, {status} new{type_summary}")

                    # Write status for real-time UI updates
                    write_status(
                        region=self.name,
                        cell_name=cell_name,
                        country=country,
                        cell_idx=idx,
                        total_cells=total_cells,
                        alerts_count=len(alerts),
                        new_count=new_count,
                        event_types=new_types
                    )

            except Exception as e:
                stats["errors"] += 1
                stats["scanned_cells"].append(cell["name"])  # Mark as scanned even on error
                self.logger.error(f"[{idx:3}/{total_cells}] {cell['name']:25} -> ERROR: {e}")

        return stats


class WorldwideCollector:
    """Autonomous worldwide Waze data collector."""

    REGIONS = [
        ("europe", "config_europe.yaml", "./data/waze_europe.db"),
        ("americas", "config_americas.yaml", "./data/waze_americas.db"),
        ("asia", "config_asia.yaml", "./data/waze_asia.db"),
        ("oceania", "config_oceania.yaml", "./data/waze_oceania.db"),
        ("africa", "config_africa.yaml", "./data/waze_africa.db"),
    ]

    def __init__(self):
        self.running = False
        self.pid_file = "collector_worldwide.pid"
        self.scanners = {}
        self.databases = {}
        self.clients = {}

    def _generate_all_configs(self):
        """Generate all regional configs."""
        configs = [
            ("europe_grid", "save_europe_config"),
            ("americas_grid", "save_americas_config"),
            ("asia_grid", "save_asia_config"),
            ("oceania_grid", "save_oceania_config"),
            ("africa_grid", "save_africa_config"),
        ]

        for module_name, func_name in configs:
            config_file = f"config_{module_name.replace('_grid', '')}.yaml"
            if not os.path.exists(config_file):
                logger.info(f"Generating {config_file}...")
                module = __import__(module_name)
                getattr(module, func_name)()

    def _save_pid(self):
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self):
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)

    @staticmethod
    def get_pid() -> Optional[int]:
        if os.path.exists("collector_worldwide.pid"):
            with open("collector_worldwide.pid") as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                return pid
            except OSError:
                return None
        return None

    def run(self):
        """Main worldwide collection loop."""
        from database import Database
        from waze_client import WazeClient

        # Create directories
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Generate configs
        self._generate_all_configs()

        # Initialize scanners for each region
        logger.info("=" * 70)
        logger.info("WORLDWIDE WAZE COLLECTOR")
        logger.info("Covering: Europe, Americas, Asia, Oceania, Africa")
        logger.info("=" * 70)

        total_p1 = 0
        total_p3 = 0

        for region_name, config_path, db_path in self.REGIONS:
            if not os.path.exists(config_path):
                logger.warning(f"Config not found: {config_path}, skipping {region_name}")
                continue

            db = Database(db_path, check_same_thread=False)  # Thread-safe for parallel scanning
            client = WazeClient()

            scanner = RegionScanner(region_name, config_path, db, client)
            self.scanners[region_name] = scanner
            self.databases[region_name] = db
            self.clients[region_name] = client

            counts = scanner.get_cell_counts()
            p1 = counts.get(1, 0)
            p3 = counts.get(3, 0)
            total_p1 += p1
            total_p3 += p3

            logger.info(f"  {region_name.upper():10} - P1 (cities): {p1:4}, P3 (coverage): {p3:4}")

        logger.info("-" * 70)
        logger.info(f"  {'TOTAL':10} - P1 (cities): {total_p1:4}, P3 (coverage): {total_p3:4}")
        logger.info(f"  {'':10}   Grand total: {total_p1 + total_p3} grid cells")
        logger.info("=" * 70)
        logger.info("Collection strategy (MULTITHREADED):")
        logger.info("  - All regions scanned in PARALLEL for P1 (city) scans")
        logger.info("  - Full P3 (coverage) scan every 10 cycles (parallel)")
        logger.info("  - 10 second pause between cycles")
        logger.info("=" * 70)

        self.running = True
        self._save_pid()

        def handle_signal(signum, frame):
            logger.info("Shutdown signal received...")
            self.running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        region_names = list(self.scanners.keys())

        # Load checkpoint to resume from where we left off
        checkpoint = load_checkpoint()
        cycle = checkpoint.get("cycle", 0)
        scanned_cells = checkpoint.get("scanned", {})

        if cycle > 0:
            logger.info(f"Resuming from checkpoint: cycle {cycle}")
            for key, cells in scanned_cells.items():
                logger.info(f"  {key}: {len(cells)} cells already scanned")

        def scan_region(region_name: str, priority: int, today: str, already_scanned: set,
                        checkpoint_key: str) -> Dict[str, Any]:
            """Scan a single region (runs in thread)."""
            scanner = self.scanners[region_name]
            db = self.databases[region_name]

            p_count = scanner.get_cell_counts().get(priority, 0)
            if p_count == 0:
                return {"region": region_name, "events": 0, "errors": 0, "requests": 0, "cells": 0, "scanned_cells": []}

            def on_cell_scanned(cell_name):
                """Callback to save checkpoint after each cell (thread-safe)."""
                with checkpoint_lock:
                    if checkpoint_key not in scanned_cells:
                        scanned_cells[checkpoint_key] = []
                    scanned_cells[checkpoint_key].append(cell_name)
                save_checkpoint(cycle, scanned_cells)

            stats = scanner.scan(priority, lambda: self.running, already_scanned, on_cell_scanned)

            # Update daily stats (thread-safe - SQLite handles this)
            db.update_daily_stats(
                date=today,
                events=stats["events"],
                requests=stats["requests"],
                errors=stats["errors"],
                cells=stats["cells"]
            )

            return {"region": region_name, **stats}

        try:
            while self.running:
                cycle += 1
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                logger.info(f"\n{'='*50}")
                logger.info(f"CYCLE {cycle} (PARALLEL MODE)")
                logger.info(f"{'='*50}")

                # Parallel P1 scan - all regions at once
                logger.info(f"Starting parallel P1 scan across {len(region_names)} regions...")
                total_events = 0
                total_errors = 0
                cycle_complete = True

                with ThreadPoolExecutor(max_workers=len(region_names)) as executor:
                    futures = {}
                    for region in region_names:
                        key = f"{region}_p1"
                        already_scanned = set(scanned_cells.get(key, []))
                        futures[executor.submit(scan_region, region, 1, today, already_scanned, key)] = (region, key)

                    for future in as_completed(futures):
                        region, key = futures[future]
                        try:
                            result = future.result()
                            total_events += result["events"]
                            total_errors += result["errors"]

                            # Checkpoint is saved per-cell by callback, no need to save here

                            if result["events"] > 0 or result["errors"] > 0:
                                logger.info(f"  [{region.upper()}] +{result['events']} events, {result['errors']} errors")
                        except Exception as e:
                            logger.error(f"  [{region.upper()}] Thread error: {e}")
                            cycle_complete = False

                logger.info(f"P1 cycle complete: +{total_events} total events, {total_errors} errors")

                # Clear P1 checkpoint data after successful cycle
                if cycle_complete:
                    for region in region_names:
                        scanned_cells.pop(f"{region}_p1", None)
                    save_checkpoint(cycle, scanned_cells)

                # Full coverage scan every 10 cycles (also parallel)
                if cycle % 10 == 0 and self.running:
                    logger.info("\n--- FULL COVERAGE SCAN (PARALLEL) ---")
                    total_p3_events = 0

                    with ThreadPoolExecutor(max_workers=len(region_names)) as executor:
                        futures = {}
                        for region in region_names:
                            key = f"{region}_p3"
                            already_scanned = set(scanned_cells.get(key, []))
                            futures[executor.submit(scan_region, region, 3, today, already_scanned, key)] = (region, key)

                        for future in as_completed(futures):
                            region, key = futures[future]
                            try:
                                result = future.result()
                                total_p3_events += result["events"]

                                # Checkpoint is saved per-cell by callback, no need to save here

                                if result["events"] > 0:
                                    logger.info(f"  [{region.upper()}] +{result['events']} events")
                            except Exception as e:
                                logger.error(f"  [{region.upper()}] Thread error: {e}")

                    logger.info(f"P3 coverage complete: +{total_p3_events} total events")

                    # Clear P3 checkpoint data after successful coverage scan
                    for region in region_names:
                        scanned_cells.pop(f"{region}_p3", None)
                    save_checkpoint(cycle, scanned_cells)

                # Print summary every 5 cycles
                if cycle % 5 == 0:
                    logger.info("\n--- DATABASE SUMMARY ---")
                    for region_name, db in self.databases.items():
                        result = db.execute(
                            "SELECT COUNT(*) as events, COUNT(DISTINCT username) as users FROM events"
                        ).fetchone()
                        logger.info(f"  {region_name.upper():10}: {result[0]:,} events, {result[1]:,} users")

                # Wait between cycles (shorter since parallel is faster)
                if self.running:
                    time.sleep(10)

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            self._remove_pid()
            for db in self.databases.values():
                db.close()
            logger.info("Worldwide collector stopped.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Worldwide Waze Data Collector")
    parser.add_argument("--generate-configs", action="store_true", help="Generate all configs and exit")
    parser.add_argument("--status", action="store_true", help="Show collector status")
    args = parser.parse_args()

    if args.generate_configs:
        from europe_grid import save_europe_config
        from americas_grid import save_americas_config
        from asia_grid import save_asia_config
        from oceania_grid import save_oceania_config
        from africa_grid import save_africa_config

        save_europe_config()
        save_americas_config()
        save_asia_config()
        save_oceania_config()
        save_africa_config()
        return

    if args.status:
        pid = WorldwideCollector.get_pid()
        print(f"Worldwide Collector: {'Running (PID ' + str(pid) + ')' if pid else 'Stopped'}")
        return

    collector = WorldwideCollector()
    collector.run()


if __name__ == "__main__":
    main()
