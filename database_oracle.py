# database_oracle.py
"""Oracle Database backend — drop-in replacement for the SQLite Database class.

Connects via oracledb thin mode.  DSN format:
    user/password@host:port/service

All tables must already exist (created by scripts/init_oracle.sql).
"""

import re

import oracledb


class Database:
    """Oracle implementation matching the SQLite Database interface."""

    db_type = "oracle"

    def __init__(self, dsn: str, schema: str = "waze"):
        self.dsn = dsn
        self.schema = schema
        user, password, host, port, service = self._parse_dsn(dsn)
        self.conn = oracledb.connect(
            user=user,
            password=password,
            dsn=f"{host}:{port}/{service}",
        )
        # Make unqualified table references resolve to the target schema
        self.conn.cursor().execute(f"ALTER SESSION SET CURRENT_SCHEMA = {schema}")

    @staticmethod
    def _parse_dsn(dsn: str):
        """Parse ``user/password@host:port/service`` into components."""
        m = re.match(
            r"^(?P<user>[^/]+)/(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<service>.+)$",
            dsn,
        )
        if not m:
            raise ValueError(
                f"Invalid DSN format. Expected user/password@host:port/service, got: {dsn}"
            )
        return m["user"], m["password"], m["host"], int(m["port"]), m["service"]

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _translate_placeholders(query: str) -> str:
        """Replace ``?`` positional placeholders with ``:1, :2, :3 ...``."""
        counter = 0

        def _replacer(_match):
            nonlocal counter
            counter += 1
            return f":{counter}"

        return re.sub(r"\?", _replacer, query)

    def execute(self, query: str, params: tuple = ()):
        """Execute *query* after translating ``?`` → ``:N`` placeholders.

        Returns a cursor whose ``.fetchone()`` / ``.fetchall()`` methods
        produce dict-like rows (via ``oracledb.DICT`` rowfactory helper).
        """
        translated = self._translate_placeholders(query)
        cur = self.conn.cursor()
        cur.execute(translated, list(params))
        # Only set rowfactory for queries that return rows
        if cur.description is not None:
            cur.rowfactory = lambda *args: dict(zip([d[0].lower() for d in cur.description], args))
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def insert_event(self, event: dict) -> bool:
        """Insert an event, returning True on success, False on duplicate.

        The Oracle ``events`` table uses ``(event_hash, region)`` as its
        unique constraint, so ``region`` **must** be present in *event*.
        """
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO events (
                    event_hash, username, latitude, longitude,
                    timestamp_utc, timestamp_ms, collected_at,
                    report_type, subtype, region, grid_cell, raw_json
                ) VALUES (
                    :1, :2, :3, :4,
                    TO_TIMESTAMP_TZ(:5, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                    :6,
                    TO_TIMESTAMP_TZ(:7, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                    :8, :9, :10, :11, :12
                )
                """,
                [
                    event["event_hash"],
                    event["username"],
                    event["latitude"],
                    event["longitude"],
                    event["timestamp_utc"],
                    event.get("timestamp_ms"),
                    event["collected_at"],
                    event["report_type"],
                    event.get("subtype"),
                    event["region"],
                    event.get("grid_cell"),
                    event.get("raw_json"),
                ],
            )
            self.conn.commit()
            return True
        except oracledb.IntegrityError:
            self.conn.rollback()
            return False

    # ------------------------------------------------------------------
    # Tracked users
    # ------------------------------------------------------------------

    def upsert_tracked_user(self, username: str, timestamp: str) -> bool:
        """Track a user via MERGE — insert or bump event count."""
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                MERGE INTO tracked_users tu
                USING (SELECT :1 AS username FROM dual) src
                ON (tu.username = src.username)
                WHEN MATCHED THEN
                    UPDATE SET tu.last_seen  = TO_TIMESTAMP_TZ(:2, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                               tu.total_events = tu.total_events + 1
                WHEN NOT MATCHED THEN
                    INSERT (username, first_seen, last_seen, total_events)
                    VALUES (:3,
                            TO_TIMESTAMP_TZ(:4, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                            TO_TIMESTAMP_TZ(:5, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                            1)
                """,
                [username, timestamp, username, timestamp, timestamp],
            )
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def get_tracked_users(self, limit: int = 100):
        """Get tracked users ordered by total event count."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT * FROM tracked_users
            ORDER BY total_events DESC
            FETCH FIRST :1 ROWS ONLY
            """,
            [limit],
        )
        cur.rowfactory = lambda *args: dict(zip([d[0].lower() for d in cur.description], args))
        return cur.fetchall()

    # ------------------------------------------------------------------
    # Daily stats
    # ------------------------------------------------------------------

    def update_daily_stats(
        self,
        date: str,
        events: int = 0,
        users: int = 0,
        requests: int = 0,
        errors: int = 0,
        cells: int = 0,
        by_type: dict = None,
        region: str = "madrid",
    ):
        """Upsert daily statistics via MERGE.

        The Oracle ``daily_stats`` table has columns that differ slightly from
        the SQLite version (no ``api_requests``, ``api_errors``, etc.), so we
        map to the available Oracle columns.
        """
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                MERGE INTO daily_stats ds
                USING (SELECT TO_DATE(:1, 'YYYY-MM-DD') AS stat_date,
                              :2 AS region
                       FROM dual) src
                ON (ds.stat_date = src.stat_date AND ds.region = src.region)
                WHEN MATCHED THEN
                    UPDATE SET ds.total_events = ds.total_events + :3,
                               ds.unique_users = :4
                WHEN NOT MATCHED THEN
                    INSERT (stat_date, region, total_events, unique_users)
                    VALUES (TO_DATE(:5, 'YYYY-MM-DD'), :6, :7, :8)
                """,
                [date, region, events, users, date, region, events, users],
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_daily_stats(self, days: int = 30):
        """Get daily stats for the last N days."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT * FROM daily_stats
            ORDER BY stat_date DESC
            FETCH FIRST :1 ROWS ONLY
            """,
            [days],
        )
        cur.rowfactory = lambda *args: dict(zip([d[0].lower() for d in cur.description], args))
        return cur.fetchall()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_collection_summary(self) -> dict:
        """Get overall collection summary (mirrors SQLite version)."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*)                          AS total_events,
                COUNT(DISTINCT username)          AS unique_users,
                COUNT(DISTINCT TRUNC(timestamp_utc)) AS days_collected,
                MIN(timestamp_utc)                AS first_event,
                MAX(timestamp_utc)                AS last_event,
                COUNT(DISTINCT region)            AS grid_cells_used
            FROM events
            """
        )
        cur.rowfactory = lambda *args: dict(zip([d[0].lower() for d in cur.description], args))
        row = cur.fetchone()
        return row if row else {}
