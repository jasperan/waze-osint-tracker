"""Database factory — unified access to Oracle (primary) or SQLite (fallback).

Reads config to determine backend. Oracle is the default. SQLite activates when
``database_type: sqlite`` is set or when ``sqlite_fallback: true`` and Oracle
is unreachable.
"""

import logging
import os
import time

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def load_config():
    """Load config, preferring config_oracle.yaml over config.yaml."""
    for config_file in ("config_oracle.yaml", "config.yaml"):
        full_path = os.path.join(_PROJECT_ROOT, config_file)
        if os.path.exists(full_path):
            with open(full_path) as f:
                return yaml.safe_load(f)
    with open(os.path.join(_PROJECT_ROOT, "config.yaml")) as f:
        return yaml.safe_load(f)


def get_database(config=None, region=None, retry=True):
    """Return a database connection based on config.

    Parameters
    ----------
    config : dict or None
        Parsed config dict. Loaded from disk when None.
    region : str or None
        Region hint for SQLite per-region files.
    retry : bool
        If True and Oracle is selected, retry connection up to 3 times
        with exponential backoff (useful during container startup).

    Returns
    -------
    Database instance (Oracle or SQLite).
    """
    if config is None:
        config = load_config()

    db_type = config.get("database_type", "oracle")

    if db_type == "sqlite":
        return _get_sqlite(config, region)

    # Oracle is the default
    try:
        return _get_oracle(config, retry=retry)
    except Exception as exc:
        if config.get("sqlite_fallback", False):
            logger.warning("Oracle unavailable (%s), falling back to SQLite", exc)
            return _get_sqlite(config, region)
        raise


def _get_oracle(config, retry=True):
    """Connect to Oracle with optional retry."""
    from database_oracle import Database as OracleDatabase

    dsn = config.get("oracle_dsn", "waze/WazeIntel2026@localhost:1521/FREEPDB1")
    schema = config.get("oracle_schema", "waze")

    max_attempts = 3 if retry else 1
    last_exc = None
    for attempt in range(max_attempts):
        try:
            db = OracleDatabase(dsn, schema)
            if attempt > 0:
                logger.info("Oracle connected after %d retries", attempt)
            return db
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                wait = 2 ** (attempt + 1)  # 2, 4 seconds
                logger.debug(
                    "Oracle connection attempt %d failed, retrying in %ds", attempt + 1, wait
                )
                time.sleep(wait)

    raise ConnectionError(f"Cannot connect to Oracle after {max_attempts} attempts: {last_exc}")


def _get_sqlite(config, region=None):
    """Return a SQLite database connection."""
    from database import Database

    if region:
        db_path = os.path.join(_PROJECT_ROOT, "data", f"waze_{region}.db")
        if os.path.exists(db_path):
            return Database(db_path)
    return Database(
        config.get("database_path", os.path.join(_PROJECT_ROOT, "data", "waze_madrid.db"))
    )


def get_all_databases(config=None):
    """Return list of (region_name, db) pairs covering all data.

    Oracle: single ("all", db) pair.
    SQLite: one pair per existing regional file.
    """
    if config is None:
        config = load_config()

    db_type = config.get("database_type", "oracle")

    if db_type != "sqlite":
        try:
            db = _get_oracle(config, retry=True)
            return [("all", db)]
        except Exception:
            if not config.get("sqlite_fallback", False):
                raise
            logger.warning("Oracle unavailable, falling back to SQLite for all DBs")

    # SQLite path
    from database import Database

    data_dir = os.path.join(_PROJECT_ROOT, "data")
    regions = ["madrid", "europe", "americas", "asia", "oceania", "africa"]
    dbs = []
    for region in regions:
        path = os.path.join(data_dir, f"waze_{region}.db")
        if os.path.exists(path):
            try:
                dbs.append((region, Database(path)))
            except Exception:
                logger.warning("Failed to open SQLite DB for region %s", region)
    return dbs


def check_oracle_connection(config=None):
    """Test Oracle connectivity. Returns (ok, message) tuple."""
    if config is None:
        config = load_config()

    try:
        db = _get_oracle(config, retry=False)
        # Check if schema tables exist
        try:
            row = db.execute("SELECT COUNT(*) AS cnt FROM events").fetchone()
            event_count = row["cnt"] if isinstance(row, dict) else row[0]
            db.close()
            return True, f"Connected. Events table has {event_count} rows."
        except Exception:
            db.close()
            return True, "Connected, but schema not initialized. Run: waze db init"
    except Exception as exc:
        return False, f"Connection failed: {exc}"
