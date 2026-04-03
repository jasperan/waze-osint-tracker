from __future__ import annotations

import signal

import cli


def test_stop_pid_finishes_after_sigterm(monkeypatch, capsys):
    signals: list[int] = []
    removed: list[str | None] = []

    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: signals.append(sig))
    monkeypatch.setattr(cli, "_pid_is_running", lambda pid: False)
    monkeypatch.setattr(cli, "_remove_pid_file", lambda pid_file: removed.append(pid_file))
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    cli._stop_pid(123, "collector", "collector.pid")

    out = capsys.readouterr().out
    assert signals == [signal.SIGTERM]
    assert removed == ["collector.pid"]
    assert "Stopped cleanly" in out


def test_stop_pid_escalates_to_sigkill(monkeypatch, capsys):
    signals: list[int] = []
    times = iter([0.0, 11.0, 11.0, 12.0])
    removed: list[str | None] = []

    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: signals.append(sig))
    monkeypatch.setattr(cli, "_pid_is_running", lambda pid: False)
    monkeypatch.setattr(cli, "_remove_pid_file", lambda pid_file: removed.append(pid_file))
    monkeypatch.setattr(cli.time, "time", lambda: next(times))
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    cli._stop_pid(456, "collector", "collector.pid")

    out = capsys.readouterr().out
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert removed == ["collector.pid"]
    assert "Stopped after SIGKILL" in out


def test_stop_worldwide_pid_refuses_unexpected_process(monkeypatch, capsys):
    removed: list[str | None] = []
    signals: list[int] = []

    monkeypatch.setattr(cli, "_pid_matches_expected", lambda pid, **kwargs: False)
    monkeypatch.setattr(cli, "_remove_pid_file", lambda pid_file: removed.append(pid_file))
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: signals.append(sig))

    cli._stop_worldwide_pid(789)

    err = capsys.readouterr().err
    assert removed == [cli.PID_FILE]
    assert signals == []
    assert "Refusing to signal" in err


def test_stop_script_pid_refuses_unexpected_process(monkeypatch, capsys):
    removed: list[str | None] = []
    signals: list[int] = []

    monkeypatch.setattr(cli, "_pid_matches_expected", lambda pid, **kwargs: False)
    monkeypatch.setattr(cli, "_remove_pid_file", lambda pid_file: removed.append(pid_file))
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: signals.append(sig))

    cli._stop_script_pid(321, "Madrid collector", "collector.pid", "collector.py")

    err = capsys.readouterr().err
    assert removed == ["collector.pid"]
    assert signals == []
    assert "Refusing to signal" in err
