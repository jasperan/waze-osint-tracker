# Waze Worldwide Logger

[![PyPI version](https://badge.fury.io/py/waze-logs.svg)](https://pypi.org/project/waze-logs/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/badge/GitHub-jasperan-181717?logo=github)](https://github.com/jasperan/waze-osint-tracker)
[![Flask](https://img.shields.io/badge/Flask-Web_UI-000000?logo=flask)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?logo=sqlite)](https://www.sqlite.org/)
[![Leaflet](https://img.shields.io/badge/Leaflet-Maps-199900?logo=leaflet)](https://leafletjs.com/)

A worldwide data collection and analysis tool for Waze traffic events. Demonstrates location privacy risks in crowdsourced traffic applications.

## Overview

This tool captures Waze traffic reports (police, jams, hazards, accidents, road closures) from **5 continents** with:
- **Username** of the reporter
- **GPS coordinates** (latitude/longitude)
- **Timestamp** (millisecond precision)
- **Report type** and subtype
- **Region and city** information

By collecting this data over time, it's possible to build detailed movement profiles of individual users - demonstrating significant privacy implications of Waze's crowdsourced model.

**Coverage:** 8,656 grid cells across Europe, Americas, Asia, Oceania, and Africa

**Based on research by [Covert Labs](https://x.com/harrris0n/status/2014197314571952167)**

## Quick Start

### Prerequisites

- Python 3.10+
- ~500MB disk space (for worldwide data)

### 1. Install from PyPI (recommended)

```bash
pip install waze-logs
```

Or install from source:

```bash
git clone https://github.com/jasperan/waze-osint-tracker
cd waze-osint-tracker
pip install -e .
```

This installs the `waze` command globally.

### 2. Start collector with web UI (recommended)

```bash
# Start worldwide collector + web visualization (default)
waze start

# Run in background (daemonized)
waze start -b
waze start --background

# Custom port
waze start --port 8080

# Without web UI
waze start --no-web

# Open http://localhost:5000 (or your custom port)
```

### 3. Monitor and control

```bash
# Watch live logs
waze logs

# Stop collector
waze stop
```

### 4. Alternative: Run components separately

```bash
# Web UI only (view existing data)
waze web
waze web --port 8080
```

### 5. Explore the data

```bash
waze status --all    # Worldwide status & stats
waze summary         # Collection summary
waze recent          # Latest events
waze users           # Active users
waze profile <user>  # User movement analysis
```

### 6. Stop the collector

```bash
waze stop            # Stop any running collector
```

## Worldwide Collector

The worldwide collector scans 5 continents in parallel using multithreading:

| Region | Priority 1 (Cities) | Priority 3 (Coverage) | Total |
|--------|--------------------|-----------------------|-------|
| Europe | 477 | 1,748 | 2,225 |
| Americas | 693 | 1,692 | 2,385 |
| Asia | 684 | 1,517 | 2,201 |
| Oceania | 216 | 481 | 697 |
| Africa | 315 | 833 | 1,148 |
| **Total** | **2,385** | **6,271** | **8,656** |

### Collection Strategy

- **Priority 1 (Cities):** Major metropolitan areas, scanned every cycle
- **Priority 3 (Coverage):** Broader coverage areas, scanned every 10 cycles
- **Parallel scanning:** All 5 regions scanned simultaneously
- **WAL mode:** Thread-safe SQLite with Write-Ahead Logging

## Web Visualization UI

The web UI provides real-time visualization at `http://localhost:5000`:

![Web UI Main View](img/web-ui-main.png)
*Dark-themed interface with filters, live feed, and interactive map*

![Web UI Live Events](img/web-ui-event.png)
*Click any event in the live feed to fly to its location on the map*

### Features

- **Live Map:** Leaflet.js heatmap of worldwide events
- **Real-time Feed:** SSE-powered live event stream
- **Auto-Follow Events:** Map automatically teleports to new events as they arrive (toggle in Display panel)
- **Type Filtering:** Filter by POLICE (blue), ACCIDENT (red), JAM (orange), HAZARD (yellow), ROAD_CLOSED (purple)
- **User Tracking:** Search and filter events by specific username
- **Time Filters:** Filter by date range or hours ago
- **Leaderboard:** Top contributors ranked by event count
- **Click-to-Navigate:** Click any event in the live feed to fly to its location on the map

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/stats` | Summary statistics from all databases |
| `/api/events` | Events with filters (type, user, since, from, to) |
| `/api/heatmap` | Aggregated coordinates for heatmap layer |
| `/api/types` | Event types with counts |
| `/api/users` | User list with search |
| `/api/leaderboard` | Top contributors |
| `/api/stream` | Server-Sent Events for real-time updates |
| `/api/status` | Current collector status |

## CLI Commands

### Collection Control

```bash
# Start worldwide collector (default, includes web UI)
waze start                        # Start collector + web UI on port 5000
waze start -b                     # Run in background (daemonized)
waze start --background           # Same as -b
waze start --port 8080            # Web UI on custom port
waze start --no-web               # Collector only, no web UI
waze start -r europe -r asia      # Collect from specific regions only
waze start --madrid               # Legacy: Madrid-only collector

# Watch live logs (connect to running collector)
waze logs                         # Follow live collector output
waze logs -n 100                  # Show last 100 lines, then follow
waze logs -F                      # Show recent logs and exit (no follow)

# Stop collectors
waze stop                         # Stop any running collector
waze stop --madrid                # Stop Madrid-only collector

# Status
waze status                       # Basic status
waze status --all                 # Full status with all regional DBs
```

### Web Visualization

```bash
waze web                          # Start web UI only (no collection)
waze web --port 8080              # Web UI on custom port
```

### Data Exploration

```bash
waze summary                      # Worldwide collection summary
waze stats                        # Summary statistics
waze daily --all                  # Daily stats from all regions
waze recent                       # Last 20 events
waze recent -n 50                 # Last 50 events
waze search -u <user>             # Events from user
waze search -t police             # Filter by type
waze search --since 2h            # Last 2 hours
```

### User Analysis

```bash
waze users                        # List users by activity
waze tracked                      # Show tracked users with most events
waze profile <username>           # Detailed user profile
```

### Export

```bash
waze export --format csv          # Export to CSV
waze export --format geojson      # Export for mapping
```

## Configuration

Regional configs are auto-generated on first run:
- `config_europe.yaml`
- `config_americas.yaml`
- `config_asia.yaml`
- `config_oceania.yaml`
- `config_africa.yaml`

## Project Structure

```
waze-madrid-logger/
├── pyproject.toml            # Package config (installs 'waze' command)
├── cli.py                    # CLI entry point (with integrated collector + web UI)
├── collector_worldwide.py    # Standalone multithreaded collector
├── database.py               # SQLite operations (WAL mode)
├── analysis.py               # Stats and profiling
├── waze_client.py            # Direct Waze API client
├── web/
│   ├── app.py                # Flask web application
│   └── templates/
│       └── index.html        # Map visualization UI
├── config_*.yaml             # Regional configurations (auto-generated)
├── *_grid.py                 # Grid cell generators
├── data/
│   ├── waze_europe.db
│   ├── waze_americas.db
│   ├── waze_asia.db
│   ├── waze_oceania.db
│   ├── waze_africa.db
│   ├── collector_status.json     # Real-time status for web UI
│   └── collector_checkpoint.json # Resume checkpoint
└── logs/
    └── cli_collector.log
```

## Privacy & Ethics

This tool is for **security research and education** - demonstrating privacy risks in Waze's design.

**Do not use for:**
- Stalking or tracking individuals
- Publishing identifiable data
- Any illegal surveillance

## License

MIT

---

## Annex: Sample Outputs

### CLI Collector Startup (`waze start` or `waze start -b`)

```
Collector started in background
Web UI available at http://localhost:5000
Use 'waze logs' to watch output or 'waze stop' to stop
```

### Foreground Mode (`waze start` without `-b`)

```
Starting worldwide collector...
Web UI will be available at http://localhost:5000
======================================================================
WAZE WORLDWIDE COLLECTOR (CLI)
======================================================================
  EUROPE     - P1 (cities):  477, P3 (coverage): 1748
  AMERICAS   - P1 (cities):  693, P3 (coverage): 1692
  ASIA       - P1 (cities):  684, P3 (coverage): 1517
  OCEANIA    - P1 (cities):  216, P3 (coverage):  481
  AFRICA     - P1 (cities):  315, P3 (coverage):  833
----------------------------------------------------------------------
  TOTAL      - P1 (cities): 2385, P3 (coverage): 6271
               Grand total: 8656 grid cells
======================================================================
Collection strategy (MULTITHREADED):
  - All regions scanned in PARALLEL for P1 (city) scans
  - Full P3 (coverage) scan every 10 cycles (parallel)
  - 10 second pause between cycles
  - Web UI at http://localhost:5000
======================================================================
```

### Parallel Scanning Output

```
==================================================
CYCLE 1 (PARALLEL MODE)
==================================================
Starting parallel P1 scan across 5 regions...
[  1/315] abidjan                   (CI) ->   4 alerts, +4 new | HAZARD:1, JAM:1, POLICE:1
[  1/684] abu_dhabi                 (AE) ->   9 alerts, +1 new | JAM:1
[  1/693] arequipa                  (PE) -> 181 alerts, +6 new | HAZARD:3, POLICE:2, JAM:1
[  1/216] adelaide                  (AU) ->  38 alerts, +38 new | ROAD_CLOSED:31, POLICE:7
[  1/477] amsterdam                 (NL) -> 183 alerts, +3 new | HAZARD:3
  [EUROPE] +4 events, 0 errors
  [ASIA] +1 events, 0 errors
  [AFRICA] +9 events, 0 errors
  [AMERICAS] +7 events, 0 errors
  [OCEANIA] +190 events, 0 errors
P1 cycle complete: +211 total events, 0 errors
```

### API Response: /api/stats

```json
{
    "total_events": 28709,
    "unique_users": 28496,
    "first_event": "2021-02-28T00:00:00+00:00",
    "last_event": "2026-01-24T10:36:15+00:00"
}
```

### API Response: /api/leaderboard

```json
[
    {"rank": 1, "username": "world_3e440399", "count": 3, "last_seen": "2026-01-24T08:09:24+00:00"},
    {"rank": 2, "username": "world_9886cdb3", "count": 3, "last_seen": "2026-01-24T08:33:22+00:00"},
    {"rank": 3, "username": "world_9e5e1c59", "count": 3, "last_seen": "2026-01-24T08:24:36+00:00"}
]
```

### Live Feed Event (SSE)

```json
{
    "type": "new_event",
    "event": {
        "id": "europe_12345",
        "username": "user123",
        "latitude": 52.3676,
        "longitude": 4.9041,
        "timestamp": "2026-01-24T10:30:00+00:00",
        "report_type": "POLICE",
        "subtype": "POLICE_VISIBLE",
        "grid_cell": "amsterdam",
        "region": "europe"
    }
}
```

### Logs Command (`waze logs`)

```
Connected to worldwide collector (PID 2275044)
Log file: logs/cli_collector.log
------------------------------------------------------------
2026-01-24 11:40:45 [INFO]   + POLICE       @  40.41710,   -3.70325 - user_12345
2026-01-24 11:40:47 [INFO]   + JAM          @  48.85640,    2.35220 (JAM_HEAVY_TRAFFIC) - user_67890
2026-01-24 11:40:49 [INFO]   + HAZARD       @  51.50740,   -0.12780 (HAZARD_ON_ROAD_OBJECT) - user_54321
```

### Status Command (`waze status --all`)

```
=== Collector Status ===
Worldwide: Running (PID 2275044)
Madrid:    Stopped
Europe:    Stopped

=== Regional Database Summary ===
Region    Events    Users    First       Last
--------  --------  -------  ----------  ----------
MADRID    272       227      2025-07-31  2026-01-24
EUROPE    17,561    17,412   2021-02-28  2026-01-24
AMERICAS  9,794     9,781    2023-09-21  2026-01-24
ASIA      3,017     3,017    2023-08-16  2026-01-24
OCEANIA   996       995      2023-12-31  2026-01-24
AFRICA    1,120     1,120    2025-06-21  2026-01-24

=== Totals ===
Total events: 32,760
Unique users: 32,498
Time range: 2021-02-28T00:00:00 -> 2026-01-24T11:00:48

By type (all regions):
  HAZARD         15,958 (48.7%)
  ROAD_CLOSED    10,107 (30.9%)
  JAM             3,289 (10.0%)
  POLICE          3,016 (9.2%)
  ACCIDENT          360 (1.1%)
  CHIT_CHAT          30 (0.1%)
```

### Summary Command (`waze summary`)

```
=== Worldwide Collection Summary ===
Total events:    32,760
Unique users:    32,498
Days collected:  45
Grid cells used: 2,156
First event:     2021-02-28T00:00:00
Last event:      2026-01-24T11:00:48
Avg events/day:  728.0

=== By Region ===
  EUROPE       17,561 events    17,412 users  (53.6%)
  AMERICAS      9,794 events     9,781 users  (29.9%)
  ASIA          3,017 events     3,017 users  (9.2%)
  AFRICA        1,120 events     1,120 users  (3.4%)
  OCEANIA         996 events       995 users  (3.0%)
  MADRID          272 events       227 users  (0.8%)
```
