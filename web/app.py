"""Flask web application for Waze Madrid Logger visualization."""
import os
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from analysis import get_stats, get_recent_events, get_user_profile

app = Flask(__name__)

# Database path relative to project root
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "waze_madrid.db")


def get_db():
    """Get database connection."""
    return Database(DB_PATH)


@app.route("/")
def index():
    """Render main map view."""
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    """Get summary statistics."""
    db = get_db()
    stats = get_stats(db)
    db.close()
    return jsonify(stats)


@app.route("/api/events")
def api_events():
    """Get events with optional filters."""
    db = get_db()

    # Parse query parameters
    event_type = request.args.get("type")
    since = request.args.get("since")  # hours ago
    limit = request.args.get("limit", 1000, type=int)

    query = "SELECT * FROM events WHERE 1=1"
    params = []

    if event_type:
        query += " AND report_type = ?"
        params.append(event_type.upper())

    if since:
        hours = int(since)
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query += " AND timestamp_utc >= ?"
        params.append(cutoff.isoformat())

    query += " ORDER BY timestamp_ms DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, tuple(params)).fetchall()

    events = []
    for row in rows:
        events.append({
            "id": row["id"],
            "username": row["username"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "timestamp": row["timestamp_utc"],
            "type": row["report_type"],
            "subtype": row["subtype"],
        })

    db.close()
    return jsonify(events)


@app.route("/api/heatmap")
def api_heatmap():
    """Get events formatted for heatmap layer."""
    db = get_db()

    since = request.args.get("since")  # hours ago
    event_type = request.args.get("type")

    query = "SELECT latitude, longitude, COUNT(*) as weight FROM events WHERE 1=1"
    params = []

    if event_type:
        query += " AND report_type = ?"
        params.append(event_type.upper())

    if since:
        hours = int(since)
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query += " AND timestamp_utc >= ?"
        params.append(cutoff.isoformat())

    query += " GROUP BY ROUND(latitude, 4), ROUND(longitude, 4)"

    rows = db.execute(query, tuple(params)).fetchall()

    # Format for Leaflet heatmap: [[lat, lng, intensity], ...]
    heatmap_data = []
    for row in rows:
        heatmap_data.append([row["latitude"], row["longitude"], row["weight"]])

    db.close()
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
    """Get list of event types with counts."""
    db = get_db()
    rows = db.execute("""
        SELECT report_type, COUNT(*) as count
        FROM events
        GROUP BY report_type
        ORDER BY count DESC
    """).fetchall()

    types = [{"type": row["report_type"], "count": row["count"]} for row in rows]
    db.close()
    return jsonify(types)


if __name__ == "__main__":
    print(f"Database: {DB_PATH}")
    print(f"Starting server at http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
