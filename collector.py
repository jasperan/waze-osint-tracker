# collector.py
import hashlib
import json
import time
import os
import signal
import sys
import yaml
import logging
from pathlib import Path
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
    def __init__(self, config_path: str = "config.yaml", web_port: int = None):
        self.config_path = config_path
        self.config = self._load_config()
        self.running = False
        self.pid_file = "collector.pid"
        self.web_port = web_port
        self.logger = None
        self._setup_logging()

    def _setup_logging(self):
        """Set up logging to both console and file."""
        Path("logs").mkdir(exist_ok=True)
        self.logger = logging.getLogger("collector")
        self.logger.setLevel(logging.INFO)
        # Clear any existing handlers
        self.logger.handlers.clear()
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(console_handler)
        # File handler
        file_handler = logging.FileHandler('logs/collector.log')
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        self.logger.addHandler(file_handler)

    def log(self, msg):
        """Log a message to both console and file."""
        self.logger.info(msg)

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

    def _start_web_server(self):
        """Start Flask web server in a background thread."""
        import threading
        def run_flask():
            import logging as flask_logging
            flask_log = flask_logging.getLogger('werkzeug')
            flask_log.setLevel(flask_logging.WARNING)

            project_root = os.path.dirname(os.path.abspath(__file__))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from web.app import app
            app.run(host="0.0.0.0", port=self.web_port, debug=False, threaded=True, use_reloader=False)

        web_thread = threading.Thread(target=run_flask, daemon=True)
        web_thread.start()
        self.log(f"Web UI started at http://localhost:{self.web_port}")
        return web_thread

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

        # Start web server if requested
        if self.web_port:
            self._start_web_server()

        def handle_signal(signum, frame):
            self.log("Shutting down collector...")
            self.running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        self.log(f"Collector started. Polling every {interval} seconds.")
        self.log(f"Grid cells: {[c.name for c in cells]}")
        self.log(f"Rate limiting: enabled (1.5s min delay, exponential backoff)")

        try:
            while self.running:
                # Daily stats tracking
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                cycle_events = 0
                cycle_errors = 0
                cycle_requests = 0
                type_counts = {}

                for cell in cells:
                    if not self.running:
                        break

                    try:
                        cycle_requests += 1
                        alerts, jams = client.get_traffic_notifications(**cell.to_params())
                        new_count = 0

                        for alert in alerts:
                            event = process_alert(alert, cell.name)
                            if db.insert_event(event):
                                new_count += 1
                                cycle_events += 1
                                # Track the user
                                db.upsert_tracked_user(
                                    event["username"],
                                    event["timestamp_utc"]
                                )
                                # Count by type
                                t = event["report_type"]
                                type_counts[t] = type_counts.get(t, 0) + 1

                        # Show rate limiter status if backing off
                        rate_status = client.get_rate_limit_status()
                        delay_info = ""
                        if rate_status["current_delay"] > 2:
                            delay_info = f" [delay: {rate_status['current_delay']:.1f}s]"

                        self.log(f"[{datetime.now().strftime('%H:%M:%S')}] {cell.name}: "
                              f"{len(alerts)} alerts, {new_count} new{delay_info}")

                    except Exception as e:
                        cycle_errors += 1
                        self.log(f"[{datetime.now().strftime('%H:%M:%S')}] Error {cell.name}: {e}")

                # Update daily stats after each full cycle
                unique_users = db.execute(
                    "SELECT COUNT(DISTINCT username) FROM events WHERE DATE(timestamp_utc) = ?",
                    (today,)
                ).fetchone()[0]

                db.update_daily_stats(
                    date=today,
                    events=cycle_events,
                    users=unique_users,
                    requests=cycle_requests,
                    errors=cycle_errors,
                    cells=len(cells),
                    by_type=type_counts if type_counts else None
                )

                if cycle_events > 0:
                    self.log(f"[{datetime.now().strftime('%H:%M:%S')}] Cycle complete: "
                          f"+{cycle_events} events, {cycle_errors} errors")

                if self.running:
                    time.sleep(interval)
        finally:
            self._remove_pid()
            db.close()
            self.log("Collector stopped.")
