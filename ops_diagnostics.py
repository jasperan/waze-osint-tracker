"""Runtime diagnostics and local operator helpers."""

from __future__ import annotations

import json
import shutil
import socket
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

DEFAULT_STATUS_STALE_SECONDS = 600


def detect_config_path(project_root: str | Path) -> str:
    """Return the active config path using the repo's precedence order."""
    root = Path(project_root)
    for name in ("config_oracle.yaml", "config.yaml"):
        path = root / name
        if path.exists():
            return str(path)
    return str(root / "config.yaml")


def read_status_file(
    path: str | Path,
    *,
    now: datetime | None = None,
    stale_seconds: int = DEFAULT_STATUS_STALE_SECONDS,
) -> dict[str, Any]:
    """Read collector status from disk and mark stale/invalid payloads."""
    status_path = Path(path)
    if not status_path.exists():
        return {"status": "unknown", "message": "No collector status available"}

    try:
        status = json.loads(status_path.read_text())
    except Exception:
        return {"status": "unknown", "message": "Collector status file is unreadable"}

    timestamp = status.get("timestamp")
    if not timestamp:
        status["status"] = "stale"
        status["stale"] = True
        status["message"] = "Collector status timestamp is missing"
        return status

    current_time = now or datetime.now(timezone.utc)
    try:
        updated_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        status["status"] = "stale"
        status["stale"] = True
        status["message"] = "Collector status timestamp is invalid"
        return status

    age = max(0.0, (current_time - updated_at).total_seconds())
    status["age_seconds"] = round(age, 1)
    if age > stale_seconds:
        status["status"] = "stale"
        status["stale"] = True
        status["message"] = "Collector status file is stale"
    else:
        status.setdefault("stale", False)
    return status


def port_is_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True when a local TCP port can be bound."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                return False
    except OSError:
        return False
    return True


def find_available_port(
    preferred_port: int = 5000,
    *,
    host: str = "127.0.0.1",
    search_window: int = 100,
) -> int:
    """Return the first bindable port at or above the preferred port."""
    for candidate in range(preferred_port, preferred_port + search_window):
        if port_is_available(candidate, host=host):
            return candidate

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])
    except OSError:
        return preferred_port


def choose_web_port(requested_port: int, auto_port: bool) -> int:
    """Resolve the effective web port for CLI commands."""
    if auto_port:
        return find_available_port(preferred_port=requested_port)
    return requested_port


def api_probe(base_url: str, timeout: float = 2.0) -> dict[str, Any]:
    """Probe a local or remote API base for basic health."""
    result: dict[str, Any] = {
        "base_url": base_url.rstrip("/"),
        "reachable": False,
        "stats_ok": False,
        "status_ok": False,
    }

    try:
        stats_resp = requests.get(result["base_url"] + "/api/stats", timeout=timeout)
        result["stats_status_code"] = stats_resp.status_code
        result["stats_ok"] = stats_resp.ok
        if stats_resp.ok:
            try:
                result["stats"] = stats_resp.json()
            except ValueError:
                result["stats"] = None

        status_resp = requests.get(result["base_url"] + "/api/status", timeout=timeout)
        result["status_status_code"] = status_resp.status_code
        result["status_ok"] = status_resp.ok
        if status_resp.ok:
            try:
                result["status"] = status_resp.json()
            except ValueError:
                result["status"] = None

        result["reachable"] = bool(result["stats_ok"] or result["status_ok"])
    except requests.RequestException as exc:
        result["error"] = str(exc)

    return result


def parse_port_from_api_url(api_url: str) -> int | None:
    """Extract a port from an API base URL."""
    parsed = urlparse(api_url)
    return parsed.port


def _sqlite_summary(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return info

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS events, MAX(timestamp_utc) AS last_event FROM events"
            ).fetchone()
            info["events"] = int(row[0]) if row and row[0] is not None else 0
            info["last_event"] = row[1] if row else None
        finally:
            conn.close()
    except Exception as exc:
        info["error"] = str(exc)

    return info


def build_doctor_report(
    config: dict[str, Any] | None = None,
    *,
    project_root: str | Path | None = None,
    port: int = 5000,
    api_url: str | None = None,
    live_check: bool = True,
) -> dict[str, Any]:
    """Build a full environment/runtime diagnostics report."""
    from database_factory import check_oracle_connection
    from utils import load_config

    cfg = config or load_config()
    root = Path(project_root or Path(__file__).resolve().parent)
    config_path = detect_config_path(root)
    requested_backend = cfg.get("database_type", "oracle")
    resolved_port = find_available_port(preferred_port=port)

    sqlite_paths = []
    default_path = Path(cfg.get("database_path", root / "data" / "waze_madrid.db"))
    sqlite_paths.append(default_path)
    data_dir = root / "data"
    if data_dir.exists():
        sqlite_paths.extend(sorted(data_dir.glob("waze_*.db")))

    unique_paths: list[Path] = []
    seen = set()
    for path in sqlite_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)

    sqlite_dbs = [_sqlite_summary(path) for path in unique_paths]

    oracle_ok, oracle_message = check_oracle_connection(cfg)
    status = read_status_file(root / "data" / "collector_status.json")

    effective_api = api_url or f"http://localhost:{port}"
    if live_check:
        api = api_probe(effective_api)
    else:
        api = {"base_url": effective_api, "reachable": False}

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": config_path,
        "backend": {
            "requested": requested_backend,
            "sqlite_fallback": bool(cfg.get("sqlite_fallback", False)),
            "oracle": {"ok": oracle_ok, "message": oracle_message},
        },
        "status_file": status,
        "port": {
            "requested": port,
            "available": port_is_available(port),
            "recommended": resolved_port,
        },
        "api": api,
        "sqlite": {
            "default_path": str(default_path),
            "databases": sqlite_dbs,
        },
        "tui": {
            "go_installed": shutil.which("go") is not None,
            "binary_present": (root / "tui" / "waze-tui").exists(),
        },
    }

    next_steps: list[str] = []
    if not oracle_ok and cfg.get("sqlite_fallback", False):
        next_steps.append("Oracle is unavailable, but SQLite fallback is enabled.")
    if not report["port"]["available"]:
        next_steps.append(
            f"Port {port} is busy. Use --auto-port or switch to {report['port']['recommended']}."
        )
    if status.get("status") == "stale":
        next_steps.append(
            "Collector status is stale. Restart the collector if you want live updates."
        )
    if live_check and not api.get("reachable", False):
        next_steps.append(
            f"API is not reachable at {effective_api}. "
            f"Start it with 'waze web -p {report['port']['recommended']}'."
        )
    if not report["tui"]["go_installed"]:
        next_steps.append("Install Go 1.24+ to build and run the TUI.")
    report["next_steps"] = next_steps

    return report


def render_doctor_report(report: dict[str, Any]) -> str:
    """Render the doctor report as human-readable text."""
    lines = [
        "Waze Doctor",
        "===========",
        f"Config: {report['config_path']}",
        (
            f"Backend: {report['backend']['requested']} "
            f"(sqlite_fallback={report['backend']['sqlite_fallback']})"
        ),
        (
            "Oracle: "
            + ("OK" if report["backend"]["oracle"]["ok"] else "UNAVAILABLE")
            + f" - {report['backend']['oracle']['message']}"
        ),
        (
            f"Port {report['port']['requested']}: "
            f"{'free' if report['port']['available'] else 'busy'} "
            f"(recommended {report['port']['recommended']})"
        ),
        f"Collector status: {report['status_file'].get('status', 'unknown')}",
    ]
    if report["api"].get("base_url"):
        lines.append(
            f"API: {report['api']['base_url']} "
            f"({'reachable' if report['api'].get('reachable') else 'unreachable'})"
        )

    lines.extend(["", "SQLite Databases"])
    for info in report["sqlite"]["databases"]:
        suffix = f"{info.get('events', 0)} events"
        if info.get("last_event"):
            suffix += f", last={info['last_event']}"
        if info.get("error"):
            suffix += f", error={info['error']}"
        lines.append(f"- {info['path']}: {'present' if info['exists'] else 'missing'} ({suffix})")

    if report["next_steps"]:
        lines.extend(["", "Next steps"])
        for step in report["next_steps"]:
            lines.append(f"- {step}")

    return "\n".join(lines)
