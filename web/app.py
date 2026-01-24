"""Flask web application for Waze Madrid Logger visualization."""
import os
import sys
import json
import time
import queue
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, Response

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from analysis import get_stats, get_recent_events, get_user_profile

app = Flask(__name__)

# Global event queue for SSE broadcasting
event_queues = []
event_queues_lock = threading.Lock()

# Status file path for collector updates
STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "collector_status.json")

# Database paths - all regional databases
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
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
    """Get database connection for a specific region or default."""
    if region and region in DB_PATHS:
        return Database(DB_PATHS[region])
    return Database(DB_PATH)


def get_all_dbs():
    """Get connections to all existing databases."""
    dbs = []
    for region, path in DB_PATHS.items():
        if os.path.exists(path):
            try:
                dbs.append((region, Database(path)))
            except Exception:
                pass
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
    """Get summary statistics from all databases."""
    total_events = 0
    unique_users = set()
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

                # Get unique users for this db
                users_rows = db.execute("SELECT DISTINCT username FROM events").fetchall()
                for u in users_rows:
                    unique_users.add(u["username"])

                if row["first_event"]:
                    if first_event is None or row["first_event"] < first_event:
                        first_event = row["first_event"]
                if row["last_event"]:
                    if last_event is None or row["last_event"] > last_event:
                        last_event = row["last_event"]

            db.close()
        except Exception as e:
            print(f"Stats error for {region}: {e}")

    return jsonify({
        "total_events": total_events,
        "unique_users": len(unique_users),
        "first_event": first_event,
        "last_event": last_event
    })


@app.route("/api/events")
def api_events():
    """Get events with optional filters from all databases."""
    # Parse query parameters
    event_type = request.args.get("type")
    since = request.args.get("since")  # hours ago
    date_from = request.args.get("from")  # ISO date string
    date_to = request.args.get("to")  # ISO date string
    username = request.args.get("user")  # filter by username
    limit = request.args.get("limit", 1000, type=int)

    all_events = []

    for region, db in get_all_dbs():
        try:
            query = "SELECT * FROM events WHERE 1=1"
            params = []

            if event_type:
                query += " AND report_type = ?"
                params.append(event_type.upper())

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
                all_events.append({
                    "id": f"{region}_{row['id']}",
                    "username": row["username"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "timestamp": row["timestamp_utc"],
                    "type": row["report_type"],
                    "subtype": row["subtype"],
                    "region": region
                })

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
    date_from = request.args.get("from")  # ISO date string
    date_to = request.args.get("to")  # ISO date string
    username = request.args.get("user")  # filter by username

    # Aggregate heatmap data from all databases
    location_weights = {}

    for region, db in get_all_dbs():
        try:
            query = "SELECT latitude, longitude, COUNT(*) as weight FROM events WHERE 1=1"
            params = []

            if event_type:
                query += " AND report_type = ?"
                params.append(event_type.upper())

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
    """Get list of event types with counts from all databases."""
    type_counts = {}

    for region, db in get_all_dbs():
        try:
            rows = db.execute("""
                SELECT report_type, COUNT(*) as count
                FROM events
                GROUP BY report_type
            """).fetchall()

            for row in rows:
                t = row["report_type"]
                type_counts[t] = type_counts.get(t, 0) + row["count"]

            db.close()
        except Exception as e:
            print(f"Types error for {region}: {e}")

    types = [{"type": t, "count": c} for t, c in sorted(type_counts.items(), key=lambda x: -x[1])]
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
                rows = db.execute("""
                    SELECT username, COUNT(*) as count
                    FROM events
                    WHERE username LIKE ?
                    GROUP BY username
                """, (f"%{search}%",)).fetchall()
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

    users = [{"username": u, "count": c} for u, c in sorted(user_counts.items(), key=lambda x: -x[1])[:limit]]
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
                    if user_stats[u]["last_seen"] is None or row["last_seen"] > user_stats[u]["last_seen"]:
                        user_stats[u]["last_seen"] = row["last_seen"]

            db.close()
        except Exception as e:
            print(f"Leaderboard error for {region}: {e}")

    # Sort by count and format
    sorted_users = sorted(user_stats.items(), key=lambda x: -x[1]["count"])[:limit]

    leaderboard = []
    for rank, (username, stats) in enumerate(sorted_users, 1):
        leaderboard.append({
            "rank": rank,
            "username": username,
            "count": stats["count"],
            "last_seen": stats["last_seen"]
        })

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
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected to live feed'})}\n\n"

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

    return Response(generate(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route("/api/status")
def api_status():
    """Get current collector status."""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
            return jsonify(status)
    except Exception:
        pass
    return jsonify({"status": "unknown", "message": "No collector status available"})


@app.route("/api/recent-activity")
def api_recent_activity():
    """Get most recent events for activity feed from all databases."""
    all_events = []

    for region, db in get_all_dbs():
        try:
            rows = db.execute("""
                SELECT id, username, latitude, longitude, timestamp_utc, report_type, subtype, grid_cell
                FROM events
                ORDER BY id DESC
                LIMIT 20
            """).fetchall()

            for row in rows:
                all_events.append({
                    "id": f"{region}_{row['id']}",
                    "username": row["username"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "timestamp": row["timestamp_utc"],
                    "type": row["report_type"],
                    "subtype": row["subtype"],
                    "grid_cell": row["grid_cell"] if "grid_cell" in row.keys() else None,
                    "region": region
                })

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
                    with open(STATUS_FILE, 'r') as f:
                        status = json.load(f)
                    status['type'] = 'status'
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
                            new_events = db.execute("""
                                SELECT id, username, latitude, longitude, timestamp_utc,
                                       report_type, subtype, grid_cell
                                FROM events WHERE id > ? ORDER BY id ASC LIMIT 20
                            """, (last_id,)).fetchall()

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
                                        "grid_cell": event_row["grid_cell"] if "grid_cell" in event_row.keys() else None,
                                        "region": region
                                    }
                                }
                                broadcast_event(event_data)

                            last_event_ids[region] = current_max
                    db.close()
                except Exception as e:
                    pass

        except Exception as e:
            pass

        time.sleep(2)  # Check every 2 seconds


# Start status monitor thread
monitor_thread = threading.Thread(target=status_monitor_thread, daemon=True)
monitor_thread.start()


if __name__ == "__main__":
    print(f"Database: {DB_PATH}")
    print(f"Starting server at http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
