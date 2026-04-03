from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cli import cli
from smoke_test import build_smoke_report, render_smoke_report, render_smoke_report_markdown


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
        "smoke_test.run_command_step",
        lambda name, command, **kwargs: {"name": name, "kind": "command", "ok": True},
    )
    monkeypatch.setattr(
        "smoke_test.wait_for_json",
        lambda url, **kwargs: {
            "ok": True,
            "status_code": 200,
            "data": {"total_events": 1},
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
        "smoke_test.subprocess.Popen",
        lambda *args, **kwargs: DummyProcess(),
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
    assert any(step["name"] == "api-status" for step in report["steps"])


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
