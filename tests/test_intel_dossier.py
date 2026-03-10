# tests/test_intel_dossier.py
"""Tests for intel_dossier module.

Tests do NOT require Ollama running — only test prompt building and response parsing.
"""

from intel_dossier import build_dossier_prompt, parse_dossier_response

SAMPLE_PROFILE = {
    "username": "wazer_madrid_42",
    "event_count": 137,
    "days_active": 45,
    "first_seen": "2026-01-10T08:15:00Z",
    "last_seen": "2026-02-23T17:42:00Z",
    "region": "madrid",
    "type_distribution": {"POLICE": 80, "JAM": 40, "HAZARD": 12, "ACCIDENT": 5},
    "routines": {
        "HOME": {"latitude": 40.4530, "longitude": -3.6883, "confidence": 0.91},
        "WORK": {"latitude": 40.4168, "longitude": -3.7038, "confidence": 0.85},
    },
    "peak_hours": [8, 9, 17, 18],
    "peak_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "cadence_mean_hours": 7.8,
    "cadence_std_hours": 4.2,
    "similar_users": [
        {"username": "commuter_m30", "similarity": 0.92},
        {"username": "daily_driver_sur", "similarity": 0.87},
    ],
    "co_occurrence_partners": [
        {"username": "commuter_m30", "co_count": 14},
        {"username": "a6_morning", "co_count": 8},
    ],
    "prediction": {
        "day": "Monday",
        "hour": 8,
        "latitude": 40.4530,
        "longitude": -3.6883,
        "confidence": 0.88,
    },
}


def test_build_dossier_prompt():
    """Verify prompt contains username, event count, HOME, WORK, and is >200 chars."""
    prompt = build_dossier_prompt(SAMPLE_PROFILE)

    assert "wazer_madrid_42" in prompt
    assert "137" in prompt
    assert "HOME" in prompt
    assert "WORK" in prompt
    assert len(prompt) > 200


def test_parse_dossier_response():
    """Verify parse_dossier_response returns clean text unchanged."""
    clean_text = "Subject wazer_madrid_42 exhibits a highly regular commuting pattern."
    result = parse_dossier_response(clean_text)
    assert result == clean_text


def test_parse_dossier_strips_thinking():
    """Verify <think>...</think> blocks are stripped from LLM output."""
    raw = (
        "<think>Let me analyze this profile carefully. The user shows "
        "a strong commuting pattern based on the temporal data.</think>"
        "Subject wazer_madrid_42 exhibits a highly regular commuting pattern."
    )
    result = parse_dossier_response(raw)
    assert "<think>" not in result
    assert "</think>" not in result
    assert result == "Subject wazer_madrid_42 exhibits a highly regular commuting pattern."


def test_parse_dossier_strips_multiline_thinking():
    """Verify multi-line <think> blocks are also stripped."""
    raw = (
        "<think>\nStep 1: Analyze temporal patterns.\n"
        "Step 2: Assess routine locations.\n</think>\n"
        "Intelligence Dossier: Subject Analysis"
    )
    result = parse_dossier_response(raw)
    assert "<think>" not in result
    assert "Intelligence Dossier: Subject Analysis" in result


def test_build_dossier_prompt_minimal_profile():
    """Verify prompt generation works with a minimal/empty profile."""
    minimal = {"username": "test_user", "event_count": 0}
    prompt = build_dossier_prompt(minimal)
    assert "test_user" in prompt
    assert "0" in prompt
    assert len(prompt) > 200
