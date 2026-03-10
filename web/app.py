"""Flask web application for Waze Madrid Logger visualization."""

import json
import logging
import os
import queue
import sys
import threading
import time
from datetime import datetime, timedelta

import yaml
from flask import Flask, Response, jsonify, render_template, request

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import get_user_profile
from database import Database

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global event queue for SSE broadcasting
event_queues = []
event_queues_lock = threading.Lock()

# Stats cache (expensive query - cache for 60 seconds)
_stats_cache = {"data": None, "expires": 0}

# Status file path for collector updates
STATUS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "collector_status.json"
)

# Project root for config file discovery
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_web_config():
    """Load config, preferring config_oracle.yaml over config.yaml."""
    for config_file in ("config_oracle.yaml", "config.yaml"):
        full_path = os.path.join(_PROJECT_ROOT, config_file)
        if os.path.exists(full_path):
            with open(full_path) as f:
                return yaml.safe_load(f)
    # Final fallback
    with open(os.path.join(_PROJECT_ROOT, "config.yaml")) as f:
        return yaml.safe_load(f)


# Database paths - all regional databases (SQLite fallback)
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
DB_PATHS = {
    "madrid": os.path.join(DATA_DIR, "waze_madrid.db"),
    "europe": os.path.join(DATA_DIR, "waze_europe.db"),
    "americas": os.path.join(DATA_DIR, "waze_americas.db"),
    "asia": os.path.join(DATA_DIR, "waze_asia.db"),
    "oceania": os.path.join(DATA_DIR, "waze_oceania.db"),
    "africa": os.path.join(DATA_DIR, "waze_africa.db"),
}

# Legacy single DB path for compatibility
DB_PATH = DB_PATHS["madrid"]


def get_db(region=None):
    """Get database connection for a specific region or default.

    If config specifies ``database_type: oracle``, returns an OracleDatabase
    instance.  Otherwise falls back to per-region SQLite files.
    """
    try:
        config = _load_web_config()
    except Exception:
        config = {}

    if config.get("database_type") == "oracle":
        from database_oracle import Database as OracleDatabase

        return OracleDatabase(config["oracle_dsn"], config.get("oracle_schema", "waze"))

    if region and region in DB_PATHS:
        return Database(DB_PATHS[region])
    return Database(DB_PATH)


def get_all_dbs():
    """Get connections to all existing databases.

    With Oracle, returns a single ``("all", db)`` pair since all regions live
    in one partitioned table.  With SQLite, returns one pair per region file.
    """
    try:
        config = _load_web_config()
    except Exception:
        config = {}

    if config.get("database_type") == "oracle":
        from database_oracle import Database as OracleDatabase

        db = OracleDatabase(config["oracle_dsn"], config.get("oracle_schema", "waze"))
        return [("all", db)]

    dbs = []
    for region, path in DB_PATHS.items():
        if os.path.exists(path):
            try:
                dbs.append((region, Database(path)))
            except Exception:
                logger.warning("Failed to open database for region %s", region)
    return dbs


def query_all_dbs(query_func):
    """Execute a function on all databases and combine results."""
    all_results = []
    for region, db in get_all_dbs():
        try:
            results = query_func(db, region)
            if results:
                all_results.extend(results)
            db.close()
        except Exception as e:
            print(f"Error querying {region}: {e}")
    return all_results


@app.route("/")
def index():
    """Render main map view."""
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    """Get summary statistics from all databases (cached 60s)."""
    now = time.time()
    if _stats_cache["data"] and now < _stats_cache["expires"]:
        return jsonify(_stats_cache["data"])

    total_events = 0
    total_unique_users = 0
    first_event = None
    last_event = None

    for region, db in get_all_dbs():
        try:
            row = db.execute("""
                SELECT COUNT(*) as count,
                       COUNT(DISTINCT username) as users,
                       MIN(timestamp_utc) as first_event,
                       MAX(timestamp_utc) as last_event
                FROM events
            """).fetchone()

            if row:
                total_events += row["count"] or 0
                total_unique_users += row["users"] or 0

                if row["first_event"]:
                    if first_event is None or row["first_event"] < first_event:
                        first_event = row["first_event"]
                if row["last_event"]:
                    if last_event is None or row["last_event"] > last_event:
                        last_event = row["last_event"]

            db.close()
        except Exception as e:
            print(f"Stats error for {region}: {e}")

    result = {
        "total_events": total_events,
        "unique_users": total_unique_users,
        "first_event": first_event,
        "last_event": last_event,
    }
    _stats_cache["data"] = result
    _stats_cache["expires"] = time.time() + 60
    return jsonify(result)


@app.route("/api/events")
def api_events():
    """Get events with optional filters from all databases."""
    # Parse query parameters
    event_type = request.args.get("type")
    event_subtype = request.args.get("subtype")  # filter by subtype
    since = request.args.get("since")  # hours ago
    date_from = request.args.get("from")  # ISO date string
    date_to = request.args.get("to")  # ISO date string
    username = request.args.get("user")  # filter by username
    region_filter = request.args.get("region")  # filter by region
    limit = min(request.args.get("limit", 1000, type=int), 10000)

    all_events = []

    for region, db in get_all_dbs():
        # With SQLite, skip databases that don't match the filter.
        # With Oracle (region == "all"), add a SQL WHERE clause instead.
        if region_filter and region != "all" and region != region_filter:
            db.close()
            continue
        try:
            query = "SELECT * FROM events WHERE 1=1"
            params = []

            # Oracle: filter by region column inside the single DB
            if region_filter and region == "all":
                query += " AND region = ?"
                params.append(region_filter)

            if event_type:
                query += " AND report_type = ?"
                params.append(event_type.upper())

            if event_subtype:
                query += " AND subtype = ?"
                params.append(event_subtype)

            if username:
                query += " AND username = ?"
                params.append(username)

            if since:
                hours = int(since)
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                query += " AND timestamp_utc >= ?"
                params.append(cutoff.isoformat())
            elif date_from:
                query += " AND timestamp_utc >= ?"
                params.append(date_from)

            if date_to:
                date_to_val = date_to
                if len(date_to_val) == 10:
                    date_to_val += "T23:59:59"
                query += " AND timestamp_utc <= ?"
                params.append(date_to_val)

            query += " ORDER BY timestamp_ms DESC LIMIT ?"
            params.append(limit)

            rows = db.execute(query, tuple(params)).fetchall()

            for row in rows:
                evt_region = row.get("region", region) if region == "all" else region
                all_events.append(
                    {
                        "id": f"{evt_region}_{row['id']}",
                        "username": row["username"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                        "timestamp": row["timestamp_utc"],
                        "type": row["report_type"],
                        "subtype": row["subtype"],
                        "region": evt_region,
                    }
                )

            db.close()
        except Exception as e:
            print(f"Events error for {region}: {e}")

    # Sort by timestamp and limit
    all_events.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return jsonify(all_events[:limit])


@app.route("/api/heatmap")
def api_heatmap():
    """Get events formatted for heatmap layer from all databases."""
    since = request.args.get("since")  # hours ago
    event_type = request.args.get("type")
    event_subtype = request.args.get("subtype")  # filter by subtype
    date_from = request.args.get("from")  # ISO date string
    date_to = request.args.get("to")  # ISO date string
    username = request.args.get("user")  # filter by username
    region_filter = request.args.get("region")  # filter by region

    # Aggregate heatmap data from all databases
    location_weights = {}

    for region, db in get_all_dbs():
        # With SQLite, skip databases that don't match the filter.
        # With Oracle (region == "all"), add a SQL WHERE clause instead.
        if region_filter and region != "all" and region != region_filter:
            db.close()
            continue
        try:
            query = "SELECT latitude, longitude, COUNT(*) as weight FROM events WHERE 1=1"
            params = []

            # Oracle: filter by region column inside the single DB
            if region_filter and region == "all":
                query += " AND region = ?"
                params.append(region_filter)

            if event_type:
                query += " AND report_type = ?"
                params.append(event_type.upper())

            if event_subtype:
                query += " AND subtype = ?"
                params.append(event_subtype)

            if username:
                query += " AND username = ?"
                params.append(username)

            if since:
                hours = int(since)
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                query += " AND timestamp_utc >= ?"
                params.append(cutoff.isoformat())
            elif date_from:
                query += " AND timestamp_utc >= ?"
                params.append(date_from)

            if date_to:
                date_to_val = date_to
                if len(date_to_val) == 10:
                    date_to_val += "T23:59:59"
                query += " AND timestamp_utc <= ?"
                params.append(date_to_val)

            query += " GROUP BY ROUND(latitude, 4), ROUND(longitude, 4)"

            rows = db.execute(query, tuple(params)).fetchall()

            for row in rows:
                key = (round(row["latitude"], 4), round(row["longitude"], 4))
                location_weights[key] = location_weights.get(key, 0) + row["weight"]

            db.close()
        except Exception as e:
            print(f"Heatmap error for {region}: {e}")

    # Format for Leaflet heatmap: [[lat, lng, intensity], ...]
    heatmap_data = [[lat, lon, weight] for (lat, lon), weight in location_weights.items()]

    return jsonify(heatmap_data)


@app.route("/api/user/<username>")
def api_user(username):
    """Get user profile and events."""
    db = get_db()
    profile = get_user_profile(db, username)
    db.close()

    if not profile:
        return jsonify({"error": "User not found"}), 404

    # Remove full events list from profile (too large)
    profile["events"] = profile["events"][-50:]  # Last 50 only
    return jsonify(profile)


@app.route("/api/types")
def api_types():
    """Get list of event types with counts and subtypes from all databases."""
    type_counts = {}
    subtype_counts = {}  # {parent_type: {subtype: count}}

    for region, db in get_all_dbs():
        try:
            rows = db.execute("""
                SELECT report_type, subtype, COUNT(*) as count
                FROM events
                GROUP BY report_type, subtype
            """).fetchall()

            for row in rows:
                t = row["report_type"]
                st = row["subtype"] or ""
                count = row["count"]

                # Aggregate total for type
                type_counts[t] = type_counts.get(t, 0) + count

                # Aggregate subtype counts
                if t not in subtype_counts:
                    subtype_counts[t] = {}
                if st:  # Only track non-empty subtypes
                    subtype_counts[t][st] = subtype_counts[t].get(st, 0) + count

            db.close()
        except Exception as e:
            print(f"Types error for {region}: {e}")

    # Build response with subtypes included
    types = []
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        type_data = {"type": t, "count": c}
        if t in subtype_counts and subtype_counts[t]:
            # Sort subtypes by count descending
            type_data["subtypes"] = [
                {"subtype": st, "count": sc}
                for st, sc in sorted(subtype_counts[t].items(), key=lambda x: -x[1])
            ]
        types.append(type_data)

    return jsonify(types)


@app.route("/api/users")
def api_users():
    """Get list of users with event counts from all databases."""
    search = request.args.get("q", "")
    limit = request.args.get("limit", 50, type=int)

    user_counts = {}

    for region, db in get_all_dbs():
        try:
            if search:
                rows = db.execute(
                    """
                    SELECT username, COUNT(*) as count
                    FROM events
                    WHERE username LIKE ?
                    GROUP BY username
                """,
                    (f"%{search}%",),
                ).fetchall()
            else:
                rows = db.execute("""
                    SELECT username, COUNT(*) as count
                    FROM events
                    GROUP BY username
                """).fetchall()

            for row in rows:
                u = row["username"]
                user_counts[u] = user_counts.get(u, 0) + row["count"]

            db.close()
        except Exception as e:
            print(f"Users error for {region}: {e}")

    users = [
        {"username": u, "count": c}
        for u, c in sorted(user_counts.items(), key=lambda x: -x[1])[:limit]
    ]
    return jsonify(users)


@app.route("/api/leaderboard")
def api_leaderboard():
    """Get top users leaderboard with detailed stats."""
    limit = request.args.get("limit", 10, type=int)

    user_stats = {}

    for region, db in get_all_dbs():
        try:
            rows = db.execute("""
                SELECT username,
                       COUNT(*) as count,
                       COUNT(DISTINCT report_type) as types,
                       MAX(timestamp_utc) as last_seen
                FROM events
                WHERE username != 'anonymous'
                GROUP BY username
            """).fetchall()

            for row in rows:
                u = row["username"]
                if u not in user_stats:
                    user_stats[u] = {"count": 0, "types": set(), "last_seen": None}

                user_stats[u]["count"] += row["count"]
                user_stats[u]["types"].add(row["types"])

                if row["last_seen"]:
                    if (
                        user_stats[u]["last_seen"] is None
                        or row["last_seen"] > user_stats[u]["last_seen"]
                    ):
                        user_stats[u]["last_seen"] = row["last_seen"]

            db.close()
        except Exception as e:
            print(f"Leaderboard error for {region}: {e}")

    # Sort by count and format
    sorted_users = sorted(user_stats.items(), key=lambda x: -x[1]["count"])[:limit]

    leaderboard = []
    for rank, (username, stats) in enumerate(sorted_users, 1):
        leaderboard.append(
            {
                "rank": rank,
                "username": username,
                "count": stats["count"],
                "last_seen": stats["last_seen"],
            }
        )

    return jsonify(leaderboard)


@app.route("/api/stream")
def api_stream():
    """Server-Sent Events endpoint for real-time updates."""

    def generate():
        q = queue.Queue()
        with event_queues_lock:
            event_queues.append(q)

        try:
            # Send initial connection message
            msg = json.dumps({"type": "connected", "message": "Connected to live feed"})
            yield f"data: {msg}\n\n"

            while True:
                try:
                    # Wait for new events with timeout
                    event = q.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            with event_queues_lock:
                if q in event_queues:
                    event_queues.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/status")
def api_status():
    """Get current collector status."""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r") as f:
                status = json.load(f)
            return jsonify(status)
    except Exception:
        logger.warning("Failed to read collector status file")
    return jsonify({"status": "unknown", "message": "No collector status available"})


@app.route("/api/recent-activity")
def api_recent_activity():
    """Get most recent events for activity feed from all databases."""
    all_events = []

    for region, db in get_all_dbs():
        try:
            rows = db.execute("""
                SELECT id, username, latitude, longitude,
                       timestamp_utc, report_type, subtype,
                       grid_cell
                FROM events
                ORDER BY id DESC
                LIMIT 20
            """).fetchall()

            for row in rows:
                evt_region = row.get("region", region) if region == "all" else region
                all_events.append(
                    {
                        "id": f"{evt_region}_{row['id']}",
                        "username": row["username"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                        "timestamp": row["timestamp_utc"],
                        "type": row["report_type"],
                        "subtype": row["subtype"],
                        "grid_cell": row["grid_cell"] if "grid_cell" in row.keys() else None,
                        "region": evt_region,
                    }
                )

            db.close()
        except Exception as e:
            print(f"Recent activity error for {region}: {e}")

    # Sort by timestamp and return most recent
    all_events.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return jsonify(all_events[:50])


def broadcast_event(event_data):
    """Broadcast an event to all connected SSE clients."""
    with event_queues_lock:
        for q in event_queues:
            try:
                q.put_nowait(event_data)
            except queue.Full:
                pass


def status_monitor_thread():
    """Monitor status file and broadcast updates."""
    last_mtime = 0
    last_event_ids = {}  # Track per-region

    while True:
        try:
            # Check for status file updates
            if os.path.exists(STATUS_FILE):
                mtime = os.path.getmtime(STATUS_FILE)
                if mtime > last_mtime:
                    last_mtime = mtime
                    with open(STATUS_FILE, "r") as f:
                        status = json.load(f)
                    status["type"] = "status"
                    broadcast_event(status)

            # Check for new database events in all regions
            for region, db in get_all_dbs():
                try:
                    row = db.execute("SELECT MAX(id) as max_id FROM events").fetchone()
                    if row and row["max_id"]:
                        current_max = row["max_id"]
                        last_id = last_event_ids.get(region, 0)

                        if current_max > last_id:
                            # Get new events
                            new_events = db.execute(
                                """
                                SELECT id, username, latitude, longitude, timestamp_utc,
                                       report_type, subtype, grid_cell
                                FROM events WHERE id > ? ORDER BY id ASC LIMIT 20
                            """,
                                (last_id,),
                            ).fetchall()

                            for event_row in new_events:
                                event_data = {
                                    "type": "new_event",
                                    "event": {
                                        "id": f"{region}_{event_row['id']}",
                                        "username": event_row["username"],
                                        "latitude": event_row["latitude"],
                                        "longitude": event_row["longitude"],
                                        "timestamp": event_row["timestamp_utc"],
                                        "report_type": event_row["report_type"],
                                        "subtype": event_row["subtype"],
                                        "grid_cell": event_row["grid_cell"]
                                        if "grid_cell" in event_row.keys()
                                        else None,
                                        "region": region,
                                    },
                                }
                                broadcast_event(event_data)

                            last_event_ids[region] = current_max
                    db.close()
                except Exception:
                    logger.debug("Error monitoring region %s", region)

        except Exception:
            logger.debug("Error in status monitor cycle")

        time.sleep(2)  # Check every 2 seconds


# Start status monitor thread
monitor_thread = threading.Thread(target=status_monitor_thread, daemon=True)
monitor_thread.start()


# === Intelligence API endpoints ===


@app.route("/api/intel/user/<username>")
def api_intel_user(username):
    """Get full intelligence profile for a user."""
    try:
        config = _load_web_config()
    except Exception:
        config = {}
    if config.get("database_type") != "oracle":
        return jsonify({"error": "Intelligence requires Oracle backend"}), 400

    from database_oracle import Database as OracleDatabase

    db = OracleDatabase(config["oracle_dsn"], config.get("oracle_schema", "waze"))

    # Get behavioral vector data
    row = db.execute(
        "SELECT username, region, event_count, centroid_lat, centroid_lon, "
        "geo_spread_km, hour_histogram, dow_histogram, type_distribution, "
        "cadence_stats, dossier FROM user_behavioral_vectors WHERE username = ?",
        (username,),
    ).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "User not found in intelligence database"}), 404

    profile = dict(row)

    # Get routines
    routines = db.execute(
        "SELECT routine_type, latitude, longitude, confidence, evidence_count "
        "FROM user_routines WHERE username = ?",
        (username,),
    ).fetchall()
    profile["routines"] = [dict(r) for r in routines]

    # Get co-occurrence partners
    coocs = db.execute(
        "SELECT user_a, user_b, co_count, avg_distance_m "
        "FROM user_co_occurrences "
        "WHERE user_a = ? OR user_b = ? "
        "ORDER BY co_count DESC FETCH FIRST 10 ROWS ONLY",
        (username, username),
    ).fetchall()
    profile["co_occurrences"] = [
        {
            "partner": r["user_b"] if r["user_a"] == username else r["user_a"],
            "co_count": r["co_count"],
            "avg_distance_m": r["avg_distance_m"],
        }
        for r in coocs
    ]

    db.close()
    return jsonify(profile)


@app.route("/api/intel/correlations")
def api_intel_correlations():
    """Get top identity correlations."""
    try:
        config = _load_web_config()
    except Exception:
        config = {}
    if config.get("database_type") != "oracle":
        return jsonify({"error": "Intelligence requires Oracle backend"}), 400

    limit = request.args.get("limit", 20, type=int)
    from database_oracle import Database as OracleDatabase

    db = OracleDatabase(config["oracle_dsn"], config.get("oracle_schema", "waze"))

    results = db.execute(
        "SELECT user_a, user_b, vector_similarity, graph_score, "
        "combined_score, correlation_type, explanation "
        "FROM identity_correlations "
        "ORDER BY combined_score DESC "
        "FETCH FIRST ? ROWS ONLY",
        (limit,),
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in results])


@app.route("/api/intel/convoys")
def api_intel_convoys():
    """Get convoy pairs."""
    try:
        config = _load_web_config()
    except Exception:
        config = {}
    if config.get("database_type") != "oracle":
        return jsonify({"error": "Intelligence requires Oracle backend"}), 400

    min_count = request.args.get("min_count", 5, type=int)
    from database_oracle import Database as OracleDatabase

    db = OracleDatabase(config["oracle_dsn"], config.get("oracle_schema", "waze"))

    results = db.execute(
        "SELECT user_a, user_b, co_count, avg_distance_m, avg_time_gap_s "
        "FROM user_co_occurrences "
        "WHERE co_count >= ? "
        "ORDER BY co_count DESC "
        "FETCH FIRST 50 ROWS ONLY",
        (min_count,),
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in results])


if __name__ == "__main__":
    try:
        _cfg = _load_web_config()
        if _cfg.get("database_type") == "oracle":
            print(f"Database: Oracle ({_cfg.get('oracle_dsn', 'N/A').split('@')[1]})")
        else:
            print(f"Database: {DB_PATH}")
    except Exception:
        print(f"Database: {DB_PATH}")
    print("Starting server at http://localhost:5000")
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(debug=debug, host="0.0.0.0", port=5000, threaded=True)
