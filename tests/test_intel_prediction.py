# tests/test_intel_prediction.py
from datetime import datetime, timedelta, timezone

from intel_prediction import predict_presence


def _make_event(lat: float, lon: float, dt: datetime, report_type: str = "POLICE") -> dict:
    """Helper to build an event dict from a datetime."""
    return {
        "latitude": lat,
        "longitude": lon,
        "timestamp_ms": int(dt.timestamp() * 1000),
        "report_type": report_type,
    }


def _monday_at_9(week_offset: int) -> datetime:
    """Return a Monday at 09:00 UTC, *week_offset* weeks from a reference Monday."""
    # 2026-01-05 is a Monday
    base = datetime(2026, 1, 5, 9, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(weeks=week_offset)


def test_predict_location():
    """User consistently at (40.42, -3.70) on Mondays 9am for 10 weeks → predict Monday 9am."""
    events = []
    for week in range(10):
        dt = _monday_at_9(week)
        # Add small jitter so DBSCAN has realistic spread
        lat = 40.42 + (week % 3) * 0.0001
        lon = -3.70 + (week % 5) * 0.0001
        events.append(_make_event(lat, lon, dt))

    result = predict_presence(events, target_dow=0, target_hour=9)

    assert result is not None
    assert abs(result["latitude"] - 40.42) < 0.01
    assert abs(result["longitude"] - (-3.70)) < 0.01
    assert result["confidence"] > 0.5
    assert result["radius_km"] < 1.0
    assert result["evidence_count"] >= 2


def test_no_data_for_time():
    """User only active Mondays → predict Sunday should return None or very low confidence."""
    events = []
    for week in range(10):
        dt = _monday_at_9(week)
        events.append(_make_event(40.42, -3.70, dt))

    # Sunday = dow 6
    result = predict_presence(events, target_dow=6, target_hour=9)

    # No Sunday events → should be None (fewer than 2 matching events)
    assert result is None
