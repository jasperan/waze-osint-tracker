# geofence.py
"""Geofencing engine: define zones, check events against them, persist alerts."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from utils import haversine_m


def point_in_circle(
    point_lat: float,
    point_lon: float,
    center_lat: float,
    center_lon: float,
    radius_m: float,
) -> bool:
    """Return True if the point is within *radius_m* meters of the center."""
    return haversine_m(point_lat, point_lon, center_lat, center_lon) <= radius_m


def point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting algorithm: return True if (lat, lon) is inside *polygon*.

    *polygon* is a list of (lat, lon) vertices. The polygon is implicitly closed
    (last vertex connects back to the first).
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


@dataclass
class Geofence:
    geofence_id: str
    name: str
    geometry_type: str  # "circle" or "polygon"
    center_lat: float = 0.0
    center_lon: float = 0.0
    radius_m: float = 0.0
    polygon: list = field(default_factory=list)
    tracked_users: list = field(default_factory=list)
    created_at: str = ""

    def contains(self, lat: float, lon: float) -> bool:
        if self.geometry_type == "circle":
            return point_in_circle(lat, lon, self.center_lat, self.center_lon, self.radius_m)
        if self.geometry_type == "polygon":
            return point_in_polygon(lat, lon, self.polygon)
        return False


class GeofenceManager:
    """Manages geofence CRUD and event checking against an SQLite Database."""

    def __init__(self, db):
        self.db = db
        self._cache: list[Geofence] | None = None
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_tables(self):
        self.db.conn.executescript("""
            CREATE TABLE IF NOT EXISTS geofences (
                geofence_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                geometry_type TEXT NOT NULL,
                geometry_json TEXT NOT NULL,
                tracked_users_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geofence_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                geofence_id TEXT NOT NULL,
                geofence_name TEXT NOT NULL,
                username TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                alerted_at TEXT NOT NULL
            );
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_geofence(
        self,
        name: str,
        geometry_type: str,
        center_lat: float = 0.0,
        center_lon: float = 0.0,
        radius_m: float = 0.0,
        polygon: list | None = None,
        tracked_users: list | None = None,
    ) -> Geofence:
        gid = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()

        if geometry_type == "circle":
            geometry = {"center_lat": center_lat, "center_lon": center_lon, "radius_m": radius_m}
        else:
            geometry = {"polygon": [list(p) for p in (polygon or [])]}

        tracked = tracked_users or []

        self.db.conn.execute(
            "INSERT INTO geofences (geofence_id, name, geometry_type, geometry_json, "
            "tracked_users_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (gid, name, geometry_type, json.dumps(geometry), json.dumps(tracked), now),
        )
        self.db.conn.commit()
        self._cache = None  # invalidate

        return Geofence(
            geofence_id=gid,
            name=name,
            geometry_type=geometry_type,
            center_lat=center_lat,
            center_lon=center_lon,
            radius_m=radius_m,
            polygon=polygon or [],
            tracked_users=tracked,
            created_at=now,
        )

    def list_geofences(self) -> list[Geofence]:
        if self._cache is not None:
            return self._cache

        rows = self.db.conn.execute(
            "SELECT geofence_id, name, geometry_type, geometry_json, "
            "tracked_users_json, created_at FROM geofences"
        ).fetchall()

        fences: list[Geofence] = []
        for row in rows:
            geo = json.loads(row["geometry_json"])
            tracked = json.loads(row["tracked_users_json"])
            if row["geometry_type"] == "circle":
                fences.append(
                    Geofence(
                        geofence_id=row["geofence_id"],
                        name=row["name"],
                        geometry_type="circle",
                        center_lat=geo["center_lat"],
                        center_lon=geo["center_lon"],
                        radius_m=geo["radius_m"],
                        tracked_users=tracked,
                        created_at=row["created_at"],
                    )
                )
            else:
                fences.append(
                    Geofence(
                        geofence_id=row["geofence_id"],
                        name=row["name"],
                        geometry_type="polygon",
                        polygon=[tuple(p) for p in geo["polygon"]],
                        tracked_users=tracked,
                        created_at=row["created_at"],
                    )
                )

        self._cache = fences
        return fences

    def delete_geofence(self, geofence_id: str) -> None:
        self.db.conn.execute("DELETE FROM geofences WHERE geofence_id = ?", (geofence_id,))
        self.db.conn.commit()
        self._cache = None

    # ------------------------------------------------------------------
    # Event checking
    # ------------------------------------------------------------------

    def check_event(self, event: dict) -> list[dict]:
        """Check an event against all geofences, persist and return triggered alerts."""
        username = event.get("username", "")
        lat = event.get("latitude", 0.0)
        lon = event.get("longitude", 0.0)
        timestamp_ms = event.get("timestamp_ms", 0)
        event_type = event.get("report_type", event.get("event_type", "unknown"))

        alerts: list[dict] = []
        now = datetime.now(timezone.utc).isoformat()

        for fence in self.list_geofences():
            # If tracked_users is set, skip users not in the list
            if fence.tracked_users and username not in fence.tracked_users:
                continue

            if fence.contains(lat, lon):
                alert = {
                    "geofence_id": fence.geofence_id,
                    "geofence_name": fence.name,
                    "username": username,
                    "latitude": lat,
                    "longitude": lon,
                    "timestamp_ms": timestamp_ms,
                    "event_type": event_type,
                    "alerted_at": now,
                }
                self.db.conn.execute(
                    "INSERT INTO geofence_alerts "
                    "(geofence_id, geofence_name, username, latitude, longitude, "
                    "timestamp_ms, event_type, alerted_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        fence.geofence_id,
                        fence.name,
                        username,
                        lat,
                        lon,
                        timestamp_ms,
                        event_type,
                        now,
                    ),
                )
                alerts.append(alert)

        if alerts:
            self.db.conn.commit()

        return alerts

    def get_alert_history(self, limit: int = 50) -> list[dict]:
        """Return the most recent geofence alerts."""
        rows = self.db.conn.execute(
            "SELECT geofence_id, geofence_name, username, latitude, longitude, "
            "timestamp_ms, event_type, alerted_at "
            "FROM geofence_alerts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
