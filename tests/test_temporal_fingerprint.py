"""Tests for temporal_fingerprint module."""

from datetime import datetime, timezone

from temporal_fingerprint import (
    build_fingerprint,
    detect_identity_links,
    find_rhythm_matches,
    fingerprint_similarity,
)


def _make_events_at(username, dow, hour, count=10):
    """Create events weekly on a given day-of-week and hour.

    Base date: 2023-11-13 (a Monday). dow=0 means Monday, dow=4 means Friday, etc.
    Each subsequent event is 7 days later.
    """
    base = datetime(2023, 11, 13 + dow, hour, 0, 0, tzinfo=timezone.utc)
    base_ms = int(base.timestamp() * 1000)
    events = []
    for i in range(count):
        ts_ms = base_ms + i * 7 * 86400 * 1000
        events.append({"username": username, "timestamp_ms": ts_ms})
    return events


class TestBuildFingerprint:
    def test_length_is_168(self):
        events = _make_events_at("alice", 0, 8)
        fp = build_fingerprint(events)
        assert len(fp) == 168

    def test_normalized_sums_to_one(self):
        events = _make_events_at("alice", 0, 8)
        fp = build_fingerprint(events)
        assert abs(sum(fp) - 1.0) < 1e-9

    def test_peak_at_correct_bin(self):
        """Monday 8am should be index 0*24+8 = 8."""
        events = _make_events_at("alice", 0, 8)
        fp = build_fingerprint(events)
        peak_idx = fp.index(max(fp))
        assert peak_idx == 8

    def test_empty_events_returns_168_zeros(self):
        fp = build_fingerprint([])
        assert len(fp) == 168
        assert all(v == 0.0 for v in fp)


class TestFingerprintSimilarity:
    def test_identical_fingerprints_near_one(self):
        events = _make_events_at("alice", 0, 8)
        fp = build_fingerprint(events)
        sim = fingerprint_similarity(fp, fp)
        assert abs(sim - 1.0) < 1e-9

    def test_different_schedules_low_similarity(self):
        """Mon 8am vs Fri 8pm should be very different."""
        fp_a = build_fingerprint(_make_events_at("alice", 0, 8))
        fp_b = build_fingerprint(_make_events_at("bob", 4, 20))
        sim = fingerprint_similarity(fp_a, fp_b)
        assert sim < 0.3

    def test_same_schedules_high_similarity(self):
        """Two users both active Mon 8am should be nearly identical."""
        fp_a = build_fingerprint(_make_events_at("alice", 0, 8))
        fp_b = build_fingerprint(_make_events_at("bob", 0, 8))
        sim = fingerprint_similarity(fp_a, fp_b)
        assert sim > 0.9

    def test_zero_vector_returns_zero(self):
        fp_zero = [0.0] * 168
        fp_a = build_fingerprint(_make_events_at("alice", 0, 8))
        assert fingerprint_similarity(fp_zero, fp_a) == 0.0
        assert fingerprint_similarity(fp_a, fp_zero) == 0.0
        assert fingerprint_similarity(fp_zero, fp_zero) == 0.0


class TestFindRhythmMatches:
    def test_finds_matching_user_excludes_different(self):
        fp_alice = build_fingerprint(_make_events_at("alice", 0, 8))
        fp_bob = build_fingerprint(_make_events_at("bob", 0, 8))
        fp_charlie = build_fingerprint(_make_events_at("charlie", 4, 20))

        all_fps = {"alice": fp_alice, "bob": fp_bob, "charlie": fp_charlie}
        matches = find_rhythm_matches("alice", all_fps, threshold=0.85)

        usernames = [m["username"] for m in matches]
        assert "bob" in usernames
        assert "charlie" not in usernames

    def test_excludes_target_user(self):
        fp_alice = build_fingerprint(_make_events_at("alice", 0, 8))
        all_fps = {"alice": fp_alice}
        matches = find_rhythm_matches("alice", all_fps, threshold=0.85)
        assert len(matches) == 0


class TestDetectIdentityLinks:
    def test_finds_identity_link(self):
        fp_alice = build_fingerprint(_make_events_at("alice", 0, 8))
        fp_alt = build_fingerprint(_make_events_at("alice_alt", 0, 8))
        fp_charlie = build_fingerprint(_make_events_at("charlie", 4, 20))

        all_fps = {"alice": fp_alice, "alice_alt": fp_alt, "charlie": fp_charlie}
        links = detect_identity_links(all_fps, threshold=0.90)

        pairs = [(lnk["user_a"], lnk["user_b"]) for lnk in links]
        assert ("alice", "alice_alt") in pairs
        # charlie shouldn't be linked to either
        charlie_links = [lnk for lnk in links if "charlie" in (lnk["user_a"], lnk["user_b"])]
        assert len(charlie_links) == 0

    def test_canonical_ordering(self):
        fp_a = build_fingerprint(_make_events_at("zara", 0, 8))
        fp_b = build_fingerprint(_make_events_at("anna", 0, 8))

        all_fps = {"zara": fp_a, "anna": fp_b}
        links = detect_identity_links(all_fps, threshold=0.90)

        assert len(links) == 1
        assert links[0]["user_a"] == "anna"
        assert links[0]["user_b"] == "zara"

    def test_sorted_by_similarity_desc(self):
        fp_a = build_fingerprint(_make_events_at("a", 0, 8))
        fp_b = build_fingerprint(_make_events_at("b", 0, 8))
        fp_c = build_fingerprint(
            _make_events_at("c", 0, 8, count=8) + _make_events_at("c", 0, 9, count=2)
        )

        all_fps = {"a": fp_a, "b": fp_b, "c": fp_c}
        links = detect_identity_links(all_fps, threshold=0.90)

        for i in range(len(links) - 1):
            assert links[i]["similarity"] >= links[i + 1]["similarity"]
