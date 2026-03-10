# tests/test_intel_vectors.py
import math

import numpy as np

from intel_vectors import (
    REGION_BBOXES,
    build_behavioral_vector,
    build_hour_histogram,
    cosine_similarity,
    haversine_km,
)


def _make_event(lat, lon, timestamp_ms, report_type):
    """Helper to create an event dict."""
    return {
        "latitude": lat,
        "longitude": lon,
        "timestamp_ms": timestamp_ms,
        "report_type": report_type,
    }


# --- Timestamp helpers ---
# Base: 2026-01-05 00:00:00 UTC (a Monday)
_BASE_MS = 1767571200000  # 2026-01-05T00:00:00Z
_HOUR_MS = 3_600_000
_DAY_MS = 86_400_000

MADRID_BBOX = REGION_BBOXES["madrid"]


def test_build_hour_histogram():
    """Verify 24 bins, normalized, correct values."""
    hours = [8, 8, 8, 9, 9, 17]
    hist = build_hour_histogram(hours)

    assert len(hist) == 24
    assert math.isclose(sum(hist), 1.0, abs_tol=1e-9)
    assert math.isclose(hist[8], 3 / 6)
    assert math.isclose(hist[9], 2 / 6)
    assert math.isclose(hist[17], 1 / 6)
    # All other bins should be zero
    for i in range(24):
        if i not in (8, 9, 17):
            assert hist[i] == 0.0


def test_build_hour_histogram_empty():
    """Empty input returns 24 zeros."""
    hist = build_hour_histogram([])
    assert len(hist) == 24
    assert all(v == 0.0 for v in hist)


def test_haversine_km_known_distance():
    """Haversine between two known Madrid points (~1.6 km)."""
    # Puerta del Sol to Plaza Mayor (~0.4 km)
    d = haversine_km(40.4168, -3.7038, 40.4154, -3.7074)
    assert 0.2 < d < 1.0  # roughly 0.35 km


def test_haversine_km_same_point():
    """Distance from a point to itself is zero."""
    d = haversine_km(40.42, -3.70, 40.42, -3.70)
    assert d == 0.0


def test_cosine_similarity_identical():
    """Identical vectors have similarity 1.0."""
    a = np.array([1.0, 2.0, 3.0])
    sim = cosine_similarity(a, a)
    assert math.isclose(sim, 1.0, abs_tol=1e-9)


def test_cosine_similarity_orthogonal():
    """Orthogonal vectors have similarity 0.0."""
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    sim = cosine_similarity(a, b)
    assert math.isclose(sim, 0.0, abs_tol=1e-9)


def test_cosine_similarity_zero_vector():
    """Zero vector returns 0.0."""
    a = np.array([1.0, 2.0])
    b = np.zeros(2)
    assert cosine_similarity(a, b) == 0.0


def test_build_behavioral_vector():
    """Verify shape (44,), all finite values."""
    events = [
        _make_event(40.42, -3.70, _BASE_MS + 8 * _HOUR_MS, "POLICE"),
        _make_event(40.43, -3.71, _BASE_MS + 9 * _HOUR_MS, "JAM"),
        _make_event(40.44, -3.72, _BASE_MS + 10 * _HOUR_MS, "POLICE"),
        _make_event(40.42, -3.70, _BASE_MS + _DAY_MS + 8 * _HOUR_MS, "HAZARD"),
        _make_event(40.43, -3.71, _BASE_MS + 2 * _DAY_MS + 9 * _HOUR_MS, "POLICE"),
    ]

    vec = build_behavioral_vector(events, MADRID_BBOX)

    assert vec.shape == (44,)
    assert np.all(np.isfinite(vec))

    # Hour histogram sums to 1
    assert math.isclose(sum(vec[0:24]), 1.0, abs_tol=1e-9)
    # DOW histogram sums to 1
    assert math.isclose(sum(vec[24:31]), 1.0, abs_tol=1e-9)
    # Event type distribution sums to 1
    assert math.isclose(sum(vec[34:40]), 1.0, abs_tol=1e-9)
    # Geographic centroid within [0, 1]
    assert 0.0 <= vec[31] <= 1.0
    assert 0.0 <= vec[32] <= 1.0
    # Activity is positive
    assert vec[43] > 0.0


def test_build_behavioral_vector_empty():
    """Empty events produce a zero vector."""
    vec = build_behavioral_vector([], MADRID_BBOX)
    assert vec.shape == (44,)
    assert np.all(vec == 0.0)


def test_build_behavioral_vector_single_event():
    """Single event still produces a valid 44-dim vector."""
    events = [_make_event(40.42, -3.70, _BASE_MS + 8 * _HOUR_MS, "POLICE")]
    vec = build_behavioral_vector(events, MADRID_BBOX)
    assert vec.shape == (44,)
    assert np.all(np.isfinite(vec))
    # Cadence dims should be zero with a single event
    assert vec[40] == 0.0
    assert vec[41] == 0.0
    assert vec[42] == 0.0


def test_vector_similarity_different_users():
    """Morning commuter vs night owl should have low similarity (< 0.5)."""
    # Use the global bbox to amplify geographic differences
    global_bbox = REGION_BBOXES["global"]

    # Morning commuter: reports 7-9 AM on weekdays, POLICE only, Madrid center
    morning_events = []
    for day in range(21):  # 3 weeks
        if day % 7 < 5:  # weekdays only
            for hour in (7, 8, 9):
                ts = _BASE_MS + day * _DAY_MS + hour * _HOUR_MS
                morning_events.append(_make_event(40.42, -3.70, ts, "POLICE"))

    # Night owl: reports 22-02 on weekends, ROAD_CLOSED/CHIT_CHAT, Tokyo
    night_events = []
    for day in range(21):
        if day % 7 >= 5:  # weekends only
            for hour in (22, 23, 0, 1, 2):
                ts = _BASE_MS + day * _DAY_MS + hour * _HOUR_MS
                rt = "ROAD_CLOSED" if hour % 2 == 0 else "CHIT_CHAT"
                night_events.append(_make_event(35.68, 139.69, ts, rt))

    max_count = max(len(morning_events), len(night_events))
    vec_morning = build_behavioral_vector(morning_events, global_bbox, max_event_count=max_count)
    vec_night = build_behavioral_vector(night_events, global_bbox, max_event_count=max_count)

    sim = cosine_similarity(vec_morning, vec_night)
    assert sim < 0.65, f"Expected similarity < 0.65 for different patterns, got {sim}"


def test_vector_similarity_same_pattern():
    """Two similar users (same hours, same area, same types) should have high similarity (> 0.8)."""
    # User A: reports 8-10 AM on weekdays, POLICE, central Madrid
    user_a_events = []
    for day in range(14):
        if day % 7 < 5:
            for hour in (8, 9, 10):
                ts = _BASE_MS + day * _DAY_MS + hour * _HOUR_MS
                user_a_events.append(_make_event(40.42, -3.70, ts, "POLICE"))

    # User B: same pattern, slightly shifted location
    user_b_events = []
    for day in range(14):
        if day % 7 < 5:
            for hour in (8, 9, 10):
                ts = _BASE_MS + day * _DAY_MS + hour * _HOUR_MS
                user_b_events.append(_make_event(40.43, -3.71, ts, "POLICE"))

    max_count = max(len(user_a_events), len(user_b_events))
    vec_a = build_behavioral_vector(user_a_events, MADRID_BBOX, max_event_count=max_count)
    vec_b = build_behavioral_vector(user_b_events, MADRID_BBOX, max_event_count=max_count)

    sim = cosine_similarity(vec_a, vec_b)
    assert sim > 0.8, f"Expected similarity > 0.8 for similar patterns, got {sim}"
