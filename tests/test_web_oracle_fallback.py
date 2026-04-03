from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database


def test_get_all_dbs_caches_oracle_failure(monkeypatch, tmp_path):
    import database_oracle
    import web.app as web_app

    db_path = tmp_path / "waze_madrid.db"
    Database(str(db_path)).close()

    attempts = {"count": 0}
    clock = {"now": 100.0}

    class FailingOracleDatabase:
        def __init__(self, *args, **kwargs):
            attempts["count"] += 1
            raise RuntimeError("oracle offline")

    monkeypatch.setattr(database_oracle, "Database", FailingOracleDatabase)
    monkeypatch.setattr(
        web_app,
        "_load_web_config",
        lambda: {
            "database_type": "oracle",
            "oracle_dsn": "dsn",
            "sqlite_fallback": True,
            "oracle_schema": "waze",
        },
    )
    monkeypatch.setattr(web_app, "DB_PATHS", {"madrid": str(db_path)})
    monkeypatch.setattr(web_app.time, "time", lambda: clock["now"])
    web_app._oracle_retry_blocked_until = 0.0
    web_app._oracle_retry_last_error = None

    first = web_app.get_all_dbs()
    second = web_app.get_all_dbs()

    assert attempts["count"] == 1
    assert first[0][0] == "madrid"
    assert second[0][0] == "madrid"

    clock["now"] += web_app._ORACLE_RETRY_COOLDOWN_SECONDS + 1
    web_app.get_all_dbs()
    assert attempts["count"] == 2


def test_get_stats_dbs_uses_oracle_retry_cache(monkeypatch, tmp_path):
    import database_oracle
    import web.app as web_app

    db_path = tmp_path / "waze_madrid.db"
    Database(str(db_path)).close()

    attempts = {"count": 0}
    clock = {"now": 200.0}

    class FailingOracleDatabase:
        def __init__(self, *args, **kwargs):
            attempts["count"] += 1
            raise RuntimeError("oracle offline")

    monkeypatch.setattr(database_oracle, "Database", FailingOracleDatabase)
    monkeypatch.setattr(
        web_app,
        "_load_web_config",
        lambda: {
            "database_type": "oracle",
            "oracle_dsn": "dsn",
            "sqlite_fallback": True,
            "oracle_schema": "waze",
        },
    )
    monkeypatch.setattr(web_app, "DB_PATHS", {"madrid": str(db_path)})
    monkeypatch.setattr(web_app.time, "time", lambda: clock["now"])
    web_app._oracle_retry_blocked_until = 0.0
    web_app._oracle_retry_last_error = None

    first = web_app.get_stats_dbs()
    second = web_app.get_stats_dbs()

    assert attempts["count"] == 1
    assert first[0][0] == "madrid"
    assert second[0][0] == "madrid"
