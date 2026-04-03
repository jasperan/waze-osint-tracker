"""README-style smoke walkthrough helpers."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from briefing import open_briefing_dbs
from repo_hygiene import audit_git_generated_markdown
from utils import load_config

MIN_SAMPLE_USER_EVENTS = 1
MAX_SAMPLE_USER_EVENTS = 200


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str | None, limit: int = 1600) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def _python_cli_command(project_root: Path, *args: str) -> list[str]:
    return [os.environ.get("PYTHON", sys.executable), str(project_root / "cli.py"), *args]


def _pick_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_command_step(
    name: str,
    command: list[str],
    *,
    cwd: str | Path,
    timeout: float = 30,
    env: dict[str, str] | None = None,
    allow_exit_codes: set[int] | None = None,
    note_for_exit_codes: dict[int, str] | None = None,
    timeout_is_success: bool = False,
    timeout_note: str | None = None,
) -> dict[str, Any]:
    """Run a subprocess and return a structured step record."""
    started = time.monotonic()
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        duration = round(time.monotonic() - started, 2)
        allowed = allow_exit_codes or {0}
        ok = process.returncode in allowed
        step = {
            "name": name,
            "kind": "command",
            "ok": ok,
            "returncode": process.returncode,
            "command": " ".join(command),
            "duration_seconds": duration,
            "stdout": _truncate(process.stdout),
            "stderr": _truncate(process.stderr),
        }
        if note_for_exit_codes and process.returncode in note_for_exit_codes:
            step["note"] = note_for_exit_codes[process.returncode]
        if not ok and process.stderr:
            step["error"] = _truncate(process.stderr)
        return step
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "kind": "command",
            "ok": timeout_is_success,
            "command": " ".join(command),
            "duration_seconds": round(time.monotonic() - started, 2),
            "error": None if timeout_is_success else f"Timed out after {timeout}s",
            "note": timeout_note if timeout_is_success else None,
            "stdout": _truncate(_coerce_output(exc.stdout)),
            "stderr": _truncate(_coerce_output(exc.stderr)),
        }


def record_http_step(
    name: str, url: str, *, timeout: float = 20, attempts: int = 3
) -> dict[str, Any]:
    """Fetch a JSON endpoint and return a structured step record."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=timeout)
            payload = response.json()
            if isinstance(payload, dict):
                keys = sorted(payload.keys())[:8]
            else:
                keys = [type(payload).__name__]
            step = {
                "name": name,
                "kind": "http",
                "ok": response.ok,
                "url": url,
                "status_code": response.status_code,
                "response_keys": keys,
            }
            if not response.ok:
                step["error"] = f"HTTP {response.status_code}"
            return step
        except Exception as exc:  # pragma: no cover - exercised in live smoke only
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(1)
    return {
        "name": name,
        "kind": "http",
        "ok": False,
        "url": url,
        "error": last_error or "request failed",
    }


def wait_for_json(url: str, *, timeout: float = 30, predicate=None) -> dict[str, Any]:
    """Poll an HTTP endpoint until it returns JSON satisfying *predicate*."""
    deadline = time.monotonic() + timeout
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=2)
            data = response.json()
            if response.ok and (predicate is None or predicate(data)):
                return {"ok": True, "status_code": response.status_code, "data": data}
            last_error = f"HTTP {response.status_code}"
        except Exception as exc:  # pragma: no cover - exercised in live smoke only
            last_error = str(exc)
        time.sleep(1)
    return {"ok": False, "error": last_error}


def _finalize_process(process: subprocess.Popen[str], *, timeout: float = 5) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive path
        process.kill()
        stdout, stderr = process.communicate(timeout=timeout)
    return _truncate(stdout), _truncate(stderr)


def launch_web_process(
    project_root: Path,
    env: dict[str, str],
    requested_port: int,
    *,
    auto_port: bool,
    max_attempts: int = 5,
    startup_timeout: float = 15,
) -> dict[str, Any]:
    """Start the local web UI on a collision-free port and verify readiness."""
    candidate = requested_port
    attempts: list[dict[str, Any]] = []

    total_attempts = max_attempts if auto_port else 1
    for attempt in range(total_attempts):
        if auto_port and attempt > 0:
            candidate = _pick_ephemeral_port()
        process = subprocess.Popen(
            _python_cli_command(project_root, "web", "--port", str(candidate)),
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        time.sleep(0.5)
        if process.poll() is not None:
            stdout, stderr = _finalize_process(process, timeout=1)
            attempts.append(
                {
                    "port": candidate,
                    "stdout": stdout,
                    "stderr": stderr,
                    "error": "web process exited before startup completed",
                }
            )
            continue

        status_result = wait_for_json(
            f"http://127.0.0.1:{candidate}/api/status",
            timeout=startup_timeout,
        )
        if status_result.get("ok") and process.poll() is None:
            return {
                "ok": True,
                "process": process,
                "port": candidate,
                "status_result": status_result,
                "attempts": attempts,
            }

        process.terminate()
        stdout, stderr = _finalize_process(process)
        attempts.append(
            {
                "port": candidate,
                "stdout": stdout,
                "stderr": stderr,
                "error": status_result.get("error") or "web UI never became ready",
            }
        )

    return {
        "ok": False,
        "port": candidate,
        "attempts": attempts,
        "error": "Failed to launch a ready web UI after multiple port attempts.",
    }


def select_sample_user(dbs: list[tuple[str, Any]]) -> dict[str, Any] | None:
    """Choose a recent non-anonymous user from the available databases."""
    best: dict[str, str | int] | None = None
    for region, db in dbs:
        recent_rows = db.execute(
            "SELECT username, timestamp_ms FROM events "
            "WHERE username IS NOT NULL AND username != ? "
            "ORDER BY timestamp_ms DESC LIMIT ?",
            ("anonymous", 100),
        ).fetchall()

        recent_usernames: list[str] = []
        seen: set[str] = set()
        for row in recent_rows:
            username = row["username"]
            if username in seen:
                continue
            seen.add(username)
            recent_usernames.append(username)
            if len(recent_usernames) >= 10:
                break

        fallback_candidate: dict[str, str | int] | None = None
        for username in recent_usernames:
            stats = db.execute(
                "SELECT COUNT(*) AS event_count, MAX(timestamp_ms) AS last_seen_ms "
                "FROM events WHERE username = ?",
                (username,),
            ).fetchone()
            candidate = {
                "username": username,
                "event_count": int(stats["event_count"]),
                "timestamp_ms": int(stats["last_seen_ms"]),
                "region": region,
            }
            if fallback_candidate is None or (
                int(candidate["event_count"]),
                -int(candidate["timestamp_ms"]),
            ) < (
                int(fallback_candidate["event_count"]),
                -int(fallback_candidate["timestamp_ms"]),
            ):
                fallback_candidate = candidate
            if MIN_SAMPLE_USER_EVENTS <= candidate["event_count"] <= MAX_SAMPLE_USER_EVENTS:
                candidate["selection_mode"] = "bounded"
                if best is None or (
                    int(candidate["timestamp_ms"]),
                    -int(candidate["event_count"]),
                ) > (
                    int(best["timestamp_ms"]),
                    -int(best["event_count"]),
                ):
                    best = candidate
                break
        else:
            if fallback_candidate is not None:
                fallback_candidate["selection_mode"] = "fallback"
                if best is None or (
                    int(fallback_candidate["timestamp_ms"]),
                    -int(fallback_candidate["event_count"]),
                ) > (
                    int(best["timestamp_ms"]),
                    -int(best["event_count"]),
                ):
                    best = fallback_candidate
    return best


def build_smoke_report(
    *,
    project_root: str | Path,
    port: int = 5000,
    auto_port: bool = False,
    include_tui: bool = True,
    api_only: bool = False,
) -> dict[str, Any]:
    """Run a README-style smoke walkthrough and return a structured report."""
    root = Path(project_root).resolve()
    resolved_port = _pick_ephemeral_port() if auto_port else port
    base_url = f"http://127.0.0.1:{resolved_port}"
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    report: dict[str, Any] = {
        "generated_at": _iso_now(),
        "project_root": str(root),
        "port": {"requested": port, "resolved": resolved_port},
        "steps": [],
        "sample_user": None,
        "git_hygiene": audit_git_generated_markdown(root),
    }

    dbs = open_briefing_dbs(root, load_config())
    try:
        sample_user = select_sample_user(dbs)
    finally:
        for _, db in dbs:
            try:
                db.close()
            except Exception:
                pass
    report["sample_user"] = sample_user
    if sample_user:
        selection_mode = str(sample_user.get("selection_mode", "bounded"))
        note = (
            "Using a bounded recent sample user for deep walkthrough coverage."
            if selection_mode == "bounded"
            else (
                "No bounded recent sample user found; using the lightest recent fallback candidate."
            )
        )
        report["steps"].append(
            {
                "name": "sample-user-selection",
                "kind": "analysis",
                "ok": True,
                "note": note,
                "username": sample_user["username"],
                "event_count": sample_user.get("event_count"),
                "selection_mode": selection_mode,
            }
        )
    else:
        report["steps"].append(
            {
                "name": "sample-user-selection",
                "kind": "analysis",
                "ok": False,
                "error": "No non-anonymous sample user available for deep walkthrough coverage.",
            }
        )

    report["steps"].append(
        run_command_step(
            "cli-help",
            _python_cli_command(root, "--help"),
            cwd=root,
            timeout=15,
            env=env,
        )
    )
    report["steps"].append(
        run_command_step(
            "doctor-json",
            _python_cli_command(
                root,
                "doctor",
                "--port",
                str(resolved_port),
                "--api-url",
                base_url,
                "--no-live-check",
                "--format",
                "json",
            ),
            cwd=root,
            timeout=30,
            env=env,
        )
    )
    report["steps"].append(
        run_command_step(
            "briefing-json",
            _python_cli_command(root, "briefing", "--format", "json", "--hours", "24"),
            cwd=root,
            timeout=45,
            env=env,
        )
    )
    report["steps"].append(
        run_command_step(
            "status",
            _python_cli_command(root, "status"),
            cwd=root,
            timeout=30,
            env=env,
        )
    )
    report["steps"].append(
        run_command_step(
            "recent",
            _python_cli_command(root, "recent", "-n", "3"),
            cwd=root,
            timeout=30,
            env=env,
        )
    )
    report["steps"].append(
        run_command_step(
            "users",
            _python_cli_command(root, "users", "-n", "3"),
            cwd=root,
            timeout=30,
            env=env,
        )
    )

    if sample_user:
        username = sample_user["username"]
        report["steps"].append(
            run_command_step(
                "profile-sample-user",
                _python_cli_command(root, "profile", username),
                cwd=root,
                timeout=30,
                env=env,
            )
        )
        report["steps"].append(
            run_command_step(
                "report-sample-user-json",
                _python_cli_command(root, "report", username, "--format", "json"),
                cwd=root,
                timeout=45,
                env=env,
            )
        )

    launch = launch_web_process(root, env, resolved_port, auto_port=auto_port)
    report["web_launch_attempts"] = launch.get("attempts", [])
    if not launch.get("ok"):
        report["steps"].append(
            {
                "name": "web-launch",
                "kind": "command",
                "ok": False,
                "command": f"python cli.py web --port {resolved_port}",
                "error": launch.get("error"),
            }
        )
    else:
        resolved_port = int(launch["port"])
        report["port"]["resolved"] = resolved_port
        base_url = f"http://127.0.0.1:{resolved_port}"
        web_process = launch["process"]
        report["steps"].append(
            {
                "name": "web-launch",
                "kind": "command",
                "ok": True,
                "command": f"python cli.py web --port {resolved_port}",
            }
        )
        try:
            status_result = launch["status_result"]
            report["steps"].append(
                {
                    "name": "api-status",
                    "kind": "http",
                    "ok": status_result.get("ok", False),
                    "url": f"{base_url}/api/status",
                    "status_code": status_result.get("status_code"),
                    "response_keys": sorted(status_result.get("data", {}).keys())[:8],
                    "error": status_result.get("error"),
                }
            )

            stats_result = wait_for_json(
                f"{base_url}/api/stats",
                timeout=20,
                predicate=lambda payload: isinstance(payload, dict) and "total_events" in payload,
            )
            stats_data = stats_result.get("data", {})
            report["steps"].append(
                {
                    "name": "api-stats",
                    "kind": "http",
                    "ok": stats_result.get("ok", False),
                    "url": f"{base_url}/api/stats",
                    "status_code": stats_result.get("status_code"),
                    "response_keys": sorted(stats_data.keys())[:8],
                    "note": (
                        "Stats warmup still in progress; endpoint returned placeholder data."
                        if stats_data.get("message")
                        else None
                    ),
                    "error": stats_result.get("error"),
                }
            )

            for name, url in [
                ("api-briefing", f"{base_url}/api/briefing"),
                ("api-events", f"{base_url}/api/events?limit=3"),
            ]:
                report["steps"].append(record_http_step(name, url))

            if sample_user:
                username = quote(sample_user["username"], safe="")
                for name, url in [
                    ("api-user", f"{base_url}/api/user/{username}"),
                    ("api-privacy-score", f"{base_url}/api/privacy-score/{username}"),
                ]:
                    report["steps"].append(record_http_step(name, url))
        finally:
            web_process.terminate()
            _, stderr = _finalize_process(web_process, timeout=10)
            report["web_process_stderr"] = stderr

    if include_tui and not api_only:
        report["steps"].append(
            run_command_step(
                "tui-build",
                ["make", "build"],
                cwd=root / "tui",
                timeout=120,
                env=env,
            )
        )
        report["steps"].append(
            run_command_step(
                "tui-launch",
                ["./waze-tui", "--api", base_url],
                cwd=root / "tui",
                timeout=3,
                env=env,
                timeout_is_success=True,
                timeout_note="Timed out intentionally after bounded launch smoke.",
            )
        )
        tui_step = report["steps"][-1]
        if not tui_step.get("ok") and "could not open a new TTY" in tui_step.get("stderr", ""):
            tui_step["ok"] = True
            tui_step["error"] = None
            tui_step["note"] = (
                "TUI launch hit a headless /dev/tty limitation; binary built successfully."
            )

    report["ok"] = all(step.get("ok", False) for step in report["steps"]) and report[
        "git_hygiene"
    ].get("clean", True)
    report["summary"] = {
        "passed": sum(1 for step in report["steps"] if step.get("ok")),
        "failed": sum(1 for step in report["steps"] if not step.get("ok")),
        "git_hygiene_clean": report["git_hygiene"].get("clean", True),
    }
    report["counts"] = {
        "passed": report["summary"]["passed"],
        "failed": report["summary"]["failed"],
    }
    report["overall_status"] = "pass" if report["ok"] else "fail"
    return report


def render_smoke_report(report: dict[str, Any]) -> str:
    """Render a human-readable smoke report."""
    lines = [
        "Waze Smoke Walkthrough",
        "======================",
        f"Generated: {report['generated_at']}",
        f"Project root: {report['project_root']}",
        f"Resolved port: {report['port']['resolved']}",
        f"Overall: {'PASS' if report.get('ok') else 'FAIL'}",
        "",
        "Steps:",
    ]
    for step in report["steps"]:
        status = "PASS" if step.get("ok") else "FAIL"
        extra = step.get("note") or step.get("error") or ""
        lines.append(f"- [{status}] {step['name']}: {extra}".rstrip())

    hygiene = report.get("git_hygiene", {})
    lines.extend(["", "Git hygiene:"])
    if hygiene.get("available"):
        lines.append(f"- clean: {hygiene.get('clean', False)}")
        if hygiene.get("tracked"):
            lines.append(f"- tracked suspicious markdown: {', '.join(hygiene['tracked'])}")
        if hygiene.get("history"):
            lines.append(f"- history suspicious markdown: {', '.join(hygiene['history'])}")
    else:
        lines.append("- git metadata unavailable")

    if report.get("sample_user"):
        lines.extend(["", f"Sample user: {report['sample_user']['username']}"])
    return "\n".join(lines)


def render_smoke_report_markdown(report: dict[str, Any]) -> str:
    """Render a markdown smoke report."""
    lines = [
        "# Waze Smoke Walkthrough",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Project root: `{report['project_root']}`",
        f"- Resolved port: `{report['port']['resolved']}`",
        f"- Overall: **{'PASS' if report.get('ok') else 'FAIL'}**",
        "",
        "| Step | Kind | Status | Notes |",
        "|---|---|---|---|",
    ]
    for step in report["steps"]:
        note = step.get("note") or step.get("error") or ""
        status = "PASS" if step.get("ok") else "FAIL"
        lines.append(f"| `{step['name']}` | `{step['kind']}` | `{status}` | {note} |")

    hygiene = report.get("git_hygiene", {})
    lines.extend(["", "## Git hygiene"])
    if hygiene.get("available"):
        lines.append(f"- Clean: `{hygiene.get('clean', False)}`")
        if hygiene.get("tracked"):
            lines.append(f"- Tracked suspicious markdown: `{', '.join(hygiene['tracked'])}`")
        if hygiene.get("history"):
            lines.append(f"- History suspicious markdown: `{', '.join(hygiene['history'])}`")
    else:
        lines.append("- Git metadata unavailable")

    if report.get("sample_user"):
        lines.extend(["", f"Sample user: `{report['sample_user']['username']}`"])
    return "\n".join(lines)


def save_smoke_report(report: dict[str, Any], destination: str | Path, fmt: str = "json") -> Path:
    """Persist a smoke report to disk."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(report, indent=2))
    elif fmt == "markdown":
        path.write_text(render_smoke_report_markdown(report))
    else:
        path.write_text(render_smoke_report(report))
    return path
