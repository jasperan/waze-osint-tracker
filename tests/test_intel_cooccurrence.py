# tests/test_intel_cooccurrence.py
from intel_cooccurrence import find_cooccurrences


def test_find_cooccurrences():
    """Two users at the same location 3 times should produce one co-occurrence
    edge.  A distant user C must NOT match either of them."""
    base_ts = 1_700_000_000_000  # arbitrary epoch ms

    events = []
    for offset_min in (0, 60, 120):  # three separate 1-minute windows
        ts = base_ts + offset_min * 60_000
        # User A and B at virtually the same spot, within temporal window
        events.append(
            {
                "username": "alice",
                "latitude": 40.4168,
                "longitude": -3.7038,
                "timestamp_ms": ts,
                "region": "madrid",
            }
        )
        events.append(
            {
                "username": "bob",
                "latitude": 40.4169,
                "longitude": -3.7037,
                "timestamp_ms": ts + 30_000,  # 30 s later
                "region": "madrid",
            }
        )
        # User C is far away (~1000 km north)
        events.append(
            {
                "username": "charlie",
                "latitude": 49.0,
                "longitude": -3.7038,
                "timestamp_ms": ts + 10_000,
                "region": "paris",
            }
        )

    results = find_cooccurrences(
        events, spatial_threshold_m=500, temporal_threshold_s=300, min_count=3
    )

    # Exactly one edge: alice <-> bob
    assert len(results) == 1
    edge = results[0]
    assert edge["user_a"] == "alice"
    assert edge["user_b"] == "bob"
    assert edge["co_count"] == 3
    assert edge["avg_distance_m"] < 500  # they are ~15 m apart
    assert edge["avg_time_gap_s"] < 300


def test_no_self_cooccurrence():
    """The same user appearing twice at the same place must NOT produce any
    co-occurrence edge."""
    base_ts = 1_700_000_000_000

    events = [
        {
            "username": "solo",
            "latitude": 40.4168,
            "longitude": -3.7038,
            "timestamp_ms": base_ts,
            "region": "madrid",
        },
        {
            "username": "solo",
            "latitude": 40.4168,
            "longitude": -3.7038,
            "timestamp_ms": base_ts + 60_000,
            "region": "madrid",
        },
    ]

    results = find_cooccurrences(
        events, spatial_threshold_m=500, temporal_threshold_s=300, min_count=1
    )
    assert results == []
