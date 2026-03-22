# intel_dossier.py
"""LLM dossier generation module.

Generates natural-language intelligence dossiers from structured analysis data
using Qwen3.5 via Ollama.
"""

import logging
import re
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3.5:35b-a3b"


def build_dossier_prompt(profile: Dict) -> str:
    """Build a structured OSINT analyst prompt from a profile dict.

    Args:
        profile: Dict containing user intelligence data:
            - username, event_count, days_active, first_seen, last_seen, region
            - type_distribution (dict of type->count)
            - routines (dict with HOME/WORK keys, each with latitude, longitude, confidence)
            - peak_hours, peak_days
            - cadence_mean_hours, cadence_std_hours
            - similar_users (list of {username, similarity})
            - co_occurrence_partners (list of {username, co_count})
            - prediction (dict with day, hour, latitude, longitude, confidence)

    Returns:
        Formatted prompt string for the LLM.
    """
    username = profile.get("username", "UNKNOWN")
    event_count = profile.get("event_count", 0)
    days_active = profile.get("days_active", 0)
    first_seen = profile.get("first_seen", "N/A")
    last_seen = profile.get("last_seen", "N/A")
    region = profile.get("region", "unknown")

    # Type distribution
    type_dist = profile.get("type_distribution", {})
    type_lines = "\n".join(f"  - {t}: {c}" for t, c in type_dist.items()) or "  - No data"

    # Routines
    routines = profile.get("routines", {})
    routine_lines = []
    for label in ("HOME", "WORK"):
        r = routines.get(label)
        if r:
            routine_lines.append(
                f"  - {label}: ({r.get('latitude', 'N/A')}, {r.get('longitude', 'N/A')}) "
                f"confidence={r.get('confidence', 'N/A')}"
            )
    routine_section = "\n".join(routine_lines) or "  - No routine locations identified"

    # Temporal patterns
    peak_hours = profile.get("peak_hours", [])
    peak_days = profile.get("peak_days", [])
    cadence_mean = profile.get("cadence_mean_hours", "N/A")
    cadence_std = profile.get("cadence_std_hours", "N/A")

    # Social graph
    similar_users = profile.get("similar_users", [])
    similar_lines = (
        "\n".join(
            f"  - {u.get('username', '?')} (similarity={u.get('similarity', 'N/A')})"
            for u in similar_users
        )
        or "  - None identified"
    )

    co_partners = profile.get("co_occurrence_partners", [])
    co_lines = (
        "\n".join(
            f"  - {u.get('username', '?')} (co_count={u.get('co_count', 'N/A')})"
            for u in co_partners
        )
        or "  - None identified"
    )

    # Prediction
    prediction = profile.get("prediction", {})
    if prediction:
        pred_section = (
            f"  - Day: {prediction.get('day', 'N/A')}, Hour: {prediction.get('hour', 'N/A')}\n"
            f"  - Location: ({prediction.get('latitude', 'N/A')}, "
            f"{prediction.get('longitude', 'N/A')})\n"
            f"  - Confidence: {prediction.get('confidence', 'N/A')}"
        )
    else:
        pred_section = "  - No prediction available"

    system_instruction = (
        "You are an OSINT analyst. Write a concise intelligence "
        "dossier for the following Waze user based on their behavioral "
        "profile. Use professional intelligence language. Include "
        "assessments of patterns, routines, and risks."
    )

    closing_instruction = (
        "Write a 3-5 paragraph intelligence dossier summarizing "
        "this subject's behavioral patterns, routine locations, "
        "social connections, and predictability. Assess the "
        "confidence level of each finding. Conclude with an overall "
        "risk assessment of how trackable this subject is."
    )

    prompt = f"""{system_instruction}

## Subject Profile

**Username:** {username}
**Region:** {region}
**Event Count:** {event_count}
**Days Active:** {days_active}
**First Seen:** {first_seen}
**Last Seen:** {last_seen}

## Event Type Distribution
{type_lines}

## Identified Routine Locations
{routine_section}

## Temporal Patterns
- Peak Hours: {peak_hours}
- Peak Days: {peak_days}
- Mean Reporting Cadence: {cadence_mean} hours
- Cadence Std Dev: {cadence_std} hours

## Behaviorally Similar Users
{similar_lines}

## Co-occurrence Partners
{co_lines}

## Next Appearance Prediction
{pred_section}

---

{closing_instruction}"""

    return prompt


def parse_dossier_response(raw: str) -> str:
    """Clean LLM response by stripping Qwen3.5 thinking mode leakage.

    Args:
        raw: Raw response text from the LLM.

    Returns:
        Cleaned response text with <think>...</think> blocks removed.
    """
    # Greedy match handles nested <think> tags correctly
    cleaned = re.sub(r"<think>.*</think>", "", raw, flags=re.DOTALL)
    return cleaned.strip()


def generate_dossier(
    profile: Dict,
    model: str = DEFAULT_MODEL,
    ollama_url: str = OLLAMA_URL,
) -> Optional[str]:
    """Generate an intelligence dossier for a user profile via Ollama.

    Calls Ollama /api/chat with think=False, temperature=0.3, stream=False.

    Args:
        profile: User intelligence profile dict (see build_dossier_prompt).
        model: Ollama model name to use.
        ollama_url: Ollama API endpoint URL.

    Returns:
        Cleaned dossier text, or None on failure.
    """
    prompt = build_dossier_prompt(profile)

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "think": False,
        "stream": False,
        "options": {
            "temperature": 0.3,
        },
    }

    try:
        resp = requests.post(ollama_url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        raw_content = data.get("message", {}).get("content", "")
        if not raw_content:
            logger.warning("Empty response from Ollama for user %s", profile.get("username"))
            return None
        return parse_dossier_response(raw_content)
    except requests.RequestException as exc:
        logger.error("Ollama request failed: %s", exc)
        return None
    except (KeyError, ValueError) as exc:
        logger.error("Failed to parse Ollama response: %s", exc)
        return None
