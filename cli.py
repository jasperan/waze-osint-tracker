# cli.py
import os
import sys
import signal
import click
import yaml
from tabulate import tabulate
from datetime import datetime, timedelta

@click.group()
def cli():
    """Waze Madrid Logger - Traffic event collection and analysis."""
    pass

def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)

def get_db():
    from database import Database
    config = load_config()
    return Database(config["database_path"])

# === Collection Commands ===

@cli.command()
def start():
    """Start the collector daemon."""
    from collector import Collector

    pid = Collector.get_pid()
    if pid:
        click.echo(f"Collector already running (PID {pid})")
        return

    click.echo("Starting collector...")
    collector = Collector()
    collector.run()

@cli.command()
def stop():
    """Stop the collector daemon."""
    from collector import Collector

    pid = Collector.get_pid()
    if not pid:
        click.echo("Collector is not running")
        return

    click.echo(f"Stopping collector (PID {pid})...")
    os.kill(pid, signal.SIGTERM)
    click.echo("Stop signal sent")

@cli.command()
def status():
    """Show collector status and database summary."""
    from collector import Collector
    from analysis import get_stats

    config = load_config()
    pid = Collector.get_pid()

    click.echo(f"Collector: {'Running (PID ' + str(pid) + ')' if pid else 'Stopped'}")
    click.echo(f"Database: {config['database_path']}")
    click.echo(f"Polling interval: {config.get('polling_interval_seconds', 300)}s")
    click.echo()

    if os.path.exists(config["database_path"]):
        db = get_db()
        stats = get_stats(db)

        click.echo(f"Total events: {stats['total_events']:,}")
        click.echo(f"Unique users: {stats['unique_users']:,}")

        if stats['first_event']:
            click.echo(f"Time range: {stats['first_event'][:19]} -> {stats['last_event'][:19]}")

        if stats['by_type']:
            click.echo("\nBy type:")
            for t, count in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
                pct = count / stats['total_events'] * 100 if stats['total_events'] else 0
                click.echo(f"  {t:12} {count:>6,} ({pct:.1f}%)")

        db.close()
    else:
        click.echo("No data collected yet")

# === Data Exploration Commands ===

@cli.command()
def stats():
    """Show summary statistics."""
    from analysis import get_stats

    db = get_db()
    s = get_stats(db)

    click.echo(f"Total events: {s['total_events']:,}")
    click.echo(f"Unique users: {s['unique_users']:,}")

    if s['first_event']:
        click.echo(f"First event: {s['first_event'][:19]}")
        click.echo(f"Last event: {s['last_event'][:19]}")

    if s['by_type']:
        click.echo("\nBy type:")
        for t, count in sorted(s['by_type'].items(), key=lambda x: -x[1]):
            pct = count / s['total_events'] * 100 if s['total_events'] else 0
            click.echo(f"  {t:12} {count:>6,} ({pct:.1f}%)")

    db.close()

@cli.command()
@click.option("-n", "--limit", default=20, help="Number of events to show")
def recent(limit):
    """Show recent events."""
    from analysis import get_recent_events

    db = get_db()
    events = get_recent_events(db, limit)

    if not events:
        click.echo("No events found")
        return

    table = []
    for e in events:
        table.append([
            e["timestamp_utc"][:19],
            e["username"][:20],
            e["report_type"],
            f"{e['latitude']:.4f}",
            f"{e['longitude']:.4f}"
        ])

    click.echo(tabulate(table, headers=["Time", "User", "Type", "Lat", "Lon"]))
    db.close()

@cli.command()
@click.option("-u", "--username", help="Filter by username")
@click.option("-t", "--type", "report_type", help="Filter by report type")
@click.option("--since", help="Time filter (e.g., '2h', '1d')")
@click.option("-n", "--limit", default=50, help="Max results")
def search(username, report_type, since, limit):
    """Search events with filters."""
    db = get_db()

    query = "SELECT * FROM events WHERE 1=1"
    params = []

    if username:
        query += " AND username = ?"
        params.append(username)

    if report_type:
        query += " AND report_type = ?"
        params.append(report_type.upper())

    if since:
        # Parse time filter
        unit = since[-1]
        value = int(since[:-1])
        if unit == 'h':
            delta = timedelta(hours=value)
        elif unit == 'd':
            delta = timedelta(days=value)
        elif unit == 'm':
            delta = timedelta(minutes=value)
        else:
            click.echo(f"Unknown time unit: {unit}")
            return

        cutoff = datetime.utcnow() - delta
        query += " AND timestamp_utc >= ?"
        params.append(cutoff.isoformat())

    query += " ORDER BY timestamp_ms DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, tuple(params)).fetchall()

    if not rows:
        click.echo("No events found")
        return

    table = []
    for r in rows:
        table.append([
            r["timestamp_utc"][:19],
            r["username"][:20],
            r["report_type"],
            f"{r['latitude']:.4f}",
            f"{r['longitude']:.4f}"
        ])

    click.echo(tabulate(table, headers=["Time", "User", "Type", "Lat", "Lon"]))
    click.echo(f"\n{len(rows)} events found")
    db.close()

# === User Analysis Commands ===

@cli.command()
@click.option("-n", "--limit", default=50, help="Number of users to show")
def users(limit):
    """List users with event counts."""
    from analysis import get_users_summary

    db = get_db()
    user_list = get_users_summary(db, limit)

    if not user_list:
        click.echo("No users found")
        return

    table = []
    for u in user_list:
        table.append([
            u["username"][:25],
            u["event_count"],
            u["first_seen"][:10],
            u["last_seen"][:10]
        ])

    click.echo(tabulate(table, headers=["Username", "Events", "First Seen", "Last Seen"]))
    db.close()

@cli.command()
@click.argument("username")
def profile(username):
    """Show detailed profile for a user."""
    from analysis import get_user_profile

    db = get_db()
    p = get_user_profile(db, username)

    if not p:
        click.echo(f"User '{username}' not found")
        return

    click.echo(f"User: {p['username']}")
    click.echo(f"Events: {p['event_count']}")
    click.echo(f"First seen: {p['first_seen'][:19]}")
    click.echo(f"Last seen: {p['last_seen'][:19]}")
    click.echo(f"Center location: {p['center_location']['lat']:.4f}, {p['center_location']['lon']:.4f}")

    click.echo("\nReport types:")
    for t, count in sorted(p['type_breakdown'].items(), key=lambda x: -x[1]):
        click.echo(f"  {t}: {count}")

    click.echo("\nRecent events:")
    table = []
    for e in p['events'][-10:]:
        table.append([
            e["timestamp_utc"][:19],
            e["report_type"],
            f"{e['latitude']:.4f}, {e['longitude']:.4f}"
        ])
    click.echo(tabulate(table, headers=["Time", "Type", "Location"]))

    db.close()

# === Export Commands ===

@cli.command()
@click.option("--format", "fmt", type=click.Choice(["csv", "geojson"]), default="csv")
@click.option("-o", "--output", help="Output file path")
def export(fmt, output):
    """Export events to CSV or GeoJSON."""
    import json
    import csv

    db = get_db()
    rows = db.execute("SELECT * FROM events ORDER BY timestamp_ms").fetchall()

    if not rows:
        click.echo("No events to export")
        return

    if not output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"exports/events_{timestamp}.{fmt}"

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

    if fmt == "csv":
        with open(output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow(tuple(row))

    elif fmt == "geojson":
        features = []
        for row in rows:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]]
                },
                "properties": {
                    "username": row["username"],
                    "timestamp": row["timestamp_utc"],
                    "type": row["report_type"],
                    "subtype": row["subtype"]
                }
            })

        geojson = {"type": "FeatureCollection", "features": features}
        with open(output, "w") as f:
            json.dump(geojson, f)

    click.echo(f"Exported {len(rows)} events to {output}")
    db.close()

# === Config Commands ===

@cli.command()
@click.option("--interval", type=int, help="Set polling interval in seconds")
def config(interval):
    """Show or modify configuration."""
    cfg = load_config()

    if interval:
        cfg["polling_interval_seconds"] = interval
        with open("config.yaml", "w") as f:
            yaml.dump(cfg, f, default_flow_style=False)
        click.echo(f"Polling interval set to {interval} seconds")
    else:
        click.echo(yaml.dump(cfg, default_flow_style=False))

if __name__ == "__main__":
    cli()
