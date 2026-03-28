"""Tests for encounter_prediction module."""

from encounter_prediction import find_hotspot_encounters, predict_encounters

# -- helpers ------------------------------------------------------------------

WEEK_MS = 7 * 24 * 3600 * 1000  # one week in milliseconds

# Monday 8:00 UTC (2023-11-13) — weekday 0, hour 8
MONDAY_8AM_BASE = 1_699_862_400_000

# Wednesday 18:00 UTC (2023-11-15) — weekday 2, hour 18
WEDNESDAY_6PM_BASE = 1_700_071_200_000


def _make_routine_events(
    lat: float,
    lon: float,
    base_ts: int,
    num_weeks: int = 6,
    jitter_ms: int = 120_000,
) -> list[dict]:
    """Create events at the same dow/hour across multiple weeks.

    Adds small spatial jitter (~0.0005 degrees, ~55m) and temporal jitter
    so DBSCAN can form clusters.
    """
    events = []
    for i in range(num_weeks):
        ts = base_ts + i * WEEK_MS + (i % 3) * jitter_ms
        events.append(
            {
                "latitude": lat + (i % 3 - 1) * 0.0005,
                "longitude": lon + (i % 3 - 1) * 0.0003,
                "timestamp_ms": ts,
                "report_type": "POLICE",
            }
        )
    return events


# Madrid center: ~40.4168, -3.7038

# -- test predict_encounters --------------------------------------------------


def test_overlapping_routines_produce_encounters():
    """Alice and Bob both appear Monday 8am near Madrid, ~200m apart."""
    alice_events = _make_routine_events(40.4168, -3.7038, MONDAY_8AM_BASE, num_weeks=6)
    bob_events = _make_routine_events(40.4185, -3.7035, MONDAY_8AM_BASE, num_weeks=6)

    encounters = predict_encounters(alice_events, bob_events)

    assert len(encounters) > 0
    best = encounters[0]
    assert best["dow"] == 0  # Monday
    # hour_tolerance=1 in predict_presence means hours 7, 8, 9 can all match
    assert best["hour"] in (7, 8, 9)
    assert best["probability"] > 0
    assert best["distance_km"] < 2.0
    assert "latitude" in best
    assert "longitude" in best
    assert "evidence_a" in best
    assert "evidence_b" in best


def test_non_overlapping_routines_empty():
    """Alice on Monday 8am in Madrid, Bob on Wednesday 6pm in Barcelona."""
    alice_events = _make_routine_events(40.4168, -3.7038, MONDAY_8AM_BASE, num_weeks=6)
    # Barcelona: ~41.3851, 2.1734 — different city, different day/hour
    bob_events = _make_routine_events(41.3851, 2.1734, WEDNESDAY_6PM_BASE, num_weeks=6)

    encounters = predict_encounters(alice_events, bob_events)

    assert encounters == []


def test_results_sorted_by_probability_desc():
    """When multiple encounters exist, they're sorted by probability descending."""
    # Create events at two different time slots so we get multiple encounters
    alice_events = _make_routine_events(
        40.4168, -3.7038, MONDAY_8AM_BASE, num_weeks=6
    ) + _make_routine_events(40.4168, -3.7038, WEDNESDAY_6PM_BASE, num_weeks=6)
    bob_events = _make_routine_events(
        40.4180, -3.7035, MONDAY_8AM_BASE, num_weeks=6
    ) + _make_routine_events(40.4190, -3.7030, WEDNESDAY_6PM_BASE, num_weeks=6)

    encounters = predict_encounters(alice_events, bob_events)

    if len(encounters) > 1:
        for i in range(len(encounters) - 1):
            assert encounters[i]["probability"] >= encounters[i + 1]["probability"]


def test_empty_events_returns_empty():
    """Empty event lists return no encounters."""
    assert predict_encounters([], []) == []
    assert predict_encounters([], _make_routine_events(40.0, -3.0, MONDAY_8AM_BASE)) == []
    assert predict_encounters(_make_routine_events(40.0, -3.0, MONDAY_8AM_BASE), []) == []


# -- test find_hotspot_encounters ---------------------------------------------


def test_find_hotspot_encounters_three_users():
    """Alice+Bob nearby in Madrid, Charlie far away in Tokyo."""
    alice_events = _make_routine_events(40.4168, -3.7038, MONDAY_8AM_BASE, num_weeks=6)
    bob_events = _make_routine_events(40.4185, -3.7035, MONDAY_8AM_BASE, num_weeks=6)
    # Tokyo: ~35.6762, 139.6503 — very far away
    charlie_events = _make_routine_events(35.6762, 139.6503, MONDAY_8AM_BASE, num_weeks=6)

    user_events = {
        "alice": alice_events,
        "bob": bob_events,
        "charlie": charlie_events,
    }

    results = find_hotspot_encounters(user_events)

    # Alice+Bob should appear, charlie pairs should not (too far apart)
    assert len(results) > 0
    user_pairs = {(r["user_a"], r["user_b"]) for r in results}
    assert ("alice", "bob") in user_pairs

    # Charlie shouldn't appear with anyone (thousands of km away)
    charlie_pairs = {
        (r["user_a"], r["user_b"]) for r in results if "charlie" in (r["user_a"], r["user_b"])
    }
    assert len(charlie_pairs) == 0

    # Results sorted by probability desc
    for i in range(len(results) - 1):
        assert results[i]["probability"] >= results[i + 1]["probability"]


def test_find_hotspot_encounters_filters_by_min_events():
    """Users with fewer events than min_events_per_user are excluded."""
    alice_events = _make_routine_events(40.4168, -3.7038, MONDAY_8AM_BASE, num_weeks=6)
    # Bob has only 2 events (below default min_events_per_user=5)
    bob_events = _make_routine_events(40.4185, -3.7035, MONDAY_8AM_BASE, num_weeks=2)

    user_events = {"alice": alice_events, "bob": bob_events}

    results = find_hotspot_encounters(user_events, min_events_per_user=5)
    assert results == []


def test_find_hotspot_encounters_empty_dict():
    """Empty user_events dict returns empty list."""
    assert find_hotspot_encounters({}) == []
