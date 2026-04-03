import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from ops_diagnostics import (
    build_doctor_report,
    find_available_port,
    read_status_file,
    render_doctor_report,
)


def test_read_status_file_missing(tmp_path):
    result = read_status_file(tmp_path / "missing.json")
    assert result["status"] == "unknown"


def test_read_status_file_marks_stale(tmp_path):
    status_path = tmp_path / "collector_status.json"
    stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
    status_path.write_text(json.dumps({"timestamp": stale_time.isoformat(), "status": "scanning"}))

    result = read_status_file(status_path, stale_seconds=60)
    assert result["status"] == "stale"
    assert result["stale"] is True


def test_find_available_port_skips_busy_socket(monkeypatch):
    checks = []

    def fake_port_is_available(port, host="127.0.0.1"):
        checks.append(port)
        return port != 5000

    monkeypatch.setattr("ops_diagnostics.port_is_available", fake_port_is_available)

    free_port = find_available_port(5000, search_window=20)
    assert checks[:2] == [5000, 5001]
    assert free_port == 5001


def test_build_doctor_report_and_render(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "waze_madrid.db"
    Database(str(db_path)).close()

    (tmp_path / "config.yaml").write_text(
        "\n".join(
            [
                "database_type: sqlite",
                f'database_path: "{db_path}"',
                "sqlite_fallback: true",
            ]
        )
    )
    (data_dir / "collector_status.json").write_text(
        json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "status": "idle"})
    )

    import database_factory

    monkeypatch.setattr(
        database_factory,
        "check_oracle_connection",
        lambda config=None: (False, "oracle unavailable"),
    )
    monkeypatch.setattr("ops_diagnostics.port_is_available", lambda port, host="127.0.0.1": False)
    monkeypatch.setattr("ops_diagnostics.find_available_port", lambda preferred_port=5000: 5001)

    report = build_doctor_report(
        {"database_type": "sqlite", "database_path": str(db_path), "sqlite_fallback": True},
        project_root=tmp_path,
        live_check=False,
    )

    assert report["backend"]["requested"] == "sqlite"
    assert report["sqlite"]["databases"][0]["exists"] is True
    assert report["port"]["recommended"] == 5001
    rendered = render_doctor_report(report)
    assert "Waze Doctor" in rendered
    assert "oracle unavailable" in rendered
