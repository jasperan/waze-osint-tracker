import json
from datetime import datetime, timedelta, timezone

from runtime_support import find_available_port, read_status_file


def test_read_status_file_marks_stale(tmp_path):
    status_path = tmp_path / "collector_status.json"
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    status_path.write_text(json.dumps({"timestamp": stale_ts, "status": "scanning"}))

    status = read_status_file(status_path, stale_seconds=60)

    assert status["status"] == "stale"
    assert status["stale"] is True
    assert status["message"] == "Collector status file is stale"


def test_read_status_file_keeps_live_status(tmp_path):
    now = datetime.now(timezone.utc)
    status_path = tmp_path / "collector_status.json"
    status_path.write_text(json.dumps({"timestamp": now.isoformat(), "status": "scanning"}))

    status = read_status_file(status_path, now=now, stale_seconds=600)

    assert status["status"] == "scanning"
    assert status["stale"] is False


def test_find_available_port_skips_busy_port(monkeypatch):
    busy_port = 5000
    checks = []

    def fake_is_port_available(port, host="127.0.0.1"):
        checks.append(port)
        return port != busy_port

    monkeypatch.setattr("runtime_support.is_port_available", fake_is_port_available)

    free_port = find_available_port(busy_port)

    assert checks[:2] == [busy_port, busy_port + 1]
    assert free_port == busy_port + 1
