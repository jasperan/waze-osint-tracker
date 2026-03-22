"""Tests for database_factory module."""

from unittest.mock import MagicMock, patch

import pytest

from database_factory import (
    check_oracle_connection,
    get_all_databases,
    get_database,
    load_config,
)


def test_load_config_reads_yaml(tmp_path, monkeypatch):
    """load_config() should read a config file and return a dict."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("database_type: sqlite\ndatabase_path: ./data/test.db\n")
    monkeypatch.setattr("utils._PROJECT_ROOT", str(tmp_path))
    result = load_config()
    assert result["database_type"] == "sqlite"


def test_load_config_prefers_oracle(tmp_path, monkeypatch):
    """config_oracle.yaml should take precedence over config.yaml."""
    (tmp_path / "config.yaml").write_text("database_type: sqlite\n")
    (tmp_path / "config_oracle.yaml").write_text("database_type: oracle\noracle_dsn: test\n")
    monkeypatch.setattr("utils._PROJECT_ROOT", str(tmp_path))
    result = load_config()
    assert result["database_type"] == "oracle"


def test_get_database_sqlite_explicit():
    """When database_type is sqlite, get_database returns SQLite DB."""
    config = {"database_type": "sqlite", "database_path": ":memory:"}
    db = get_database(config)
    # SQLite Database should have a conn attribute
    assert hasattr(db, "conn")
    db.close()


@patch("database_factory._get_oracle")
def test_get_database_oracle_default(mock_oracle):
    """When database_type is oracle, get_database tries Oracle."""
    mock_db = MagicMock()
    mock_oracle.return_value = mock_db
    config = {"database_type": "oracle", "oracle_dsn": "test/test@localhost:1521/FREEPDB1"}
    result = get_database(config)
    assert result is mock_db
    mock_oracle.assert_called_once()


@patch("database_factory._get_oracle", side_effect=ConnectionError("no oracle"))
def test_get_database_fallback_to_sqlite(mock_oracle):
    """When Oracle fails and sqlite_fallback is True, falls back to SQLite."""
    config = {
        "database_type": "oracle",
        "oracle_dsn": "test/test@localhost:1521/FREEPDB1",
        "sqlite_fallback": True,
        "database_path": ":memory:",
    }
    db = get_database(config)
    assert hasattr(db, "conn")
    db.close()


@patch("database_factory._get_oracle", side_effect=ConnectionError("no oracle"))
def test_get_database_no_fallback_raises(mock_oracle):
    """When Oracle fails without sqlite_fallback, raises ConnectionError."""
    config = {
        "database_type": "oracle",
        "oracle_dsn": "test/test@localhost:1521/FREEPDB1",
        "sqlite_fallback": False,
    }
    with pytest.raises(ConnectionError):
        get_database(config)


def test_get_all_databases_sqlite(tmp_path, monkeypatch):
    """get_all_databases with sqlite returns per-region files."""
    from database import Database

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # Create a fake SQLite DB
    db = Database(str(data_dir / "waze_europe.db"))
    db.close()

    monkeypatch.setattr("utils._PROJECT_ROOT", str(tmp_path))
    config = {"database_type": "sqlite", "database_path": str(data_dir / "waze_madrid.db")}
    dbs = get_all_databases(config)
    regions = [r for r, _ in dbs]
    assert "europe" in regions
    for _, d in dbs:
        d.close()


@patch("database_factory._get_oracle")
def test_check_oracle_connection_success(mock_oracle):
    """check_oracle_connection returns True when Oracle is reachable."""
    mock_db = MagicMock()
    mock_row = {"cnt": 42}
    mock_db.execute.return_value.fetchone.return_value = mock_row
    mock_oracle.return_value = mock_db
    config = {"oracle_dsn": "test/test@localhost:1521/FREEPDB1"}
    ok, msg = check_oracle_connection(config)
    assert ok is True
    assert "42" in msg


@patch("database_factory._get_oracle", side_effect=Exception("refused"))
def test_check_oracle_connection_failure(mock_oracle):
    """check_oracle_connection returns False when Oracle is down."""
    config = {"oracle_dsn": "test/test@localhost:1521/FREEPDB1"}
    ok, msg = check_oracle_connection(config)
    assert ok is False
    assert "refused" in msg
