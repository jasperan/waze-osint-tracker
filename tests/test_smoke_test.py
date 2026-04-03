from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cli import cli
from smoke_test import (
    build_smoke_report,
    render_smoke_report,
    render_smoke_report_markdown,
    select_sample_user,
)


def test_render_smoke_report_formats_counts():
    report = {
        "generated_at": "2026-04-03T00:00:00+00:00",
        "project_root": "/tmp/project",
        "port": {"requested": 5000, "resolved": 5001},
        "ok": True,
        "steps": [{"name": "cli-help", "kind": "command", "ok": True}],
        "git_hygiene": {"available": True, "clean": True},
        "sample_user": {"username": "alice"},
    }

    text = render_smoke_report(report)
    markdown = render_smoke_report_markdown(report)

    assert "Waze Smoke Walkthrough" in text
    assert "Overall: PASS" in text
    assert "alice" in markdown


def test_build_smoke_report_aggregates_steps(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("smoke_test.audit_git_generated_markdown", lambda root: {"clean": True})
    monkeypatch.setattr("smoke_test.open_briefing_dbs", lambda root, config=None: [])
    monkeypatch.setattr("smoke_test.load_config", lambda: {})
    monkeypatch.setattr(
        "smoke_test.select_sample_user",
        lambda dbs: {
            "username": "sample",
            "event_count": 3,
            "timestamp_ms": 1,
            "region": "test",
            "selection_mode": "bounded",
        },
    )
    monkeypatch.setattr(
        "smoke_test.run_command_step",
        lambda name, command, **kwargs: {"name": name, "kind": "command", "ok": True},
    )
    monkeypatch.setattr(
        "smoke_test.wait_for_json",
        lambda url, **kwargs: {
            "ok": True,
            "status_code": 200,
            "data": {"total_events": 1, "message": "Computing stats..."},
        },
    )
    monkeypatch.setattr(
        "smoke_test.record_http_step",
        lambda name, url, **kwargs: {"name": name, "kind": "http", "ok": True},
    )

    class DummyProcess:
        def terminate(self):
            return None

        def communicate(self, timeout=None):
            return ("", "")

    monkeypatch.setattr(
        "smoke_test.launch_web_process",
        lambda *args, **kwargs: {
            "ok": True,
            "process": DummyProcess(),
            "port": 5001,
            "status_result": {"ok": True, "status_code": 200, "data": {"status": "idle"}},
            "attempts": [],
        },
    )

    report = build_smoke_report(
        project_root=tmp_path,
        port=5000,
        auto_port=True,
        include_tui=False,
    )

    assert report["ok"] is True
    assert report["overall_status"] == "pass"
    assert report["counts"]["failed"] == 0
    selection_step = next(
        step for step in report["steps"] if step["name"] == "sample-user-selection"
    )
    assert selection_step["selection_mode"] == "bounded"
    assert any(step["name"] == "api-status" for step in report["steps"])
    stats_step = next(step for step in report["steps"] if step["name"] == "api-stats")
    assert "warmup" in stats_step["note"].lower()


def test_select_sample_user_prefers_recent_bounded_candidate():
    class FakeResult:
        def __init__(self, rows=None, row=None):
            self._rows = rows or []
            self._row = row

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._row

    class FakeDB:
        def execute(self, query, params):
            if "ORDER BY timestamp_ms DESC" in query:
                return FakeResult(
                    rows=[
                        {"username": "bounded", "timestamp_ms": 200},
                        {"username": "fallback", "timestamp_ms": 150},
                    ]
                )
            username = params[0]
            if username == "bounded":
                return FakeResult(row={"event_count": 12, "last_seen_ms": 200})
            return FakeResult(row={"event_count": 900, "last_seen_ms": 150})

    dbs = [("europe", FakeDB())]

    user = select_sample_user(dbs)

    assert user is not None
    assert user["username"] == "bounded"
    assert user["event_count"] == 12
    assert user["timestamp_ms"] == 200
    assert user["selection_mode"] == "bounded"


def test_select_sample_user_falls_back_when_no_bounded_candidate():
    class FakeResult:
        def __init__(self, rows=None, row=None):
            self._rows = rows or []
            self._row = row

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._row

    class FakeDB:
        def execute(self, query, params):
            if "ORDER BY timestamp_ms DESC" in query:
                return FakeResult(
                    rows=[
                        {"username": "heavy_recent", "timestamp_ms": 300},
                        {"username": "lighter_older", "timestamp_ms": 200},
                    ]
                )
            username = params[0]
            if username == "heavy_recent":
                return FakeResult(row={"event_count": 900, "last_seen_ms": 300})
            return FakeResult(row={"event_count": 700, "last_seen_ms": 200})

    user = select_sample_user([("europe", FakeDB())])

    assert user is not None
    assert user["username"] == "lighter_older"
    assert user["selection_mode"] == "fallback"


def test_cli_smoke_command_reports_failures(monkeypatch):
    monkeypatch.setattr(
        "smoke_test.build_smoke_report",
        lambda **kwargs: {
            "ok": False,
            "overall_status": "fail",
            "generated_at": "2026-04-03T00:00:00+00:00",
            "project_root": "/tmp/project",
            "port": {"requested": 5000, "resolved": 5001},
            "steps": [{"name": "cli-help", "kind": "command", "ok": False, "error": "boom"}],
            "git_hygiene": {"available": True, "clean": True},
            "sample_user": None,
        },
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["smoke", "--no-auto-port"])

    assert result.exit_code != 0
    assert "Smoke walkthrough reported failures" in result.output
