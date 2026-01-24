# collector.py
import hashlib
import json
import time
import os
import signal
import sys
import yaml
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

def generate_event_hash(
    username: str,
    latitude: float,
    longitude: float,
    timestamp_ms: int,
    report_type: str
) -> str:
    """Generate unique hash for event deduplication."""
    # Round timestamp to minute for dedup (same event reported twice in same minute)
    timestamp_minute = timestamp_ms // 60000
    # Round coordinates to 4 decimal places (~11m precision)
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


class Collector:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.running = False
        self.pid_file = "collector.pid"

    def _load_config(self) -> Dict[str, Any]:
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
        if os.path.exists("collector.pid"):
            with open("collector.pid") as f:
                pid = int(f.read().strip())
            # Check if process is actually running
            try:
                os.kill(pid, 0)
                return pid
            except OSError:
                return None
        return None

    def run(self):
        """Main collection loop."""
        from database import Database
        from waze_client import WazeClient
        from grid import load_grid_cells

        db = Database(self.config["database_path"])
        client = WazeClient(self.config["waze_server_url"])
        cells = load_grid_cells(self.config)
        interval = self.config.get("polling_interval_seconds", 300)

        self.running = True
        self._save_pid()

        def handle_signal(signum, frame):
            print("\nShutting down collector...")
            self.running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        print(f"Collector started. Polling every {interval} seconds.")
        print(f"Grid cells: {[c.name for c in cells]}")

        try:
            while self.running:
                for cell in cells:
                    if not self.running:
                        break

                    try:
                        alerts, jams = client.get_traffic_notifications(**cell.to_params())
                        new_count = 0

                        for alert in alerts:
                            event = process_alert(alert, cell.name)
                            if db.insert_event(event):
                                new_count += 1

                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {cell.name}: "
                              f"{len(alerts)} alerts, {new_count} new")

                    except Exception as e:
                        print(f"Error collecting {cell.name}: {e}")

                if self.running:
                    time.sleep(interval)
        finally:
            self._remove_pid()
            db.close()
            print("Collector stopped.")
