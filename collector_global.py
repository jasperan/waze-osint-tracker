# collector_global.py
"""Global Waze data collector managing multiple regions autonomously."""

import hashlib
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("global")


def generate_event_hash(username: str, latitude: float, longitude: float,
                        timestamp_ms: int, report_type: str) -> str:
    timestamp_minute = timestamp_ms // 60000
    lat_rounded = round(latitude, 4)
    lon_rounded = round(longitude, 4)
    data = f"{username}|{lat_rounded}|{lon_rounded}|{timestamp_minute}|{report_type}"
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

    event_hash = generate_event_hash(username, latitude, longitude, timestamp_ms, report_type)

    return {
        "event_hash": event_hash,
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


class RegionCollector:
    """Collector for a specific region."""

    def __init__(self, name: str, config: Dict[str, Any], db, client):
        self.name = name
        self.config = config
        self.db = db
        self.client = client
        self.logger = logging.getLogger(name)
        self.stats = {"requests": 0, "errors": 0, "events": 0}

    def scan_cells(self, cells: List[Dict], running_flag) -> Dict[str, int]:
        """Scan a list of grid cells."""
        cycle_stats = {"requests": 0, "errors": 0, "events": 0}

        for cell in cells:
            if not running_flag():
                break

            try:
                cycle_stats["requests"] += 1
                self.stats["requests"] += 1

                alerts, _ = self.client.get_traffic_notifications(
                    lat_top=cell["lat_top"],
                    lat_bottom=cell["lat_bottom"],
                    lon_left=cell["lon_left"],
                    lon_right=cell["lon_right"]
                )

                new_count = 0
                for alert in alerts:
                    event = process_alert(alert, cell["name"])
                    if self.db.insert_event(event):
                        new_count += 1
                        self.db.upsert_tracked_user(event["username"], event["timestamp_utc"])

                cycle_stats["events"] += new_count
                self.stats["events"] += new_count

                if new_count > 0:
                    self.logger.info(f"{cell['name']}: +{new_count} new")

            except Exception as e:
                cycle_stats["errors"] += 1
                self.stats["errors"] += 1
                self.logger.error(f"Error {cell['name']}: {e}")

        return cycle_stats


class GlobalCollector:
    """Global collector managing Europe and Americas."""

    def __init__(self, config_path: str = "config_global.yaml"):
        self.config_path = config_path
        self.running = False
        self.pid_file = "collector_global.pid"
        self.regions = {}
        self.databases = {}
        self.clients = {}

    def _generate_configs(self):
        """Generate regional configs if they don't exist."""
        from americas_grid import save_americas_config
        from europe_grid import save_europe_config

        if not os.path.exists("config_europe.yaml"):
            logger.info("Generating Europe config...")
            save_europe_config("config_europe.yaml")

        if not os.path.exists("config_americas.yaml"):
            logger.info("Generating Americas config...")
            save_americas_config("config_americas.yaml")

    def _load_region_config(self, path: str) -> Dict[str, Any]:
        with open(path) as f:
            return yaml.safe_load(f)

    def _save_pid(self):
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self):
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)

    @staticmethod
    def get_pid() -> Optional[int]:
        if os.path.exists("collector_global.pid"):
            with open("collector_global.pid") as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                return pid
            except OSError:
                return None
        return None

    def _scan_region(self, region_name: str, cells: List[Dict], priority: int,
                     db, client, running_flag) -> Dict[str, int]:
        """Scan cells for a region."""
        region_logger = logging.getLogger(region_name)
        stats = {"requests": 0, "errors": 0, "events": 0}

        for cell in cells:
            if not running_flag():
                break

            try:
                stats["requests"] += 1
                alerts, _ = client.get_traffic_notifications(
                    lat_top=cell["lat_top"],
                    lat_bottom=cell["lat_bottom"],
                    lon_left=cell["lon_left"],
                    lon_right=cell["lon_right"]
                )

                new_count = 0
                for alert in alerts:
                    event = process_alert(alert, cell["name"])
                    if db.insert_event(event):
                        new_count += 1
                        db.upsert_tracked_user(event["username"], event["timestamp_utc"])

                stats["events"] += new_count

                rate_status = client.get_rate_limit_status()
                if new_count > 0 or rate_status.get("current_delay", 0) > 3:
                    region_logger.info(f"{cell['name']}: {len(alerts)} alerts, +{new_count} new")

            except Exception as e:
                stats["errors"] += 1
                region_logger.error(f"Error {cell['name']}: {e}")

        return stats

    def run(self):
        """Main collection loop for all regions."""
        from database import Database
        from waze_client import WazeClient

        self._generate_configs()

        # Load configurations
        europe_config = self._load_region_config("config_europe.yaml")
        americas_config = self._load_region_config("config_americas.yaml")

        # Set up databases
        Path("data").mkdir(exist_ok=True)
        db_europe = Database(europe_config["database_path"])
        db_americas = Database(americas_config["database_path"])

        # Set up clients (separate rate limiters)
        client_europe = WazeClient()
        client_americas = WazeClient()

        # Group cells by priority
        def group_by_priority(cells):
            by_p = {}
            for c in cells:
                p = c.get("priority", 2)
                if p not in by_p:
                    by_p[p] = []
                by_p[p].append(c)
            return by_p

        europe_cells = group_by_priority(europe_config.get("grid_cells", []))
        americas_cells = group_by_priority(americas_config.get("grid_cells", []))

        total_europe = sum(len(v) for v in europe_cells.values())
        total_americas = sum(len(v) for v in americas_cells.values())

        self.running = True
        self._save_pid()

        def handle_signal(signum, frame):
            logger.info("Shutdown signal received...")
            self.running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        logger.info("=" * 70)
        logger.info("GLOBAL WAZE COLLECTOR - Europe + Americas")
        logger.info("=" * 70)
        logger.info(f"Europe cells: {total_europe} (P1: {len(europe_cells.get(1, []))}, P3: {len(europe_cells.get(3, []))})")
        logger.info(f"Americas cells: {total_americas} (P1: {len(americas_cells.get(1, []))}, P3: {len(americas_cells.get(3, []))})")
        logger.info("Collection strategy:")
        logger.info("  - Priority 1 (cities): every cycle, alternating regions")
        logger.info("  - Priority 3 (coverage): every 5th cycle")
        logger.info("=" * 70)

        cycle = 0
        try:
            while self.running:
                cycle += 1
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                logger.info(f"=== Cycle {cycle} ===")

                # Alternate between regions for priority 1 cells
                if cycle % 2 == 1:
                    # Europe priority 1
                    if 1 in europe_cells:
                        logger.info(f"[EUROPE] Scanning {len(europe_cells[1])} city cells...")
                        stats = self._scan_region("europe", europe_cells[1], 1,
                                                  db_europe, client_europe, lambda: self.running)
                        logger.info(f"[EUROPE] +{stats['events']} events, {stats['errors']} errors")
                else:
                    # Americas priority 1
                    if 1 in americas_cells:
                        logger.info(f"[AMERICAS] Scanning {len(americas_cells[1])} city cells...")
                        stats = self._scan_region("americas", americas_cells[1], 1,
                                                  db_americas, client_americas, lambda: self.running)
                        logger.info(f"[AMERICAS] +{stats['events']} events, {stats['errors']} errors")

                # Full coverage scan every 5th cycle
                if cycle % 5 == 0:
                    # Europe coverage
                    if 3 in europe_cells and self.running:
                        logger.info(f"[EUROPE] Full coverage scan ({len(europe_cells[3])} cells)...")
                        stats = self._scan_region("europe", europe_cells[3], 3,
                                                  db_europe, client_europe, lambda: self.running)
                        logger.info(f"[EUROPE] Coverage: +{stats['events']} events")

                if cycle % 5 == 0:
                    # Americas coverage
                    if 3 in americas_cells and self.running:
                        logger.info(f"[AMERICAS] Full coverage scan ({len(americas_cells[3])} cells)...")
                        stats = self._scan_region("americas", americas_cells[3], 3,
                                                  db_americas, client_americas, lambda: self.running)
                        logger.info(f"[AMERICAS] Coverage: +{stats['events']} events")

                # Update daily stats
                for db, name in [(db_europe, "europe"), (db_americas, "americas")]:
                    unique_users = db.execute(
                        "SELECT COUNT(DISTINCT username) FROM events WHERE DATE(timestamp_utc) = ?",
                        (today,)
                    ).fetchone()[0]
                    db.update_daily_stats(date=today, users=unique_users, requests=0, errors=0, cells=0)

                if self.running:
                    interval = 30  # 30 seconds between cycles
                    logger.info(f"Waiting {interval}s...")
                    time.sleep(interval)

        finally:
            self._remove_pid()
            db_europe.close()
            db_americas.close()
            logger.info("Global collector stopped.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Global Waze Data Collector")
    parser.add_argument("--generate-configs", action="store_true", help="Generate configs and exit")
    args = parser.parse_args()

    if args.generate_configs:
        from americas_grid import save_americas_config
        from europe_grid import save_europe_config
        save_europe_config()
        save_americas_config()
        return

    collector = GlobalCollector()
    collector.run()


if __name__ == "__main__":
    main()
