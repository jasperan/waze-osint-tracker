"""Tests for privacy risk scoring module."""

from privacy_score import (
    WEIGHTS,
    _build_histogram,
    _shannon_entropy,
    compute_home_exposure,
    compute_identity_linkage,
    compute_privacy_score,
    compute_route_reconstructability,
    compute_schedule_predictability,
    compute_trackability,
    compute_work_exposure,
    format_privacy_report,
)

# --- Fixtures ---


def _make_event(lat, lon, ts_ms, report_type="POLICE"):
    return {
        "latitude": lat,
        "longitude": lon,
        "timestamp_ms": ts_ms,
        "report_type": report_type,
    }


def _predictable_events():
    """Events concentrated at 8am and 5pm on weekdays — very predictable."""
    events = []
    base = 1700000000000  # a Monday
    for day in range(5):  # Mon-Fri
        # Morning event at ~8:00 UTC
        ts = base + day * 86_400_000 + 8 * 3_600_000
        events.append(_make_event(40.42, -3.70, ts, "POLICE"))
        # Evening event at ~17:00 UTC
        ts = base + day * 86_400_000 + 17 * 3_600_000
        events.append(_make_event(40.38, -3.72, ts, "JAM"))
    return events


def _scattered_events():
    """Events spread across all hours and days — low predictability."""
    events = []
    base = 1700000000000
    for i in range(48):  # 48 events over 48 hours
        ts = base + i * 3_600_000  # one per hour
        lat = 40.0 + (i % 10) * 0.05
        lon = -3.0 - (i % 8) * 0.03
        events.append(_make_event(lat, lon, ts))
    return events


# --- Shannon Entropy ---


class TestShannonEntropy:
    def test_uniform_distribution(self):
        hist = [1 / 24] * 24
        e = _shannon_entropy(hist)
        assert abs(e - 1.0) < 0.01  # max entropy

    def test_concentrated_distribution(self):
        hist = [0.0] * 24
        hist[8] = 1.0  # all mass at 8am
        e = _shannon_entropy(hist)
        assert e == 0.0  # zero entropy

    def test_partial_concentration(self):
        hist = [0.0] * 24
        hist[8] = 0.5
        hist[17] = 0.5  # split between 8am and 5pm
        e = _shannon_entropy(hist)
        assert 0.1 < e < 0.4  # low entropy

    def test_empty_histogram(self):
        assert _shannon_entropy([]) == 1.0

    def test_single_bin(self):
        assert _shannon_entropy([1.0]) == 0.0


# --- Home Exposure ---


class TestHomeExposure:
    def test_no_routines(self):
        score, details = compute_home_exposure(None)
        assert score == 0.0
        assert details["inferred"] is False

    def test_no_home_routine(self):
        score, _ = compute_home_exposure({"WORK": {"latitude": 40.0, "longitude": -3.0}})
        assert score == 0.0

    def test_high_confidence_home(self):
        routines = {
            "HOME": {
                "latitude": 40.38,
                "longitude": -3.72,
                "confidence": 0.9,
                "evidence_count": 15,
            }
        }
        score, details = compute_home_exposure(routines)
        assert score > 80
        assert details["inferred"] is True
        assert details["latitude"] == 40.38

    def test_low_confidence_home(self):
        routines = {
            "HOME": {
                "latitude": 40.38,
                "longitude": -3.72,
                "confidence": 0.2,
                "evidence_count": 3,
            }
        }
        score, _ = compute_home_exposure(routines)
        assert score < 30


# --- Work Exposure ---


class TestWorkExposure:
    def test_no_routines(self):
        score, _ = compute_work_exposure(None)
        assert score == 0.0

    def test_high_confidence_work(self):
        routines = {
            "WORK": {
                "latitude": 40.46,
                "longitude": -3.69,
                "confidence": 0.85,
                "evidence_count": 20,
            }
        }
        score, details = compute_work_exposure(routines)
        assert score > 75
        assert details["inferred"] is True


# --- Schedule Predictability ---


class TestSchedulePredictability:
    def test_perfectly_predictable(self):
        hour_hist = [0.0] * 24
        hour_hist[8] = 1.0
        dow_hist = [0.2] * 5 + [0.0, 0.0]  # weekdays only
        score, details = compute_schedule_predictability(hour_hist, dow_hist)
        assert score > 60  # very predictable

    def test_perfectly_random(self):
        hour_hist = [1 / 24] * 24
        dow_hist = [1 / 7] * 7
        score, _ = compute_schedule_predictability(hour_hist, dow_hist)
        assert score < 5  # near zero

    def test_has_peak_hours(self):
        hour_hist = [0.0] * 24
        hour_hist[8] = 0.5
        hour_hist[17] = 0.5
        dow_hist = [1 / 7] * 7
        _, details = compute_schedule_predictability(hour_hist, dow_hist)
        assert 8 in details["peak_hours"]
        assert 17 in details["peak_hours"]


# --- Route Reconstructability ---


class TestRouteReconstructability:
    def test_consecutive_drivable_pairs(self):
        events = []
        base = 1700000000000
        for i in range(5):
            events.append(
                _make_event(40.0 + i * 0.01, -3.0, base + i * 600_000)
            )  # 10 min apart, ~1km
        score, details = compute_route_reconstructability(events)
        assert score > 50
        assert details["pairs_drivable"] > 0

    def test_too_few_events(self):
        events = [_make_event(40.0, -3.0, 1000)]
        score, _ = compute_route_reconstructability(events)
        assert score == 0.0

    def test_teleporting_events(self):
        """Events too far apart for the time gap — should not count as drivable."""
        events = [
            _make_event(40.0, -3.0, 1000000),
            _make_event(50.0, 10.0, 1060000),  # 1000 km in 60 seconds
        ]
        score, details = compute_route_reconstructability(events)
        assert details["pairs_drivable"] == 0


# --- Identity Linkage ---


class TestIdentityLinkage:
    def test_no_correlations(self):
        score, _ = compute_identity_linkage(None)
        assert score == 0.0

    def test_high_correlation(self):
        correlations = [
            {
                "user_a": "alice",
                "user_b": "bob",
                "combined_score": 0.85,
                "correlation_type": "SAME_PERSON",
            }
        ]
        score, details = compute_identity_linkage(correlations)
        assert score > 80
        assert details["top_match"]["username"] == "bob"

    def test_multiple_weak_correlations(self):
        correlations = [
            {"user_b": "bob", "combined_score": 0.35, "correlation_type": "SIMILAR_ROUTINE"},
            {"user_b": "carol", "combined_score": 0.32, "correlation_type": "WEAK_MATCH"},
        ]
        score, details = compute_identity_linkage(correlations)
        assert details["linked_users"] == 2


# --- Trackability ---


class TestTrackability:
    def test_recent_active_user(self):
        now_ms = 1700100000000
        events = [
            _make_event(40.0, -3.0, now_ms - 3_600_000),  # 1 hour ago
            _make_event(40.0, -3.0, now_ms - 7_200_000),  # 2 hours ago
            _make_event(40.0, -3.0, now_ms - 10_800_000),  # 3 hours ago
        ]
        score, details = compute_trackability(events, now_ms=now_ms)
        assert score > 70
        assert details["last_seen_hours_ago"] < 2

    def test_stale_user(self):
        now_ms = 1700100000000
        events = [
            _make_event(40.0, -3.0, now_ms - 30 * 86_400_000),  # 30 days ago
        ]
        score, details = compute_trackability(events, now_ms=now_ms)
        assert score < 25

    def test_empty_events(self):
        score, _ = compute_trackability([])
        assert score == 0.0


# --- Full Privacy Score ---


class TestComputePrivacyScore:
    def test_full_score_with_all_data(self):
        events = _predictable_events()
        routines = {
            "HOME": {
                "latitude": 40.38,
                "longitude": -3.72,
                "confidence": 0.9,
                "evidence_count": 15,
            },
            "WORK": {
                "latitude": 40.46,
                "longitude": -3.69,
                "confidence": 0.8,
                "evidence_count": 12,
            },
        }
        correlations = [{"user_b": "bob", "combined_score": 0.5, "correlation_type": "CONVOY"}]
        now_ms = events[-1]["timestamp_ms"] + 3_600_000  # 1 hour after last event

        result = compute_privacy_score(
            events=events,
            routines=routines,
            correlations=correlations,
            now_ms=now_ms,
        )

        assert 0 <= result["overall_score"] <= 100
        assert result["risk_level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
        assert len(result["sub_scores"]) == 6
        assert len(result["details"]) == 6

    def test_minimal_data(self):
        events = [_make_event(40.0, -3.0, 1000)]
        result = compute_privacy_score(events=events)
        assert result["overall_score"] >= 0
        assert result["risk_level"] == "LOW"

    def test_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 0.001

    def test_high_risk_user(self):
        """A user with strong routines, predictable schedule, recent activity."""
        events = _predictable_events()
        routines = {
            "HOME": {
                "latitude": 40.38,
                "longitude": -3.72,
                "confidence": 0.95,
                "evidence_count": 25,
            },
            "WORK": {
                "latitude": 40.46,
                "longitude": -3.69,
                "confidence": 0.9,
                "evidence_count": 20,
            },
        }
        correlations = [
            {"user_b": "alt_account", "combined_score": 0.9, "correlation_type": "SAME_PERSON"}
        ]
        now_ms = events[-1]["timestamp_ms"] + 1_800_000

        result = compute_privacy_score(
            events=events,
            routines=routines,
            correlations=correlations,
            now_ms=now_ms,
        )
        assert result["overall_score"] > 60
        assert result["risk_level"] in ("HIGH", "CRITICAL")

    def test_low_risk_user(self):
        """User with scattered activity, no routines, no correlations."""
        events = _scattered_events()
        now_ms = events[-1]["timestamp_ms"] + 30 * 86_400_000  # 30 days later

        result = compute_privacy_score(events=events, now_ms=now_ms)
        assert result["overall_score"] < 40


# --- Report Formatting ---


class TestFormatReport:
    def test_report_contains_score(self):
        events = _predictable_events()
        result = compute_privacy_score(events=events)
        report = format_privacy_report("testuser", result)
        assert "Privacy Risk Score:" in report
        assert "/100" in report

    def test_report_contains_all_sections(self):
        events = _predictable_events()
        routines = {
            "HOME": {
                "latitude": 40.38,
                "longitude": -3.72,
                "confidence": 0.8,
                "evidence_count": 10,
            },
        }
        result = compute_privacy_score(events=events, routines=routines)
        report = format_privacy_report("testuser", result)
        assert "Home Location" in report
        assert "Work Location" in report
        assert "Schedule" in report
        assert "Routes" in report
        assert "Identity Linkage" in report
        assert "Trackability" in report


# --- Histogram Builder ---


class TestBuildHistogram:
    def test_basic(self):
        hist = _build_histogram([0, 0, 1, 1, 1], 3)
        assert len(hist) == 3
        assert abs(hist[0] - 0.4) < 0.01
        assert abs(hist[1] - 0.6) < 0.01

    def test_empty(self):
        hist = _build_histogram([], 24)
        assert all(v == 0.0 for v in hist)

    def test_normalized(self):
        hist = _build_histogram([0, 1, 2, 3, 4, 5], 6)
        assert abs(sum(hist) - 1.0) < 0.001
