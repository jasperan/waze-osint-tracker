"""Build comprehensive OSINT dossier by fusing all intelligence modules."""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def build_dossier(username: str, db) -> dict:
    """Build a complete intelligence dossier for username from db.

    Calls each intel module with try/except so partial failures
    don't break the whole report. Returns a dict with all sections.
    """
    rows = db.execute(
        "SELECT * FROM events WHERE username = ? ORDER BY timestamp_ms DESC",
        (username,),
    ).fetchall()
    events = [dict(r) for r in rows]

    dossier = {
        "username": username,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(events),
    }

    # 1. Basic report
    try:
        from report_generator import generate_user_report

        dossier["report"] = generate_user_report(username, db)
    except Exception as e:
        logger.warning("Report generation failed: %s", e)
        dossier["report"] = None

    # 2. Privacy score
    try:
        from privacy_score import PrivacyScorer

        scorer = PrivacyScorer()
        dossier["privacy_score"] = scorer.calculate_score(username, events)
    except Exception as e:
        logger.warning("Privacy score failed: %s", e)
        dossier["privacy_score"] = None

    # 3. Trip reconstruction
    try:
        from trip_reconstruction import reconstruct_trips

        dossier["trips"] = reconstruct_trips(events)
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
        from temporal_fingerprint import compute_fingerprint

        dossier["fingerprint"] = compute_fingerprint(events)
    except Exception as e:
        logger.warning("Temporal fingerprint failed: %s", e)
        dossier["fingerprint"] = None

    # 6. Anomaly detection
    try:
        from anomaly_detection import detect_anomalies

        dossier["anomalies"] = detect_anomalies(events)
    except Exception as e:
        logger.warning("Anomaly detection failed: %s", e)
        dossier["anomalies"] = None

    # 7. AI narrative (Ollama, graceful fallback)
    try:
        from intel_dossier import generate_dossier as gen_ai_dossier

        dossier["ai_narrative"] = gen_ai_dossier(username, events, db=db)
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
