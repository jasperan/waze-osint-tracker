"""Privacy risk scoring — quantifies how much private information Waze leaks about a user.

Computes a composite 0-100 score from six sub-scores:
  - home_exposure (25%): Can the user's home location be inferred?
  - work_exposure (20%): Can the user's work location be inferred?
  - schedule_predictability (20%): How predictable is the user's schedule?
  - route_reconstructability (15%): Can driving routes be reconstructed?
  - identity_linkage (10%): Can the user be linked to other accounts?
  - trackability (10%): How recently and frequently does the user report?
"""

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# Sub-score weights (must sum to 1.0)
WEIGHTS = {
    "home_exposure": 0.25,
    "work_exposure": 0.20,
    "schedule_predictability": 0.20,
    "route_reconstructability": 0.15,
    "identity_linkage": 0.10,
    "trackability": 0.10,
}

# Risk level thresholds
RISK_LEVELS = [
    (0, 25, "LOW"),
    (26, 50, "MODERATE"),
    (51, 75, "HIGH"),
    (76, 100, "CRITICAL"),
]


def _shannon_entropy(histogram: List[float]) -> float:
    """Normalized Shannon entropy of a probability distribution.

    Returns a value in [0, 1] where 0 = perfectly concentrated (one bin has all
    the probability) and 1 = perfectly uniform (all bins equal).
    """
    if not histogram:
        return 1.0

    n_bins = len(histogram)
    if n_bins <= 1:
        return 0.0

    max_entropy = math.log2(n_bins)
    if max_entropy == 0:
        return 0.0

    entropy = 0.0
    for p in histogram:
        if p > 0:
            entropy -= p * math.log2(p)

    return entropy / max_entropy


def compute_home_exposure(routines: Optional[Dict]) -> Tuple[float, Dict]:
    """Score how inferrable the user's home location is.

    Parameters
    ----------
    routines : dict or None
        Output from infer_routines(). Looks for 'HOME' key.

    Returns
    -------
    (score, details) where score is 0-100 and details is a dict.
    """
    if not routines or "HOME" not in routines:
        return 0.0, {"inferred": False}

    home = routines["HOME"]
    confidence = home.get("confidence", 0)
    evidence = home.get("evidence_count", 0)

    # Base score from confidence
    score = confidence * 80

    # Boost for strong evidence (>10 night events is very reliable)
    if evidence >= 10:
        score += 15
    elif evidence >= 5:
        score += 8

    score = min(score, 100.0)

    return round(score, 2), {
        "inferred": True,
        "latitude": home.get("latitude"),
        "longitude": home.get("longitude"),
        "confidence": round(confidence, 4),
        "evidence_count": evidence,
    }


def compute_work_exposure(routines: Optional[Dict]) -> Tuple[float, Dict]:
    """Score how inferrable the user's work location is.

    Parameters
    ----------
    routines : dict or None
        Output from infer_routines(). Looks for 'WORK' key.

    Returns
    -------
    (score, details) where score is 0-100.
    """
    if not routines or "WORK" not in routines:
        return 0.0, {"inferred": False}

    work = routines["WORK"]
    confidence = work.get("confidence", 0)
    evidence = work.get("evidence_count", 0)

    score = confidence * 80
    if evidence >= 10:
        score += 15
    elif evidence >= 5:
        score += 8

    score = min(score, 100.0)

    return round(score, 2), {
        "inferred": True,
        "latitude": work.get("latitude"),
        "longitude": work.get("longitude"),
        "confidence": round(confidence, 4),
        "evidence_count": evidence,
    }


def compute_schedule_predictability(
    hour_histogram: List[float],
    dow_histogram: List[float],
) -> Tuple[float, Dict]:
    """Score how predictable the user's reporting schedule is.

    Low entropy = concentrated activity = predictable = high risk.

    Parameters
    ----------
    hour_histogram : list[float]
        24-bin normalized histogram of reporting hours.
    dow_histogram : list[float]
        7-bin normalized histogram of reporting days.

    Returns
    -------
    (score, details) where score is 0-100.
    """
    hour_entropy = _shannon_entropy(hour_histogram)
    dow_entropy = _shannon_entropy(dow_histogram)

    # Invert: low entropy = high predictability = high score
    hour_score = (1 - hour_entropy) * 100
    dow_score = (1 - dow_entropy) * 100

    # Weighted average (hour matters more than day)
    score = hour_score * 0.6 + dow_score * 0.4

    # Find peak hours and days
    peak_hours = []
    if hour_histogram:
        threshold = max(hour_histogram) * 0.5
        peak_hours = [h for h, v in enumerate(hour_histogram) if v >= threshold]

    peak_days = []
    if dow_histogram:
        threshold = max(dow_histogram) * 0.5
        peak_days = [d for d, v in enumerate(dow_histogram) if v >= threshold]

    return round(score, 2), {
        "hour_entropy": round(hour_entropy, 4),
        "dow_entropy": round(dow_entropy, 4),
        "peak_hours": peak_hours,
        "peak_days": peak_days,
    }


def compute_route_reconstructability(
    events: List[Dict],
    max_gap_s: int = 7200,
    max_speed_kmh: float = 200.0,
) -> Tuple[float, Dict]:
    """Score how many consecutive event pairs form plausible driving segments.

    Parameters
    ----------
    events : list[dict]
        Must have latitude, longitude, timestamp_ms.
    max_gap_s : int
        Maximum gap in seconds for a plausible driving segment.
    max_speed_kmh : float
        Maximum plausible driving speed.

    Returns
    -------
    (score, details) where score is 0-100.
    """
    if len(events) < 2:
        return 0.0, {"pairs_total": 0, "pairs_drivable": 0, "ratio": 0}

    sorted_events = sorted(events, key=lambda e: e["timestamp_ms"])

    pairs_total = len(sorted_events) - 1
    pairs_drivable = 0

    for i in range(pairs_total):
        e1, e2 = sorted_events[i], sorted_events[i + 1]
        gap_s = (e2["timestamp_ms"] - e1["timestamp_ms"]) / 1000.0

        if gap_s <= 0 or gap_s > max_gap_s:
            continue

        # Haversine distance
        dlat = math.radians(e2["latitude"] - e1["latitude"])
        dlon = math.radians(e2["longitude"] - e1["longitude"])
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(e1["latitude"]))
            * math.cos(math.radians(e2["latitude"]))
            * math.sin(dlon / 2) ** 2
        )
        dist_km = 2 * 6371.0 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        speed_kmh = (dist_km / gap_s) * 3600 if gap_s > 0 else 0
        if 0 < speed_kmh <= max_speed_kmh:
            pairs_drivable += 1

    ratio = pairs_drivable / pairs_total if pairs_total > 0 else 0
    score = ratio * 100

    return round(score, 2), {
        "pairs_total": pairs_total,
        "pairs_drivable": pairs_drivable,
        "ratio": round(ratio, 4),
    }


def compute_identity_linkage(
    correlations: Optional[List[Dict]],
) -> Tuple[float, Dict]:
    """Score how strongly the user can be linked to other accounts.

    Parameters
    ----------
    correlations : list[dict] or None
        Each dict should have 'combined_score' and optionally 'correlation_type',
        'user_a', 'user_b'.

    Returns
    -------
    (score, details) where score is 0-100.
    """
    if not correlations:
        return 0.0, {"max_correlation": 0, "linked_users": 0}

    max_score = max(c.get("combined_score", 0) for c in correlations)
    linked_count = sum(1 for c in correlations if c.get("combined_score", 0) > 0.3)

    # Primary score from max correlation
    score = max_score * 100

    # Small boost for multiple linked accounts
    if linked_count > 1:
        score = min(score + linked_count * 3, 100)

    top_match = None
    if correlations:
        best = max(correlations, key=lambda c: c.get("combined_score", 0))
        partner = best.get("user_b", best.get("user_a", "unknown"))
        top_match = {
            "username": partner,
            "score": round(best.get("combined_score", 0), 4),
            "type": best.get("correlation_type", "unknown"),
        }

    return round(score, 2), {
        "max_correlation": round(max_score, 4),
        "linked_users": linked_count,
        "top_match": top_match,
    }


def compute_trackability(
    events: List[Dict],
    now_ms: Optional[int] = None,
) -> Tuple[float, Dict]:
    """Score how trackable the user is based on recency and frequency.

    Parameters
    ----------
    events : list[dict]
        Must have timestamp_ms.
    now_ms : int or None
        Current time in ms. Uses current UTC if None.

    Returns
    -------
    (score, details) where score is 0-100.
    """
    if not events:
        return 0.0, {"last_seen_hours_ago": None, "avg_reports_per_day": 0}

    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    timestamps = sorted(e["timestamp_ms"] for e in events)
    last_ts = timestamps[-1]
    first_ts = timestamps[0]

    # Recency: decay over 7 days
    hours_ago = (now_ms - last_ts) / 3_600_000
    if hours_ago <= 0:
        recency_score = 100
    elif hours_ago <= 24:
        recency_score = 90
    elif hours_ago <= 72:
        recency_score = 70
    elif hours_ago <= 168:  # 7 days
        recency_score = 40
    else:
        recency_score = max(0, 20 - (hours_ago - 168) / 24)

    # Frequency: reports per day
    span_days = max((last_ts - first_ts) / 86_400_000, 1)
    reports_per_day = len(events) / span_days

    if reports_per_day >= 5:
        freq_score = 100
    elif reports_per_day >= 2:
        freq_score = 80
    elif reports_per_day >= 1:
        freq_score = 60
    elif reports_per_day >= 0.5:
        freq_score = 40
    else:
        freq_score = max(0, reports_per_day * 80)

    # Combined: recency matters more
    score = recency_score * 0.6 + freq_score * 0.4

    return round(min(score, 100), 2), {
        "last_seen_hours_ago": round(hours_ago, 1),
        "avg_reports_per_day": round(reports_per_day, 2),
        "recency_score": round(recency_score, 2),
        "frequency_score": round(freq_score, 2),
    }


def compute_privacy_score(
    events: List[Dict],
    routines: Optional[Dict] = None,
    hour_histogram: Optional[List[float]] = None,
    dow_histogram: Optional[List[float]] = None,
    correlations: Optional[List[Dict]] = None,
    now_ms: Optional[int] = None,
) -> Dict:
    """Compute the full privacy risk score for a user.

    Parameters
    ----------
    events : list[dict]
        User's events with latitude, longitude, timestamp_ms, report_type.
    routines : dict or None
        Output from infer_routines(). HOME/WORK/COMMUTE keys.
    hour_histogram : list[float] or None
        24-bin normalized histogram. Built from events if None.
    dow_histogram : list[float] or None
        7-bin normalized histogram. Built from events if None.
    correlations : list[dict] or None
        Identity correlation records for this user.
    now_ms : int or None
        Current time in ms for trackability scoring.

    Returns
    -------
    dict with keys: overall_score, risk_level, sub_scores (dict of name -> score),
    details (dict of name -> detail dict), weights.
    """
    # Build histograms from events if not provided
    if hour_histogram is None:
        hours = []
        for e in events:
            dt = datetime.fromtimestamp(e["timestamp_ms"] / 1000, tz=timezone.utc)
            hours.append(dt.hour)
        hour_histogram = _build_histogram(hours, 24)

    if dow_histogram is None:
        dows = []
        for e in events:
            dt = datetime.fromtimestamp(e["timestamp_ms"] / 1000, tz=timezone.utc)
            dows.append(dt.weekday())
        dow_histogram = _build_histogram(dows, 7)

    # Compute sub-scores
    home_score, home_details = compute_home_exposure(routines)
    work_score, work_details = compute_work_exposure(routines)
    sched_score, sched_details = compute_schedule_predictability(hour_histogram, dow_histogram)
    route_score, route_details = compute_route_reconstructability(events)
    identity_score, identity_details = compute_identity_linkage(correlations)
    track_score, track_details = compute_trackability(events, now_ms)

    sub_scores = {
        "home_exposure": home_score,
        "work_exposure": work_score,
        "schedule_predictability": sched_score,
        "route_reconstructability": route_score,
        "identity_linkage": identity_score,
        "trackability": track_score,
    }

    details = {
        "home_exposure": home_details,
        "work_exposure": work_details,
        "schedule_predictability": sched_details,
        "route_reconstructability": route_details,
        "identity_linkage": identity_details,
        "trackability": track_details,
    }

    # Weighted composite
    overall = sum(sub_scores[k] * WEIGHTS[k] for k in WEIGHTS)
    overall = round(min(overall, 100), 2)

    # Risk level
    risk_level = "LOW"
    for low, high, level in RISK_LEVELS:
        if low <= overall <= high:
            risk_level = level
            break

    return {
        "overall_score": overall,
        "risk_level": risk_level,
        "sub_scores": sub_scores,
        "details": details,
        "weights": WEIGHTS,
    }


def _build_histogram(values: List[int], n_bins: int) -> List[float]:
    """Build a normalized histogram from integer values."""
    hist = [0.0] * n_bins
    for v in values:
        if 0 <= v < n_bins:
            hist[v] += 1.0
    total = sum(hist)
    if total > 0:
        hist = [v / total for v in hist]
    return hist


def format_privacy_report(username: str, result: Dict) -> str:
    """Format a privacy score result as a human-readable text report.

    Parameters
    ----------
    username : str
    result : dict
        Output from compute_privacy_score().

    Returns
    -------
    str with the formatted report.
    """
    overall = result["overall_score"]
    level = result["risk_level"]
    sub = result["sub_scores"]
    det = result["details"]

    def bar(score, width=20):
        filled = int(score / 100 * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    lines = [
        f"Privacy Risk Score: {overall:.0f}/100 [{level}]",
        "",
    ]

    # Home
    lines.append(f"  Home Location     {bar(sub['home_exposure'])} {sub['home_exposure']:.0f}/100")
    if det["home_exposure"].get("inferred"):
        h = det["home_exposure"]
        lines.append(
            f"    Inferred: {h['latitude']:.4f}, {h['longitude']:.4f} "
            f"(confidence: {h['confidence']:.2f}, {h['evidence_count']} night events)"
        )
    else:
        lines.append("    Not enough data to infer home location")

    # Work
    lines.append(
        f"\n  Work Location     {bar(sub['work_exposure'])} {sub['work_exposure']:.0f}/100"
    )
    if det["work_exposure"].get("inferred"):
        w = det["work_exposure"]
        lines.append(
            f"    Inferred: {w['latitude']:.4f}, {w['longitude']:.4f} "
            f"(confidence: {w['confidence']:.2f}, {w['evidence_count']} weekday events)"
        )
    else:
        lines.append("    Not enough data to infer work location")

    # Schedule
    lines.append(
        f"\n  Schedule          {bar(sub['schedule_predictability'])} "
        f"{sub['schedule_predictability']:.0f}/100"
    )
    s = det["schedule_predictability"]
    peak_h = ", ".join(f"{h}:00" for h in s.get("peak_hours", [])[:5])
    lines.append(f"    Peak hours: {peak_h or 'N/A'} (entropy: {s['hour_entropy']:.2f})")

    # Routes
    lines.append(
        f"\n  Routes            {bar(sub['route_reconstructability'])} "
        f"{sub['route_reconstructability']:.0f}/100"
    )
    r = det["route_reconstructability"]
    lines.append(
        f"    {r['pairs_drivable']} of {r['pairs_total']} consecutive event pairs "
        f"form plausible driving segments"
    )

    # Identity
    lines.append(
        f"\n  Identity Linkage  {bar(sub['identity_linkage'])} {sub['identity_linkage']:.0f}/100"
    )
    i = det["identity_linkage"]
    if i.get("top_match"):
        m = i["top_match"]
        lines.append(
            f"    Highest correlation: {m['username']} (score: {m['score']:.2f}, type: {m['type']})"
        )
    else:
        lines.append("    No identity correlations found")

    # Trackability
    lines.append(f"\n  Trackability      {bar(sub['trackability'])} {sub['trackability']:.0f}/100")
    t = det["trackability"]
    last = t.get("last_seen_hours_ago")
    last_str = f"{last:.0f} hours ago" if last is not None else "unknown"
    lines.append(
        f"    Last seen: {last_str} | Avg frequency: {t['avg_reports_per_day']:.1f} reports/day"
    )

    return "\n".join(lines)
