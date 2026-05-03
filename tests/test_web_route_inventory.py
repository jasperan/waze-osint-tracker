from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


EXPECTED_ROUTE_INVENTORY = {
    "GET / -> index",
    "GET /api/alerts -> api_alerts",
    "GET /api/anomalies -> api_anomalies",
    "GET /api/briefing -> api_briefing",
    "GET /api/encounters/<user_a>/<user_b> -> api_encounters",
    "GET /api/encounters/hotspots -> api_encounter_hotspots",
    "GET /api/encounters/schedule -> api_encounters_schedule",
    "GET /api/events -> api_events",
    "GET /api/fingerprint/<username> -> api_fingerprint",
    "GET /api/fingerprint/<username>/matches -> api_fingerprint_matches",
    "GET /api/geofence-alerts -> api_geofence_alerts",
    "GET /api/geofences -> api_list_geofences",
    "POST /api/geofences -> api_create_geofence",
    "DELETE /api/geofences/<geofence_id> -> api_delete_geofence",
    "GET /api/grid-cells -> api_grid_cells",
    "GET /api/heatmap -> api_heatmap",
    "GET /api/intel/convoys -> api_intel_convoys",
    "GET /api/intel/correlations -> api_intel_correlations",
    "GET /api/intel/user/<username> -> api_intel_user",
    "GET /api/leaderboard -> api_leaderboard",
    "GET /api/privacy-score/<username> -> api_privacy_score",
    "GET /api/privacy-score/leaderboard -> api_privacy_leaderboard",
    "GET /api/recent-activity -> api_recent_activity",
    "GET /api/report/<username> -> api_report",
    "GET /api/social-graph -> api_social_graph",
    "GET /api/social-graph/<username> -> api_social_graph_user",
    "GET /api/stats -> api_stats",
    "GET /api/status -> api_status",
    "GET /api/stream -> api_stream",
    "GET /api/timeline -> api_timeline",
    "GET /api/trips/<username> -> api_trips",
    "GET /api/types -> api_types",
    "GET /api/user/<username> -> api_user",
    "GET /api/users -> api_users",
    "GET /static/<path:filename> -> static",
}


def _route_inventory(app):
    inventory = set()
    for rule in app.url_map.iter_rules():
        methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        inventory.add(f"{methods} {rule.rule} -> {rule.endpoint}")
    return inventory


def test_method_aware_route_inventory_is_preserved():
    from web.app import app

    assert _route_inventory(app) == EXPECTED_ROUTE_INVENTORY
