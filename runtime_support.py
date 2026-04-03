"""Shared runtime helpers for diagnostics, port handling, and status freshness."""

from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

DEFAULT_STALE_SECONDS = 600


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_status_file(
    status_file: str | Path,
    *,
    now: datetime | None = None,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> dict[str, Any]:
    """Load and annotate the collector status file."""
    path = Path(status_file)
    if not path.exists():
        return {"status": "unknown", "message": "No collector status available"}

    try:
        status = json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - defensive path
        return {
            "status": "invalid",
            "stale": True,
            "message": f"Failed to read collector status file: {exc}",
        }

    if not isinstance(status, dict):
        return {
            "status": "invalid",
            "stale": True,
            "message": "Collector status file did not contain an object",
        }

    timestamp = status.get("timestamp")
    if not timestamp:
        return status

    try:
        updated_at = _parse_timestamp(str(timestamp))
    except ValueError:
        annotated = dict(status)
        annotated["status"] = "stale"
        annotated["stale"] = True
        annotated["message"] = "Collector status timestamp is invalid"
        return annotated

    now = now or datetime.now(timezone.utc)
    age_seconds = max((now - updated_at).total_seconds(), 0.0)

    annotated = dict(status)
    annotated["age_seconds"] = round(age_seconds, 1)
    if age_seconds > stale_seconds:
        annotated["status"] = "stale"
        annotated["stale"] = True
        annotated["message"] = "Collector status file is stale"
    else:
        annotated.setdefault("stale", False)
    return annotated


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True when *host:port* can be bound locally."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(
    preferred: int = 5000,
    *,
    host: str = "127.0.0.1",
    max_tries: int = 100,
) -> int:
    """Find the first available port starting at *preferred*."""
    for candidate in range(preferred, preferred + max_tries):
        if is_port_available(candidate, host=host):
            return candidate
    raise RuntimeError(f"No free port found in range {preferred}-{preferred + max_tries - 1}")


def probe_api(base_url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    """Probe a local API for basic reachability and health."""
    base = base_url.rstrip("/")
    result: dict[str, Any] = {
        "base_url": base,
        "reachable": False,
    }

    try:
        stats_resp = requests.get(f"{base}/api/stats", timeout=timeout)
        result["stats_status"] = stats_resp.status_code
        if stats_resp.ok:
            result["stats"] = stats_resp.json()

        status_resp = requests.get(f"{base}/api/status", timeout=timeout)
        result["collector_status_code"] = status_resp.status_code
        if status_resp.ok:
            result["collector_status"] = status_resp.json()

        result["reachable"] = stats_resp.ok and status_resp.ok
    except Exception as exc:
        result["error"] = str(exc)

    return result
