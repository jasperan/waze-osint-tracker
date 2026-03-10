# tests/test_intel_routines.py
import random

from intel_routines import _haversine_km, infer_routines


def make_event(lat: float, lon: float, hour: int, dow: int = 0, report_type: str = "POLICE"):
    """Create a synthetic event dict at a given location and time.

    Args:
        lat: Latitude.
        lon: Longitude.
        hour: Hour of day (0-23).
        dow: Day of week (0=Monday, 6=Sunday).
        report_type: Waze report type.
    """
    # Build an ISO timestamp for a Monday (2026-01-05 is a Monday) + dow offset
    day = 5 + dow
    return {
        "latitude": lat,
        "longitude": lon,
        "timestamp_utc": f"2026-01-{day:02d}T{hour:02d}:00:00Z",
        "timestamp_ms": None,
        "report_type": report_type,
    }


def test_infer_home_location():
    """20 night-time events clustered near (40.42, -3.70) should infer HOME."""
    random.seed(42)
    events = []

    # 20 night events near home location with small jitter
    for _ in range(20):
        lat = 40.42 + random.uniform(-0.002, 0.002)
        lon = -3.70 + random.uniform(-0.002, 0.002)
        hour = random.choice([22, 23, 0, 1, 2, 3, 4, 5, 6])
        events.append(make_event(lat, lon, hour, dow=random.randint(0, 6)))

    routines = infer_routines(events)

    assert "HOME" in routines, f"Expected HOME in routines, got: {list(routines.keys())}"
    home = routines["HOME"]
    assert abs(home["latitude"] - 40.42) < 0.02, (
        f"HOME latitude {home['latitude']} too far from 40.42"
    )
    assert abs(home["longitude"] - (-3.70)) < 0.02, (
        f"HOME longitude {home['longitude']} too far from -3.70"
    )
    assert home["confidence"] > 0, "HOME confidence should be positive"
    assert home["evidence_count"] >= 3, "HOME should have at least 3 evidence events"


def test_infer_work_location():
    """20 work-hour events clustered near (40.45, -3.65) should infer WORK."""
    random.seed(123)
    events = []

    # 20 work-hour events (weekdays, 09:00-17:00)
    for _ in range(20):
        lat = 40.45 + random.uniform(-0.002, 0.002)
        lon = -3.65 + random.uniform(-0.002, 0.002)
        hour = random.choice([9, 10, 11, 12, 13, 14, 15, 16])
        dow = random.randint(0, 4)  # Monday-Friday
        events.append(make_event(lat, lon, hour, dow=dow))

    routines = infer_routines(events)

    assert "WORK" in routines, f"Expected WORK in routines, got: {list(routines.keys())}"
    work = routines["WORK"]
    assert abs(work["latitude"] - 40.45) < 0.02, (
        f"WORK latitude {work['latitude']} too far from 40.45"
    )
    assert abs(work["longitude"] - (-3.65)) < 0.02, (
        f"WORK longitude {work['longitude']} too far from -3.65"
    )
    assert work["confidence"] > 0, "WORK confidence should be positive"
    assert work["evidence_count"] >= 3, "WORK should have at least 3 evidence events"


def test_insufficient_events():
    """Only 3 events should return empty routines (need >= 10)."""
    events = [
        make_event(40.42, -3.70, 23),
        make_event(40.42, -3.70, 0),
        make_event(40.42, -3.70, 1),
    ]

    routines = infer_routines(events)
    assert routines == {}, f"Expected empty dict for insufficient events, got: {routines}"


def test_haversine_known_distance():
    """Verify haversine gives a reasonable distance for known coordinates."""
    # Madrid center to airport (~12 km)
    dist = _haversine_km(40.4168, -3.7038, 40.4722, -3.5611)
    assert 12 < dist < 15, f"Expected ~13km, got {dist}"


def test_home_and_work_detected_together():
    """Events at two distinct locations in appropriate time windows should yield both."""
    random.seed(99)
    events = []

    # Night events at home
    for _ in range(15):
        lat = 40.42 + random.uniform(-0.001, 0.001)
        lon = -3.70 + random.uniform(-0.001, 0.001)
        hour = random.choice([22, 23, 0, 1, 2])
        events.append(make_event(lat, lon, hour, dow=random.randint(0, 6)))

    # Work-hour events at office
    for _ in range(15):
        lat = 40.45 + random.uniform(-0.001, 0.001)
        lon = -3.65 + random.uniform(-0.001, 0.001)
        hour = random.choice([9, 10, 11, 12, 13, 14, 15, 16])
        dow = random.randint(0, 4)
        events.append(make_event(lat, lon, hour, dow=dow))

    routines = infer_routines(events)

    assert "HOME" in routines, "HOME should be detected"
    assert "WORK" in routines, "WORK should be detected"

    # Home and work should be distinct locations
    dist = _haversine_km(
        routines["HOME"]["latitude"],
        routines["HOME"]["longitude"],
        routines["WORK"]["latitude"],
        routines["WORK"]["longitude"],
    )
    assert dist > 2.0, f"HOME and WORK should be >2km apart, got {dist:.1f}km"
