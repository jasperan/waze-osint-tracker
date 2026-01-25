# collector_europe.py
"""Autonomous Europe-wide Waze data collector with priority-based scanning."""

import hashlib
import json
import time
import os
import signal
import sys
import yaml
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def generate_event_hash(
    username: str,
    latitude: float,
    longitude: float,
    timestamp_ms: int,
    report_type: str
) -> str:
    """Generate unique hash for event deduplication."""
    timestamp_minute = timestamp_ms // 60000
    lat_rounded = round(latitude, 4)
    lon_rounded = round(longitude, 4)
    data = f"{username}|{lat_rounded}|{lon_rounded}|{timestamp_minute}|{report_type}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def process_alert(alert: Dict[str, Any], grid_cell: str) -> Dict[str, Any]:
    """Process raw Waze alert into event record."""
    username = alert.get("reportBy", "anonymous")
    latitude = alert.get("latitude", 0.0)
    longitude = alert.get("longitude", 0.0)
    timestamp_ms = alert.get("pubMillis", int(time.time() * 1000))
    report_type = alert.get("type", "UNKNOWN")
    subtype = alert.get("subtype")

    timestamp_utc = datetime.fromtimestamp(
        timestamp_ms / 1000, tz=timezone.utc
    ).isoformat()

    event_hash = generate_event_hash(
        username=username,
        latitude=latitude,
        longitude=longitude,
        timestamp_ms=timestamp_ms,
        report_type=report_type
    )

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


class EuropeCollector:
    """Autonomous collector for Europe-wide Waze data."""

    def __init__(self, config_path: str = "config_europe.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.running = False
        self.pid_file = "collector_europe.pid"
        self.stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_events": 0,
            "last_full_scan": None,
            "current_cycle": 0
        }

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            logger.info(f"Config not found, generating Europe grid...")
            from europe_grid import save_europe_config
            save_europe_config(self.config_path)

        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _save_pid(self):
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self):
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)

    @staticmethod
    def get_pid() -> Optional[int]:
        """Get PID of running collector, or None if not running."""
        if os.path.exists("collector_europe.pid"):
            with open("collector_europe.pid") as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                return pid
            except OSError:
                return None
        return None

    def _load_cells_by_priority(self) -> Dict[int, List[Dict]]:
        """Load grid cells grouped by priority."""
        cells = self.config.get("grid_cells", [])
        by_priority = {}
        for cell in cells:
            priority = cell.get("priority", 2)
            if priority not in by_priority:
                by_priority[priority] = []
            by_priority[priority].append(cell)
        return by_priority

    def _scan_cells(self, cells: List[Dict], db, client) -> Dict[str, int]:
        """Scan a list of grid cells and return stats."""
        stats = {"requests": 0, "errors": 0, "events": 0}

        for cell in cells:
            if not self.running:
                break

            try:
                stats["requests"] += 1
                self.stats["total_requests"] += 1

                alerts, jams = client.get_traffic_notifications(
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
                        db.upsert_tracked_user(
                            event["username"],
                            event["timestamp_utc"]
                        )

                stats["events"] += new_count
                self.stats["total_events"] += new_count

                # Log progress periodically
                rate_status = client.get_rate_limit_status()
                if new_count > 0 or rate_status["current_delay"] > 2:
                    delay_info = f" [delay:{rate_status['current_delay']:.1f}s]" if rate_status["current_delay"] > 2 else ""
                    logger.info(f"{cell['name']}: {len(alerts)} alerts, +{new_count} new{delay_info}")

            except Exception as e:
                stats["errors"] += 1
                self.stats["total_errors"] += 1
                logger.error(f"Error scanning {cell['name']}: {e}")
                # Continue to next cell on error

        return stats

    def run(self):
        """Main autonomous collection loop."""
        from database import Database
        from waze_client import WazeClient

        # Ensure database directory exists
        db_path = self.config["database_path"]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        db = Database(db_path)
        client = WazeClient(self.config.get("waze_server_url"))

        # Load cells by priority
        cells_by_priority = self._load_cells_by_priority()
        priorities = sorted(cells_by_priority.keys())

        total_cells = sum(len(c) for c in cells_by_priority.values())
        priority_1_count = len(cells_by_priority.get(1, []))
        priority_3_count = len(cells_by_priority.get(3, []))

        self.running = True
        self._save_pid()

        def handle_signal(signum, frame):
            logger.info("Shutdown signal received...")
            self.running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        logger.info("=" * 60)
        logger.info("Europe Waze Collector starting...")
        logger.info(f"Database: {db_path}")
        logger.info(f"Total grid cells: {total_cells}")
        logger.info(f"  Priority 1 (cities): {priority_1_count}")
        logger.info(f"  Priority 3 (coverage): {priority_3_count}")
        logger.info("Collection strategy:")
        logger.info("  - Priority 1 cells: every cycle")
        logger.info("  - Priority 3 cells: every 5th cycle")
        logger.info("=" * 60)

        try:
            while self.running:
                self.stats["current_cycle"] += 1
                cycle = self.stats["current_cycle"]
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                logger.info(f"--- Cycle {cycle} started ---")
                cycle_stats = {"requests": 0, "errors": 0, "events": 0}

                # Always scan high-priority cells (cities)
                if 1 in cells_by_priority:
                    logger.info(f"Scanning {len(cells_by_priority[1])} priority-1 cells (cities)...")
                    stats = self._scan_cells(cells_by_priority[1], db, client)
                    for k in cycle_stats:
                        cycle_stats[k] += stats[k]

                # Scan medium-priority cells every 3rd cycle
                if 2 in cells_by_priority and cycle % 3 == 0:
                    logger.info(f"Scanning {len(cells_by_priority[2])} priority-2 cells...")
                    stats = self._scan_cells(cells_by_priority[2], db, client)
                    for k in cycle_stats:
                        cycle_stats[k] += stats[k]

                # Scan low-priority cells (coverage) every 5th cycle
                if 3 in cells_by_priority and cycle % 5 == 0:
                    logger.info(f"Scanning {len(cells_by_priority[3])} priority-3 cells (coverage)...")
                    stats = self._scan_cells(cells_by_priority[3], db, client)
                    for k in cycle_stats:
                        cycle_stats[k] += stats[k]
                    self.stats["last_full_scan"] = datetime.now(timezone.utc).isoformat()

                # Update daily stats
                unique_users = db.execute(
                    "SELECT COUNT(DISTINCT username) FROM events WHERE DATE(timestamp_utc) = ?",
                    (today,)
                ).fetchone()[0]

                db.update_daily_stats(
                    date=today,
                    events=cycle_stats["events"],
                    users=unique_users,
                    requests=cycle_stats["requests"],
                    errors=cycle_stats["errors"],
                    cells=cycle_stats["requests"]
                )

                # Log cycle summary
                logger.info(
                    f"Cycle {cycle} complete: "
                    f"+{cycle_stats['events']} events, "
                    f"{cycle_stats['requests']} requests, "
                    f"{cycle_stats['errors']} errors"
                )
                logger.info(
                    f"Totals: {self.stats['total_events']} events, "
                    f"{self.stats['total_requests']} requests"
                )

                # Wait between cycles
                if self.running:
                    interval = self.config.get("polling_interval_seconds", 60)
                    logger.info(f"Waiting {interval}s until next cycle...")
                    time.sleep(interval)

        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
        finally:
            self._remove_pid()
            db.close()
            logger.info("Europe collector stopped.")


def main():
    """Entry point for Europe collector."""
    import argparse

    parser = argparse.ArgumentParser(description="Europe Waze Data Collector")
    parser.add_argument("--config", default="config_europe.yaml", help="Config file path")
    parser.add_argument("--generate-config", action="store_true", help="Generate config and exit")
    args = parser.parse_args()

    if args.generate_config:
        from europe_grid import save_europe_config
        save_europe_config(args.config)
        return

    collector = EuropeCollector(args.config)
    collector.run()


if __name__ == "__main__":
    main()
