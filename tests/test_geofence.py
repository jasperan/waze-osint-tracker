# tests/test_geofence.py
"""Tests for geofence module: geometry helpers, Geofence dataclass, GeofenceManager."""

import os
import sys
import tempfile

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from geofence import (
    Geofence,
    GeofenceManager,
    point_in_circle,
    point_in_polygon,
)

# ---------------------------------------------------------------------------
# Madrid reference points
# ---------------------------------------------------------------------------
MADRID_CENTER_LAT = 40.4168
MADRID_CENTER_LON = -3.7038

# Square around central Madrid (roughly 1 km side)
MADRID_SQUARE = [
    (40.42, -3.71),
    (40.42, -3.70),
    (40.41, -3.70),
    (40.41, -3.71),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def tmp_db():
    """Yield a fresh SQLite Database backed by a temp file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    db.conn.close()
    os.unlink(path)


@pytest.fixture()
def manager(tmp_db):
    return GeofenceManager(tmp_db)


# ---------------------------------------------------------------------------
# point_in_circle
# ---------------------------------------------------------------------------
class TestPointInCircle:
    def test_inside(self):
        # 0 meters away is inside any positive radius
        assert (
            point_in_circle(
                MADRID_CENTER_LAT, MADRID_CENTER_LON, MADRID_CENTER_LAT, MADRID_CENTER_LON, 100
            )
            is True
        )

    def test_inside_nearby(self):
        # ~111 m north of center should be within 200 m
        assert (
            point_in_circle(
                MADRID_CENTER_LAT + 0.001,
                MADRID_CENTER_LON,
                MADRID_CENTER_LAT,
                MADRID_CENTER_LON,
                200,
            )
            is True
        )

    def test_outside(self):
        # Barcelona is ~500 km away, not within 1 km
        assert point_in_circle(41.3851, 2.1734, MADRID_CENTER_LAT, MADRID_CENTER_LON, 1000) is False


# ---------------------------------------------------------------------------
# point_in_polygon
# ---------------------------------------------------------------------------
class TestPointInPolygon:
    def test_inside(self):
        # Center of the square
        assert point_in_polygon(40.415, -3.705, MADRID_SQUARE) is True

    def test_outside(self):
        # Well outside the square
        assert point_in_polygon(41.0, -3.0, MADRID_SQUARE) is False

    def test_edge_outside(self):
        # Just outside the southern edge
        assert point_in_polygon(40.409, -3.705, MADRID_SQUARE) is False


# ---------------------------------------------------------------------------
# Geofence.contains
# ---------------------------------------------------------------------------
class TestGeofenceContains:
    def test_circle_contains(self):
        fence = Geofence(
            geofence_id="c1",
            name="Madrid circle",
            geometry_type="circle",
            center_lat=MADRID_CENTER_LAT,
            center_lon=MADRID_CENTER_LON,
            radius_m=500,
        )
        assert fence.contains(MADRID_CENTER_LAT, MADRID_CENTER_LON) is True
        assert fence.contains(41.3851, 2.1734) is False  # Barcelona

    def test_polygon_contains(self):
        fence = Geofence(
            geofence_id="p1",
            name="Madrid square",
            geometry_type="polygon",
            polygon=MADRID_SQUARE,
        )
        assert fence.contains(40.415, -3.705) is True
        assert fence.contains(41.0, -3.0) is False


# ---------------------------------------------------------------------------
# GeofenceManager CRUD
# ---------------------------------------------------------------------------
class TestGeofenceManagerCRUD:
    def test_create_circle(self, manager):
        fence = manager.create_geofence(
            name="Test circle",
            geometry_type="circle",
            center_lat=MADRID_CENTER_LAT,
            center_lon=MADRID_CENTER_LON,
            radius_m=500,
        )
        assert fence.geofence_id
        assert fence.name == "Test circle"
        assert fence.geometry_type == "circle"
        assert fence.radius_m == 500

    def test_create_polygon(self, manager):
        fence = manager.create_geofence(
            name="Test polygon",
            geometry_type="polygon",
            polygon=MADRID_SQUARE,
        )
        assert fence.geometry_type == "polygon"
        assert len(fence.polygon) == 4

    def test_list_geofences(self, manager):
        manager.create_geofence(
            name="A", geometry_type="circle", center_lat=40.0, center_lon=-3.0, radius_m=100
        )
        manager.create_geofence(name="B", geometry_type="polygon", polygon=MADRID_SQUARE)
        fences = manager.list_geofences()
        assert len(fences) == 2
        names = {f.name for f in fences}
        assert names == {"A", "B"}

    def test_list_uses_cache(self, manager):
        manager.create_geofence(
            name="C", geometry_type="circle", center_lat=40.0, center_lon=-3.0, radius_m=100
        )
        first = manager.list_geofences()
        second = manager.list_geofences()
        assert first is second  # same object means cache hit

    def test_delete_geofence(self, manager):
        fence = manager.create_geofence(
            name="D", geometry_type="circle", center_lat=40.0, center_lon=-3.0, radius_m=100
        )
        manager.delete_geofence(fence.geofence_id)
        assert len(manager.list_geofences()) == 0


# ---------------------------------------------------------------------------
# check_event
# ---------------------------------------------------------------------------
class TestCheckEvent:
    def _make_event(self, username, lat, lon, report_type="POLICE"):
        return {
            "username": username,
            "latitude": lat,
            "longitude": lon,
            "timestamp_ms": 1700000000000,
            "report_type": report_type,
        }

    def test_triggers_inside(self, manager):
        manager.create_geofence(
            name="Madrid zone",
            geometry_type="circle",
            center_lat=MADRID_CENTER_LAT,
            center_lon=MADRID_CENTER_LON,
            radius_m=1000,
        )
        event = self._make_event("alice", MADRID_CENTER_LAT, MADRID_CENTER_LON)
        alerts = manager.check_event(event)
        assert len(alerts) == 1
        assert alerts[0]["username"] == "alice"
        assert alerts[0]["geofence_name"] == "Madrid zone"

    def test_no_trigger_outside(self, manager):
        manager.create_geofence(
            name="Madrid zone",
            geometry_type="circle",
            center_lat=MADRID_CENTER_LAT,
            center_lon=MADRID_CENTER_LON,
            radius_m=100,
        )
        # Barcelona event
        event = self._make_event("alice", 41.3851, 2.1734)
        alerts = manager.check_event(event)
        assert len(alerts) == 0

    def test_tracked_users_filter(self, manager):
        manager.create_geofence(
            name="Tracked zone",
            geometry_type="circle",
            center_lat=MADRID_CENTER_LAT,
            center_lon=MADRID_CENTER_LON,
            radius_m=1000,
            tracked_users=["alice"],
        )
        # alice is tracked, should trigger
        event_alice = self._make_event("alice", MADRID_CENTER_LAT, MADRID_CENTER_LON)
        assert len(manager.check_event(event_alice)) == 1

        # bob is NOT tracked, should not trigger
        event_bob = self._make_event("bob", MADRID_CENTER_LAT, MADRID_CENTER_LON)
        assert len(manager.check_event(event_bob)) == 0

    def test_alert_history_persists(self, manager):
        manager.create_geofence(
            name="History zone",
            geometry_type="circle",
            center_lat=MADRID_CENTER_LAT,
            center_lon=MADRID_CENTER_LON,
            radius_m=1000,
        )
        event = self._make_event("alice", MADRID_CENTER_LAT, MADRID_CENTER_LON)
        manager.check_event(event)

        history = manager.get_alert_history()
        assert len(history) == 1
        assert history[0]["username"] == "alice"
        assert history[0]["geofence_name"] == "History zone"

    def test_multiple_alerts_history(self, manager):
        manager.create_geofence(
            name="Zone A",
            geometry_type="circle",
            center_lat=MADRID_CENTER_LAT,
            center_lon=MADRID_CENTER_LON,
            radius_m=5000,
        )
        manager.create_geofence(
            name="Zone B",
            geometry_type="polygon",
            polygon=MADRID_SQUARE,
        )
        # This point is inside both (inside the circle and the square)
        event = self._make_event("carlos", 40.415, -3.705)
        alerts = manager.check_event(event)
        assert len(alerts) == 2

        history = manager.get_alert_history(limit=10)
        assert len(history) == 2
