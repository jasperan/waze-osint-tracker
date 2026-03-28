"""Temporal fingerprinting: 168-bin weekly activity histograms for user schedule matching."""

import math
from datetime import datetime, timezone

BINS = 168  # 7 days x 24 hours


def build_fingerprint(events):
    """Build a 168-bin normalized activity histogram from events.

    Each bin corresponds to (day_of_week * 24 + hour_of_day), where
    day_of_week uses Monday=0 (Python's datetime.weekday()).

    Args:
        events: list of dicts, each with a 'timestamp_ms' key (epoch millis).

    Returns:
        List of 168 floats summing to 1.0, or all zeros if no events.
    """
    histogram = [0.0] * BINS

    for event in events:
        ts_ms = event.get("timestamp_ms")
        if ts_ms is None:
            continue
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        dow = dt.weekday()  # 0=Monday
        hour = dt.hour
        idx = dow * 24 + hour
        histogram[idx] += 1.0

    total = sum(histogram)
    if total == 0:
        return histogram

    return [v / total for v in histogram]


def fingerprint_similarity(fp_a, fp_b):
    """Cosine similarity between two fingerprint vectors.

    Returns 0.0 if either vector has zero magnitude.
    """
    dot = sum(a * b for a, b in zip(fp_a, fp_b))
    mag_a = math.sqrt(sum(a * a for a in fp_a))
    mag_b = math.sqrt(sum(b * b for b in fp_b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    return dot / (mag_a * mag_b)


def find_rhythm_matches(target_user, all_fingerprints, threshold=0.85):
    """Find users whose temporal fingerprint is similar to target_user.

    Args:
        target_user: username string to compare against.
        all_fingerprints: dict of {username: [168 floats]}.
        threshold: minimum cosine similarity to include.

    Returns:
        List of {username, similarity} dicts, sorted by similarity desc.
        Excludes target_user from results.
    """
    target_fp = all_fingerprints.get(target_user)
    if target_fp is None:
        return []

    matches = []
    for username, fp in all_fingerprints.items():
        if username == target_user:
            continue
        sim = fingerprint_similarity(target_fp, fp)
        if sim >= threshold:
            matches.append({"username": username, "similarity": sim})

    matches.sort(key=lambda m: m["similarity"], reverse=True)
    return matches


def detect_identity_links(all_fingerprints, threshold=0.90):
    """Find all user pairs whose fingerprints exceed the similarity threshold.

    Args:
        all_fingerprints: dict of {username: [168 floats]}.
        threshold: minimum cosine similarity to include.

    Returns:
        List of {user_a, user_b, similarity} dicts, sorted by similarity desc.
        User pairs use canonical ordering (sorted usernames).
    """
    usernames = sorted(all_fingerprints.keys())
    links = []

    for i in range(len(usernames)):
        for j in range(i + 1, len(usernames)):
            u_a, u_b = usernames[i], usernames[j]
            sim = fingerprint_similarity(all_fingerprints[u_a], all_fingerprints[u_b])
            if sim >= threshold:
                links.append({"user_a": u_a, "user_b": u_b, "similarity": sim})

    links.sort(key=lambda entry: entry["similarity"], reverse=True)
    return links
