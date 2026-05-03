"""Build comprehensive OSINT dossier by fusing all intelligence modules."""

import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _trip_to_template_dict(trip: Any) -> dict[str, Any]:
    """Return a trip dict with legacy template aliases."""
    if isinstance(trip, dict):
        data = dict(trip)
    elif hasattr(trip, "to_dict"):
        data = trip.to_dict()
    else:
        data = {
            "started_at": getattr(trip, "started_at", ""),
            "ended_at": getattr(trip, "ended_at", ""),
            "distance_km": getattr(trip, "distance_km", 0),
            "duration_minutes": getattr(trip, "duration_minutes", 0),
            "trip_type": getattr(trip, "trip_type", ""),
        }

    data.setdefault("start_time", data.get("started_at", ""))
    data.setdefault("end_time", data.get("ended_at", ""))
    data.setdefault("duration_min", data.get("duration_minutes", 0))
    data.setdefault("label", data.get("trip_type", ""))
    return data


def _format_anomaly_sections(result: dict[str, Any]) -> dict[str, Any]:
    """Add template-friendly grouped anomaly summaries to detector output."""
    grouped: dict[str, list[str]] = {
        "time_anomalies": [],
        "location_anomalies": [],
        "frequency_anomalies": [],
    }
    for anomaly in result.get("anomalies", []):
        kind = anomaly.get("type", "unknown")
        details = anomaly.get("details", {})
        score = anomaly.get("score", 0)
        summary = f"{kind} anomaly score={score}: {details}"
        if kind == "time":
            grouped["time_anomalies"].append(summary)
        elif kind == "location":
            grouped["location_anomalies"].append(summary)
        elif kind == "frequency":
            grouped["frequency_anomalies"].append(summary)

    return {**result, **grouped}


def _build_ai_profile(
    username: str,
    events: list[dict[str, Any]],
    dossier: dict[str, Any],
    routines: dict[str, Any],
) -> dict[str, Any]:
    """Build the profile shape expected by intel_dossier.generate_dossier."""
    timestamps = [e.get("timestamp_utc") for e in events if e.get("timestamp_utc")]
    type_distribution = Counter(str(e.get("report_type", "UNKNOWN")) for e in events)
    privacy_score = dossier.get("privacy_score") or {}
    schedule = (privacy_score.get("details") or {}).get("schedule_predictability", {})
    social = dossier.get("social") or {}
    report = dossier.get("report") or {}

    co_occurrence_partners = []
    for edge in social.get("top_connections", []):
        source = edge.get("source")
        target = edge.get("target")
        other = target if source == username else source
        if other:
            co_occurrence_partners.append({"username": other, "co_count": edge.get("weight", 0)})

    return {
        "username": username,
        "event_count": len(events),
        "days_active": report.get("active_days", 0),
        "first_seen": min(timestamps) if timestamps else "N/A",
        "last_seen": max(timestamps) if timestamps else "N/A",
        "region": events[0].get("region", events[0].get("grid_cell", "unknown"))
        if events
        else "unknown",
        "type_distribution": dict(type_distribution),
        "routines": routines,
        "peak_hours": schedule.get("peak_hours", []),
        "peak_days": schedule.get("peak_days", []),
        "cadence_mean_hours": "N/A",
        "cadence_std_hours": "N/A",
        "similar_users": [],
        "co_occurrence_partners": co_occurrence_partners,
        "prediction": {},
    }


def build_dossier(username: str, db) -> dict[str, Any]:
    """Build a complete intelligence dossier for username from db.

    Calls each intel module with try/except so partial failures
    don't break the whole report. Returns a dict with all sections.
    """
    rows = db.execute(
        "SELECT * FROM events WHERE username = ? ORDER BY timestamp_ms DESC",
        (username,),
    ).fetchall()
    events: list[dict[str, Any]] = [dict(r) for r in rows]

    dossier: dict[str, Any] = {
        "username": username,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(events),
    }

    routines: dict[str, Any] = {}
    try:
        from intel_routines import infer_routines

        routines = infer_routines(events)
    except Exception as e:
        logger.warning("Routine inference failed: %s", e)

    # 1. Basic report
    try:
        from report_generator import generate_user_report

        dossier["report"] = generate_user_report(username, db)
    except Exception as e:
        logger.warning("Report generation failed: %s", e)
        dossier["report"] = None

    # 2. Privacy score
    try:
        from privacy_score import compute_privacy_score

        dossier["privacy_score"] = compute_privacy_score(events=events, routines=routines)
    except Exception as e:
        logger.warning("Privacy score failed: %s", e)
        dossier["privacy_score"] = None

    # 3. Trip reconstruction
    try:
        from trip_reconstruction import reconstruct_trips

        trips = reconstruct_trips(events, username, routines=routines)
        dossier["trips"] = [_trip_to_template_dict(trip) for trip in trips]
    except Exception as e:
        logger.warning("Trip reconstruction failed: %s", e)
        dossier["trips"] = None

    # 4. Social graph (top connections only)
    try:
        from social_graph import build_social_graph, detect_communities

        graph = build_social_graph(events)
        communities = detect_communities(graph)
        user_edges = [
            e
            for e in graph.get("edges", [])
            if e.get("source") == username or e.get("target") == username
        ]
        user_edges.sort(key=lambda e: e.get("weight", 0), reverse=True)
        dossier["social"] = {
            "total_connections": len(user_edges),
            "community_id": communities.get(username),
            "top_connections": user_edges[:10],
        }
    except Exception as e:
        logger.warning("Social graph failed: %s", e)
        dossier["social"] = None

    # 5. Temporal fingerprint
    try:
        from temporal_fingerprint import build_fingerprint

        dossier["fingerprint"] = build_fingerprint(events)
    except Exception as e:
        logger.warning("Temporal fingerprint failed: %s", e)
        dossier["fingerprint"] = None

    # 6. Anomaly detection
    try:
        from anomaly_detection import detect_anomalies

        dossier["anomalies"] = _format_anomaly_sections(detect_anomalies(events, routines=routines))
    except Exception as e:
        logger.warning("Anomaly detection failed: %s", e)
        dossier["anomalies"] = None

    # 7. AI narrative (Ollama, graceful fallback)
    try:
        from intel_dossier import generate_dossier as gen_ai_dossier

        dossier["ai_narrative"] = gen_ai_dossier(
            _build_ai_profile(username, events, dossier, routines)
        )
    except Exception as e:
        logger.warning("AI narrative failed: %s", e)
        dossier["ai_narrative"] = None

    return dossier


def render_dossier_html(dossier: dict) -> str:
    """Render dossier dict to self-contained HTML via Jinja2."""
    from jinja2 import Environment, FileSystemLoader

    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "templates")
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    template = env.get_template("dossier.html")
    return template.render(dossier=dossier)
