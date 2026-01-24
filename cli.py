# cli.py
import os
import sys
import signal
import click
import yaml
import json
import time
import threading
import logging
from pathlib import Path
from tabulate import tabulate
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich import box

# Rich console with custom theme for event types
WAZE_THEME = Theme({
    "police": "bold blue",
    "hazard": "bold yellow",
    "jam": "bold orange1",
    "accident": "bold red",
    "road_closed": "bold magenta",
    "chit_chat": "bold cyan",
    "info": "dim white",
    "success": "bold green",
    "error": "bold red",
    "region.europe": "blue",
    "region.americas": "green",
    "region.asia": "yellow",
    "region.oceania": "cyan",
    "region.africa": "magenta",
})

console = Console(theme=WAZE_THEME)

# Color map for event types
EVENT_COLORS = {
    "POLICE": "police",
    "HAZARD": "hazard",
    "JAM": "jam",
    "ACCIDENT": "accident",
    "ROAD_CLOSED": "road_closed",
    "CHIT_CHAT": "chit_chat",
}

REGION_COLORS = {
    "europe": "region.europe",
    "americas": "region.americas",
    "asia": "region.asia",
    "oceania": "region.oceania",
    "africa": "region.africa",
}

@click.group()
def cli():
    """Waze Worldwide Logger - Global traffic event collection and analysis."""
    pass

def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)

def get_db(region=None):
    """Get database connection for a specific region or default Madrid."""
    from database import Database
    if region:
        db_path = f"./data/waze_{region}.db"
        if os.path.exists(db_path):
            return Database(db_path)
    config = load_config()
    return Database(config["database_path"])

def get_all_dbs():
    """Get connections to all existing regional databases."""
    from database import Database
    DB_PATHS = {
        "madrid": "./data/waze_madrid.db",
        "europe": "./data/waze_europe.db",
        "americas": "./data/waze_americas.db",
        "asia": "./data/waze_asia.db",
        "oceania": "./data/waze_oceania.db",
        "africa": "./data/waze_africa.db",
    }
    dbs = []
    for region, path in DB_PATHS.items():
        if os.path.exists(path):
            try:
                dbs.append((region, Database(path)))
            except Exception:
                pass
    return dbs

# === Worldwide Collection System ===

# Status/checkpoint file paths
STATUS_FILE = "./data/collector_status.json"
CHECKPOINT_FILE = "./data/collector_checkpoint.json"
PID_FILE = "./collector_cli.pid"

status_lock = threading.Lock()
checkpoint_lock = threading.Lock()


def write_status(region: str, cell_name: str, country: str, cell_idx: int, total_cells: int,
                 alerts_count: int, new_count: int, event_types: list = None):
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
        pass


def load_checkpoint():
    """Load checkpoint from file."""
    try:
        if os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"cycle": 0, "scanned": {}}


def save_checkpoint(cycle: int, scanned: dict):
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


def generate_event_hash(username: str, latitude: float, longitude: float,
                        timestamp_ms: int, report_type: str) -> str:
    """Generate unique hash for event deduplication."""
    import hashlib
    timestamp_minute = timestamp_ms // 60000
    data = f"{username}|{round(latitude, 4)}|{round(longitude, 4)}|{timestamp_minute}|{report_type}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def process_alert(alert: dict, grid_cell: str) -> dict:
    """Process a Waze alert into event format."""
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

    def __init__(self, name: str, config_path: str, db, client, logger):
        self.name = name
        self.config_path = config_path
        self.db = db
        self.client = client
        self.logger = logger
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

    def get_cell_counts(self) -> dict:
        return {p: len(cells) for p, cells in self.cells_by_priority.items()}

    def scan(self, priority: int, running_flag, already_scanned: set = None,
             on_cell_scanned: callable = None) -> dict:
        """Scan cells of given priority, skipping already-scanned cells."""
        cells = self.cells_by_priority.get(priority, [])
        stats = {"requests": 0, "errors": 0, "events": 0, "cells": len(cells), "scanned_cells": []}
        total_cells = len(cells)
        already_scanned = already_scanned or set()

        # Filter out already-scanned cells
        remaining_cells = [(idx, cell) for idx, cell in enumerate(cells, 1)
                          if cell["name"] not in already_scanned]

        if len(remaining_cells) < len(cells):
            skipped = len(cells) - len(remaining_cells)
            console.print(f"  [dim]Resuming: skipping {skipped} cells, {len(remaining_cells)} remaining[/dim]")

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
                new_events = []
                for alert in alerts:
                    event = process_alert(alert, cell_name)
                    if self.db.insert_event(event):
                        new_count += 1
                        new_events.append(event)
                        self.db.upsert_tracked_user(event["username"], event["timestamp_utc"])

                stats["events"] += new_count
                stats["scanned_cells"].append(cell_name)

                if on_cell_scanned:
                    on_cell_scanned(cell_name)

                # Log each new event individually with coordinates using Rich
                for event in new_events:
                    lat = event["latitude"]
                    lon = event["longitude"]
                    etype = event["report_type"]
                    subtype = event.get("subtype") or ""
                    user = event["username"][:20]

                    # Get color style for event type
                    style = EVENT_COLORS.get(etype, "info")
                    subtype_str = f" ({subtype})" if subtype else ""

                    # Build styled text
                    line = Text()
                    line.append("  + ", style="success")
                    line.append(f"{etype:12}", style=style)
                    line.append(" @ ", style="dim")
                    line.append(f"{lat:9.5f}, {lon:10.5f}", style="cyan")
                    line.append(subtype_str, style="dim")
                    line.append(f" - {user}", style="dim white")
                    console.print(line)

                # Write status for UI (aggregated)
                if new_count > 0:
                    event_types = [e["report_type"] for e in new_events]
                    write_status(
                        region=self.name,
                        cell_name=cell_name,
                        country=country,
                        cell_idx=idx,
                        total_cells=total_cells,
                        alerts_count=len(alerts),
                        new_count=new_count,
                        event_types=event_types
                    )

            except Exception as e:
                stats["errors"] += 1
                stats["scanned_cells"].append(cell["name"])
                console.print(f"  [bold red]ERROR[/bold red] [{idx:3}/{total_cells}] {cell['name']:25} -> {e}")

        return stats


class CLIWorldwideCollector:
    """Multi-threaded worldwide Waze data collector for CLI."""

    REGIONS = [
        ("europe", "config_europe.yaml", "./data/waze_europe.db"),
        ("americas", "config_americas.yaml", "./data/waze_americas.db"),
        ("asia", "config_asia.yaml", "./data/waze_asia.db"),
        ("oceania", "config_oceania.yaml", "./data/waze_oceania.db"),
        ("africa", "config_africa.yaml", "./data/waze_africa.db"),
    ]

    def __init__(self, web_port=None, regions=None):
        self.running = False
        self.web_port = web_port
        self.selected_regions = regions  # None = all regions
        self.scanners = {}
        self.databases = {}
        self.clients = {}
        self.logger = None

    def _setup_logging(self):
        """Set up logging for the collector."""
        Path("logs").mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('logs/cli_collector.log')
            ]
        )
        self.logger = logging.getLogger("cli_collector")

    def _generate_configs(self):
        """Generate regional configs if they don't exist."""
        config_generators = [
            ("europe", "europe_grid", "save_europe_config"),
            ("americas", "americas_grid", "save_americas_config"),
            ("asia", "asia_grid", "save_asia_config"),
            ("oceania", "oceania_grid", "save_oceania_config"),
            ("africa", "africa_grid", "save_africa_config"),
        ]

        for region_name, module_name, func_name in config_generators:
            config_file = f"config_{region_name}.yaml"
            if not os.path.exists(config_file):
                console.print(f"[dim]Generating {config_file}...[/dim]")
                try:
                    module = __import__(module_name)
                    getattr(module, func_name)()
                except ImportError:
                    console.print(f"[yellow]Could not import {module_name}, skipping {region_name}[/yellow]")

    def _save_pid(self):
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self):
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

    @staticmethod
    def get_pid():
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                return pid
            except (OSError, ValueError):
                return None
        return None

    def _start_web_server(self):
        """Start Flask web server in a background thread."""
        def run_flask():
            # Suppress Flask's default logging
            import logging as flask_logging
            flask_log = flask_logging.getLogger('werkzeug')
            flask_log.setLevel(flask_logging.WARNING)

            # Add project root to path for web module import
            project_root = os.path.dirname(os.path.abspath(__file__))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from web.app import app
            app.run(host="0.0.0.0", port=self.web_port, debug=False, threaded=True, use_reloader=False)

        web_thread = threading.Thread(target=run_flask, daemon=True)
        web_thread.start()
        console.print(f"[bold green]Web UI started at[/bold green] [bold underline blue]http://localhost:{self.web_port}[/bold underline blue]")
        return web_thread

    def run(self):
        """Main worldwide collection loop."""
        from database import Database
        from waze_client import WazeClient

        self._setup_logging()

        # Create directories
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Generate configs
        self._generate_configs()

        # Start web server if requested
        if self.web_port:
            self._start_web_server()

        # Filter regions if specified
        regions_to_scan = self.REGIONS
        if self.selected_regions:
            regions_to_scan = [r for r in self.REGIONS if r[0] in self.selected_regions]

        # Initialize scanners - Rich banner
        console.print()
        console.print(Panel.fit(
            "[bold white]WAZE WORLDWIDE COLLECTOR[/bold white]",
            border_style="blue",
            padding=(0, 2)
        ))
        console.print()

        total_p1 = 0
        total_p3 = 0

        for region_name, config_path, db_path in regions_to_scan:
            if not os.path.exists(config_path):
                console.print(f"[yellow]Config not found: {config_path}, skipping {region_name}[/yellow]")
                continue

            db = Database(db_path, check_same_thread=False)
            client = WazeClient()

            scanner = RegionScanner(region_name, config_path, db, client, self.logger)
            self.scanners[region_name] = scanner
            self.databases[region_name] = db
            self.clients[region_name] = client

            counts = scanner.get_cell_counts()
            p1 = counts.get(1, 0)
            p3 = counts.get(3, 0)
            total_p1 += p1
            total_p3 += p3

        # Create Rich table for regions
        region_table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        region_table.add_column("Region", style="bold")
        region_table.add_column("P1 (Cities)", justify="right", style="cyan")
        region_table.add_column("P3 (Coverage)", justify="right", style="yellow")
        region_table.add_column("Total", justify="right", style="green")

        for region_name in self.scanners:
            counts = self.scanners[region_name].get_cell_counts()
            p1 = counts.get(1, 0)
            p3 = counts.get(3, 0)
            region_style = REGION_COLORS.get(region_name, "white")
            region_table.add_row(
                Text(region_name.upper(), style=region_style),
                str(p1),
                str(p3),
                str(p1 + p3)
            )

        region_table.add_row("", "", "", "", style="dim")
        region_table.add_row(
            Text("TOTAL", style="bold white"),
            Text(str(total_p1), style="bold cyan"),
            Text(str(total_p3), style="bold yellow"),
            Text(str(total_p1 + total_p3), style="bold green")
        )
        console.print(region_table)
        console.print()

        # Strategy info
        strategy_text = Text()
        strategy_text.append("Collection Strategy ", style="bold")
        strategy_text.append("(MULTITHREADED)\n", style="bold cyan")
        strategy_text.append("  • All regions scanned in PARALLEL for P1 (city) scans\n", style="dim")
        strategy_text.append("  • Full P3 (coverage) scan every 10 cycles (parallel)\n", style="dim")
        strategy_text.append("  • 10 second pause between cycles\n", style="dim")
        if self.web_port:
            strategy_text.append(f"  • Web UI at ", style="dim")
            strategy_text.append(f"http://localhost:{self.web_port}", style="bold underline blue")
        console.print(strategy_text)
        console.print()

        self.running = True
        self._save_pid()

        def handle_signal(signum, frame):
            console.print("\n[bold yellow]Shutdown signal received...[/bold yellow]")
            self.running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        region_names = list(self.scanners.keys())

        # Load checkpoint
        checkpoint = load_checkpoint()
        cycle = checkpoint.get("cycle", 0)
        scanned_cells = checkpoint.get("scanned", {})

        if cycle > 0:
            console.print(f"[bold yellow]Resuming from checkpoint:[/bold yellow] cycle {cycle}")

        def scan_region(region_name: str, priority: int, today: str, already_scanned: set,
                        checkpoint_key: str) -> dict:
            """Scan a single region (runs in thread)."""
            scanner = self.scanners[region_name]
            db = self.databases[region_name]

            p_count = scanner.get_cell_counts().get(priority, 0)
            if p_count == 0:
                return {"region": region_name, "events": 0, "errors": 0, "requests": 0, "cells": 0, "scanned_cells": []}

            def on_cell_scanned(cell_name):
                with checkpoint_lock:
                    if checkpoint_key not in scanned_cells:
                        scanned_cells[checkpoint_key] = []
                    scanned_cells[checkpoint_key].append(cell_name)
                save_checkpoint(cycle, scanned_cells)

            stats = scanner.scan(priority, lambda: self.running, already_scanned, on_cell_scanned)

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

                console.print()
                console.rule(f"[bold]CYCLE {cycle}[/bold] [dim](PARALLEL MODE)[/dim]", style="blue")

                # Parallel P1 scan
                console.print(f"[dim]Starting parallel P1 scan across[/dim] [bold cyan]{len(region_names)}[/bold cyan] [dim]regions...[/dim]")
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

                            if result["events"] > 0 or result["errors"] > 0:
                                region_style = REGION_COLORS.get(region, "white")
                                line = Text()
                                line.append("  [", style="dim")
                                line.append(region.upper(), style=region_style)
                                line.append("] ", style="dim")
                                line.append(f"+{result['events']}", style="bold green" if result["events"] > 0 else "dim")
                                line.append(" events", style="dim")
                                if result["errors"] > 0:
                                    line.append(f", {result['errors']} errors", style="bold red")
                                console.print(line)
                        except Exception as e:
                            console.print(f"  [bold red][{region.upper()}] Thread error: {e}[/bold red]")
                            cycle_complete = False

                summary_line = Text()
                summary_line.append("P1 cycle complete: ", style="bold")
                summary_line.append(f"+{total_events}", style="bold green")
                summary_line.append(" total events", style="dim")
                if total_errors > 0:
                    summary_line.append(f", {total_errors} errors", style="bold red")
                console.print(summary_line)

                if cycle_complete:
                    for region in region_names:
                        scanned_cells.pop(f"{region}_p1", None)
                    save_checkpoint(cycle, scanned_cells)

                # Full coverage scan every 10 cycles
                if cycle % 10 == 0 and self.running:
                    console.print()
                    console.rule("[bold yellow]FULL COVERAGE SCAN[/bold yellow] [dim](PARALLEL)[/dim]", style="yellow")
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

                                if result["events"] > 0:
                                    region_style = REGION_COLORS.get(region, "white")
                                    line = Text()
                                    line.append("  [", style="dim")
                                    line.append(region.upper(), style=region_style)
                                    line.append("] ", style="dim")
                                    line.append(f"+{result['events']}", style="bold green")
                                    line.append(" events", style="dim")
                                    console.print(line)
                            except Exception as e:
                                console.print(f"  [bold red][{region.upper()}] Thread error: {e}[/bold red]")

                    p3_summary = Text()
                    p3_summary.append("P3 coverage complete: ", style="bold")
                    p3_summary.append(f"+{total_p3_events}", style="bold green")
                    p3_summary.append(" total events", style="dim")
                    console.print(p3_summary)

                    for region in region_names:
                        scanned_cells.pop(f"{region}_p3", None)
                    save_checkpoint(cycle, scanned_cells)

                # Print summary every 5 cycles
                if cycle % 5 == 0:
                    console.print()
                    console.rule("[bold]DATABASE SUMMARY[/bold]", style="green")

                    summary_table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
                    summary_table.add_column("Region", style="bold")
                    summary_table.add_column("Events", justify="right", style="green")
                    summary_table.add_column("Users", justify="right", style="cyan")

                    for region_name, db in self.databases.items():
                        result = db.execute(
                            "SELECT COUNT(*) as events, COUNT(DISTINCT username) as users FROM events"
                        ).fetchone()
                        region_style = REGION_COLORS.get(region_name, "white")
                        summary_table.add_row(
                            Text(region_name.upper(), style=region_style),
                            f"{result[0]:,}",
                            f"{result[1]:,}"
                        )
                    console.print(summary_table)

                if self.running:
                    time.sleep(10)

        except Exception as e:
            console.print(f"[bold red]Fatal error: {e}[/bold red]")
            self.logger.error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            self._remove_pid()
            for db in self.databases.values():
                db.close()
            console.print("[bold green]Collector stopped.[/bold green]")


# === Collection Commands ===

@cli.command()
@click.option("--web", "-w", is_flag=True, help="Also start the web UI")
@click.option("--port", "-p", default=5000, help="Web UI port (default: 5000)")
@click.option("--region", "-r", multiple=True, help="Specific regions to scan (can be repeated)")
def collect(web, port, region):
    """Start worldwide multi-threaded data collection.

    This runs the full worldwide collector which scans all continents
    in parallel. Use --web to also start the visualization UI.

    Examples:
        waze collect                    # Collect from all regions
        waze collect --web              # Collect + web UI on port 5000
        waze collect --web --port 8080  # Web UI on port 8080
        waze collect -r europe -r asia  # Only Europe and Asia
    """
    pid = CLIWorldwideCollector.get_pid()
    if pid:
        click.echo(f"Collector already running (PID {pid})")
        click.echo(f"Use 'waze logs' to watch live output")
        click.echo(f"Use 'waze stop --worldwide' to stop it")
        return

    web_port = port if web else None
    selected_regions = list(region) if region else None

    click.echo("Starting worldwide collector...")
    if web_port:
        click.echo(f"Web UI will be available at http://localhost:{web_port}")

    collector = CLIWorldwideCollector(web_port=web_port, regions=selected_regions)
    collector.run()


@cli.command()
@click.option("-n", "--lines", default=50, help="Number of lines to show initially")
@click.option("-f/-F", "--follow/--no-follow", default=True, help="Follow log output (default: follow)")
def logs(lines, follow):
    """Watch live collector logs.

    Connect to a running collector and watch its output in real-time.

    Examples:
        waze logs              # Follow live logs
        waze logs -n 100       # Show last 100 lines, then follow
        waze logs -F           # Show recent logs and exit (no follow)
    """
    import subprocess

    log_file = "logs/cli_collector.log"

    # Check if collector is running
    pid = CLIWorldwideCollector.get_pid()
    if not pid:
        click.echo("No worldwide collector is running.")
        click.echo("Start one with: waze collect --web")

        # Still show logs if file exists
        if os.path.exists(log_file):
            click.echo(f"\nShowing last {lines} lines from previous run:\n")
            click.echo("-" * 60)
        else:
            return

    else:
        click.echo(f"Connected to collector (PID {pid})")
        click.echo(f"Log file: {log_file}")
        click.echo("-" * 60)

    if not os.path.exists(log_file):
        click.echo(f"Log file not found: {log_file}")
        return

    try:
        if follow:
            # Use tail -f to follow the log
            cmd = ["tail", "-n", str(lines), "-f", log_file]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            try:
                for line in process.stdout:
                    click.echo(line, nl=False)
            except KeyboardInterrupt:
                process.terminate()
                click.echo("\n\nDisconnected from logs.")
        else:
            # Just show last N lines
            cmd = ["tail", "-n", str(lines), log_file]
            result = subprocess.run(cmd, capture_output=True, text=True)
            click.echo(result.stdout)

    except Exception as e:
        click.echo(f"Error reading logs: {e}")


@cli.command()
@click.option("--europe", is_flag=True, help="Start Europe-wide collector (legacy)")
def start(europe):
    """Start the collector daemon (legacy - use 'collect' for worldwide)."""
    if europe:
        from collector_europe import EuropeCollector
        pid = EuropeCollector.get_pid()
        if pid:
            click.echo(f"Europe collector already running (PID {pid})")
            return
        click.echo("Starting Europe collector...")
        collector = EuropeCollector()
        collector.run()
    else:
        from collector import Collector
        pid = Collector.get_pid()
        if pid:
            click.echo(f"Collector already running (PID {pid})")
            return
        click.echo("Starting collector...")
        collector = Collector()
        collector.run()


@cli.command()
@click.option("--europe", is_flag=True, help="Stop Europe-wide collector")
@click.option("--worldwide", "-w", is_flag=True, help="Stop worldwide collector")
def stop(europe, worldwide):
    """Stop the collector daemon."""
    if worldwide:
        pid = CLIWorldwideCollector.get_pid()
        if not pid:
            click.echo("Worldwide collector is not running")
            return
        click.echo(f"Stopping worldwide collector (PID {pid})...")
        os.kill(pid, signal.SIGTERM)
        click.echo("Stop signal sent")
    elif europe:
        from collector_europe import EuropeCollector
        pid = EuropeCollector.get_pid()
        if not pid:
            click.echo("Europe collector is not running")
            return
        click.echo(f"Stopping Europe collector (PID {pid})...")
        os.kill(pid, signal.SIGTERM)
        click.echo("Stop signal sent")
    else:
        from collector import Collector
        pid = Collector.get_pid()
        if not pid:
            click.echo("Collector is not running")
            return
        click.echo(f"Stopping collector (PID {pid})...")
        os.kill(pid, signal.SIGTERM)
        click.echo("Stop signal sent")

@cli.command()
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all regional databases")
def status(show_all):
    """Show collector status and database summary."""
    from collector import Collector

    # Check all collector types
    worldwide_pid = CLIWorldwideCollector.get_pid()
    madrid_pid = Collector.get_pid()

    click.echo("=== Collector Status ===")
    click.echo(f"Worldwide: {'Running (PID ' + str(worldwide_pid) + ')' if worldwide_pid else 'Stopped'}")
    click.echo(f"Madrid:    {'Running (PID ' + str(madrid_pid) + ')' if madrid_pid else 'Stopped'}")

    # Check for Europe collector
    try:
        from collector_europe import EuropeCollector
        europe_pid = EuropeCollector.get_pid()
        click.echo(f"Europe:    {'Running (PID ' + str(europe_pid) + ')' if europe_pid else 'Stopped'}")
    except ImportError:
        pass

    click.echo()

    if show_all:
        # Show all regional databases
        click.echo("=== Regional Database Summary ===")
        total_events = 0
        all_users = set()
        first_event = None
        last_event = None
        all_types = {}

        dbs = get_all_dbs()
        if not dbs:
            click.echo("No regional databases found")
            return

        table = []
        for region, db in dbs:
            try:
                row = db.execute("""
                    SELECT COUNT(*) as count,
                           COUNT(DISTINCT username) as users,
                           MIN(timestamp_utc) as first_event,
                           MAX(timestamp_utc) as last_event
                    FROM events
                """).fetchone()

                events = row["count"] or 0
                users = row["users"] or 0
                total_events += events

                # Get unique users
                user_rows = db.execute("SELECT DISTINCT username FROM events").fetchall()
                for u in user_rows:
                    all_users.add(u["username"])

                # Get event types
                type_rows = db.execute("""
                    SELECT report_type, COUNT(*) as count FROM events GROUP BY report_type
                """).fetchall()
                for tr in type_rows:
                    t = tr["report_type"]
                    all_types[t] = all_types.get(t, 0) + tr["count"]

                if row["first_event"]:
                    if first_event is None or row["first_event"] < first_event:
                        first_event = row["first_event"]
                if row["last_event"]:
                    if last_event is None or row["last_event"] > last_event:
                        last_event = row["last_event"]

                table.append([
                    region.upper(),
                    f"{events:,}",
                    f"{users:,}",
                    row["first_event"][:10] if row["first_event"] else "N/A",
                    row["last_event"][:10] if row["last_event"] else "N/A"
                ])

                db.close()
            except Exception as e:
                table.append([region.upper(), "Error", str(e)[:30], "", ""])

        click.echo(tabulate(table, headers=["Region", "Events", "Users", "First", "Last"]))

        click.echo(f"\n=== Totals ===")
        click.echo(f"Total events: {total_events:,}")
        click.echo(f"Unique users: {len(all_users):,}")
        if first_event and last_event:
            click.echo(f"Time range: {first_event[:19]} -> {last_event[:19]}")

        if all_types:
            click.echo("\nBy type (all regions):")
            for t, count in sorted(all_types.items(), key=lambda x: -x[1])[:10]:
                pct = count / total_events * 100 if total_events else 0
                click.echo(f"  {t:12} {count:>8,} ({pct:.1f}%)")
    else:
        # Show default Madrid database (legacy behavior)
        config = load_config()
        click.echo(f"Database: {config['database_path']}")
        click.echo(f"Polling interval: {config.get('polling_interval_seconds', 300)}s")
        click.echo()

        if os.path.exists(config["database_path"]):
            from analysis import get_stats
            db = get_db()
            stats = get_stats(db)

            click.echo(f"Total events: {stats['total_events']:,}")
            click.echo(f"Unique users: {stats['unique_users']:,}")

            if stats['first_event']:
                click.echo(f"Time range: {stats['first_event'][:19]} -> {stats['last_event'][:19]}")

            if stats['by_type']:
                click.echo("\nBy type:")
                for t, count in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
                    pct = count / stats['total_events'] * 100 if stats['total_events'] else 0
                    click.echo(f"  {t:12} {count:>6,} ({pct:.1f}%)")

            db.close()
        else:
            click.echo("No data collected yet")

        click.echo("\nTip: Use 'waze status --all' to see all regional databases")

# === Data Exploration Commands ===

@cli.command()
def stats():
    """Show summary statistics."""
    from analysis import get_stats

    db = get_db()
    s = get_stats(db)

    click.echo(f"Total events: {s['total_events']:,}")
    click.echo(f"Unique users: {s['unique_users']:,}")

    if s['first_event']:
        click.echo(f"First event: {s['first_event'][:19]}")
        click.echo(f"Last event: {s['last_event'][:19]}")

    if s['by_type']:
        click.echo("\nBy type:")
        for t, count in sorted(s['by_type'].items(), key=lambda x: -x[1]):
            pct = count / s['total_events'] * 100 if s['total_events'] else 0
            click.echo(f"  {t:12} {count:>6,} ({pct:.1f}%)")

    db.close()

@cli.command()
@click.option("-n", "--limit", default=20, help="Number of events to show")
def recent(limit):
    """Show recent events."""
    from analysis import get_recent_events

    db = get_db()
    events = get_recent_events(db, limit)

    if not events:
        click.echo("No events found")
        return

    table = []
    for e in events:
        table.append([
            e["timestamp_utc"][:19],
            e["username"][:20],
            e["report_type"],
            f"{e['latitude']:.4f}",
            f"{e['longitude']:.4f}"
        ])

    click.echo(tabulate(table, headers=["Time", "User", "Type", "Lat", "Lon"]))
    db.close()

@cli.command()
@click.option("-u", "--username", help="Filter by username")
@click.option("-t", "--type", "report_type", help="Filter by report type")
@click.option("--since", help="Time filter (e.g., '2h', '1d')")
@click.option("-n", "--limit", default=50, help="Max results")
def search(username, report_type, since, limit):
    """Search events with filters."""
    db = get_db()

    query = "SELECT * FROM events WHERE 1=1"
    params = []

    if username:
        query += " AND username = ?"
        params.append(username)

    if report_type:
        query += " AND report_type = ?"
        params.append(report_type.upper())

    if since:
        # Parse time filter
        unit = since[-1]
        value = int(since[:-1])
        if unit == 'h':
            delta = timedelta(hours=value)
        elif unit == 'd':
            delta = timedelta(days=value)
        elif unit == 'm':
            delta = timedelta(minutes=value)
        else:
            click.echo(f"Unknown time unit: {unit}")
            return

        cutoff = datetime.utcnow() - delta
        query += " AND timestamp_utc >= ?"
        params.append(cutoff.isoformat())

    query += " ORDER BY timestamp_ms DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, tuple(params)).fetchall()

    if not rows:
        click.echo("No events found")
        return

    table = []
    for r in rows:
        table.append([
            r["timestamp_utc"][:19],
            r["username"][:20],
            r["report_type"],
            f"{r['latitude']:.4f}",
            f"{r['longitude']:.4f}"
        ])

    click.echo(tabulate(table, headers=["Time", "User", "Type", "Lat", "Lon"]))
    click.echo(f"\n{len(rows)} events found")
    db.close()

# === User Analysis Commands ===

@cli.command()
@click.option("-n", "--limit", default=50, help="Number of users to show")
def users(limit):
    """List users with event counts."""
    from analysis import get_users_summary

    db = get_db()
    user_list = get_users_summary(db, limit)

    if not user_list:
        click.echo("No users found")
        return

    table = []
    for u in user_list:
        table.append([
            u["username"][:25],
            u["event_count"],
            u["first_seen"][:10],
            u["last_seen"][:10]
        ])

    click.echo(tabulate(table, headers=["Username", "Events", "First Seen", "Last Seen"]))
    db.close()

@cli.command()
@click.argument("username")
def profile(username):
    """Show detailed profile for a user."""
    from analysis import get_user_profile

    db = get_db()
    p = get_user_profile(db, username)

    if not p:
        click.echo(f"User '{username}' not found")
        return

    click.echo(f"User: {p['username']}")
    click.echo(f"Events: {p['event_count']}")
    click.echo(f"First seen: {p['first_seen'][:19]}")
    click.echo(f"Last seen: {p['last_seen'][:19]}")
    click.echo(f"Center location: {p['center_location']['lat']:.4f}, {p['center_location']['lon']:.4f}")

    click.echo("\nReport types:")
    for t, count in sorted(p['type_breakdown'].items(), key=lambda x: -x[1]):
        click.echo(f"  {t}: {count}")

    click.echo("\nRecent events:")
    table = []
    for e in p['events'][-10:]:
        table.append([
            e["timestamp_utc"][:19],
            e["report_type"],
            f"{e['latitude']:.4f}, {e['longitude']:.4f}"
        ])
    click.echo(tabulate(table, headers=["Time", "Type", "Location"]))

    db.close()

# === Export Commands ===

@cli.command()
@click.option("--format", "fmt", type=click.Choice(["csv", "geojson"]), default="csv")
@click.option("-o", "--output", help="Output file path")
def export(fmt, output):
    """Export events to CSV or GeoJSON."""
    import json
    import csv

    db = get_db()
    rows = db.execute("SELECT * FROM events ORDER BY timestamp_ms").fetchall()

    if not rows:
        click.echo("No events to export")
        return

    if not output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"exports/events_{timestamp}.{fmt}"

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    if fmt == "csv":
        with open(output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow(tuple(row))

    elif fmt == "geojson":
        features = []
        for row in rows:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]]
                },
                "properties": {
                    "username": row["username"],
                    "timestamp": row["timestamp_utc"],
                    "type": row["report_type"],
                    "subtype": row["subtype"]
                }
            })

        geojson = {"type": "FeatureCollection", "features": features}
        with open(output, "w") as f:
            json.dump(geojson, f)

    click.echo(f"Exported {len(rows)} events to {output}")
    db.close()

# === Config Commands ===

@cli.command()
@click.option("--interval", type=int, help="Set polling interval in seconds")
def config(interval):
    """Show or modify configuration."""
    cfg = load_config()

    if interval:
        cfg["polling_interval_seconds"] = interval
        with open("config.yaml", "w") as f:
            yaml.dump(cfg, f, default_flow_style=False)
        click.echo(f"Polling interval set to {interval} seconds")
    else:
        click.echo(yaml.dump(cfg, default_flow_style=False))


# === Collection Stats Commands ===

@cli.command()
@click.option("-n", "--days", default=7, help="Number of days to show")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all regional databases")
def daily(days, show_all):
    """Show daily collection statistics."""
    if show_all:
        # Aggregate from all databases
        daily_stats = {}

        for region, db in get_all_dbs():
            try:
                stats = db.get_daily_stats(days)
                for s in stats:
                    date = s["date"]
                    if date not in daily_stats:
                        daily_stats[date] = {"events": 0, "users": set(), "requests": 0, "errors": 0}
                    daily_stats[date]["events"] += s.get("events_collected", 0)
                    daily_stats[date]["requests"] += s.get("api_requests", 0)
                    daily_stats[date]["errors"] += s.get("api_errors", 0)

                # Get unique users per day
                for date in daily_stats.keys():
                    user_rows = db.execute("""
                        SELECT DISTINCT username FROM events
                        WHERE DATE(timestamp_utc) = ?
                    """, (date,)).fetchall()
                    for u in user_rows:
                        daily_stats[date]["users"].add(u["username"])

                db.close()
            except Exception:
                pass

        if not daily_stats:
            click.echo("No daily stats recorded yet")
            return

        table = []
        for date in sorted(daily_stats.keys(), reverse=True):
            s = daily_stats[date]
            table.append([
                date,
                f"{s['events']:,}",
                f"{len(s['users']):,}",
                f"{s['requests']:,}",
                f"{s['errors']:,}",
            ])

        click.echo("=== Worldwide Daily Statistics ===")
        click.echo(tabulate(table, headers=["Date", "Events", "Users", "Requests", "Errors"]))
    else:
        db = get_db()
        stats = db.get_daily_stats(days)

        if not stats:
            click.echo("No daily stats recorded yet")
            click.echo("Tip: Use 'waze daily --all' to see all regional databases")
            return

        table = []
        for s in stats:
            table.append([
                s["date"],
                f"{s['events_collected']:,}",
                f"{s['unique_users']:,}",
                f"{s['api_requests']:,}",
                f"{s['api_errors']:,}",
            ])

        click.echo(tabulate(table, headers=["Date", "Events", "Users", "Requests", "Errors"]))
        db.close()


@cli.command()
@click.option("--port", "-p", default=5000, help="Port to run the web UI on (default: 5000)")
def web(port):
    """Start the web visualization UI only (no collection).

    Use this to view collected data without running the collector.
    """
    click.echo(f"Starting web UI at http://localhost:{port}")
    click.echo("Press Ctrl+C to stop")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'web'))
    from web.app import app
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


@cli.command()
def summary():
    """Show overall collection summary (all regions)."""
    total_events = 0
    all_users = set()
    days_collected = set()
    grid_cells = set()
    first_event = None
    last_event = None

    dbs = get_all_dbs()
    if not dbs:
        click.echo("No data collected yet")
        return

    region_stats = []

    for region, db in dbs:
        try:
            s = db.get_collection_summary()
            if s and s.get('total_events'):
                total_events += s['total_events']

                # Get unique users
                user_rows = db.execute("SELECT DISTINCT username FROM events").fetchall()
                for u in user_rows:
                    all_users.add(u["username"])

                # Track dates
                date_rows = db.execute("""
                    SELECT DISTINCT DATE(timestamp_utc) as dt FROM events
                """).fetchall()
                for d in date_rows:
                    if d["dt"]:
                        days_collected.add(d["dt"])

                # Track grid cells
                cell_rows = db.execute("""
                    SELECT DISTINCT grid_cell FROM events WHERE grid_cell IS NOT NULL
                """).fetchall()
                for c in cell_rows:
                    grid_cells.add(c["grid_cell"])

                if s['first_event']:
                    if first_event is None or s['first_event'] < first_event:
                        first_event = s['first_event']
                if s['last_event']:
                    if last_event is None or s['last_event'] > last_event:
                        last_event = s['last_event']

                region_stats.append((region, s['total_events'], s['unique_users']))

            db.close()
        except Exception as e:
            click.echo(f"Error reading {region}: {e}")

    if total_events == 0:
        click.echo("No data collected yet")
        return

    click.echo("=== Worldwide Collection Summary ===")
    click.echo(f"Total events:    {total_events:,}")
    click.echo(f"Unique users:    {len(all_users):,}")
    click.echo(f"Days collected:  {len(days_collected)}")
    click.echo(f"Grid cells used: {len(grid_cells)}")
    click.echo(f"First event:     {first_event[:19] if first_event else 'N/A'}")
    click.echo(f"Last event:      {last_event[:19] if last_event else 'N/A'}")

    if len(days_collected) > 0:
        avg = total_events / len(days_collected)
        click.echo(f"Avg events/day:  {avg:.1f}")

    click.echo("\n=== By Region ===")
    for region, events, users in sorted(region_stats, key=lambda x: -x[1]):
        pct = events / total_events * 100 if total_events else 0
        click.echo(f"  {region.upper():10} {events:>10,} events  {users:>8,} users  ({pct:.1f}%)")


@cli.command()
@click.option("-n", "--limit", default=20, help="Number of users to show")
def tracked(limit):
    """Show tracked users with most events."""
    db = get_db()
    users = db.get_tracked_users(limit)

    if not users:
        click.echo("No tracked users yet")
        return

    table = []
    for u in users:
        table.append([
            u["username"][:25],
            f"{u['event_count']:,}",
            u["first_seen"][:10],
            u["last_seen"][:10],
        ])

    click.echo(tabulate(table, headers=["Username", "Events", "First Seen", "Last Seen"]))
    db.close()


if __name__ == "__main__":
    cli()
