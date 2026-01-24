# Waze Worldwide Logger

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

### 1. Clone and setup

```bash
git clone <repo-url>
cd waze-madrid-logger
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start worldwide collector

```bash
# Start the multithreaded worldwide collector
python collector_worldwide.py

# Or run in background
nohup python collector_worldwide.py > /dev/null 2>&1 &
```

### 3. Start web visualization

```bash
python web/app.py
# Open http://localhost:5000
```

### 4. Explore the data

```bash
python cli.py stats           # Overview
python cli.py recent          # Latest events
python cli.py users           # Active users
python cli.py profile <user>  # User movement analysis
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

### Features

- **Live Map:** Leaflet.js heatmap of worldwide events
- **Real-time Feed:** SSE-powered live event stream
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
python cli.py start    # Start collector daemon
python cli.py stop     # Stop collector daemon
python cli.py status   # Show status and stats
```

### Data Exploration

```bash
python cli.py stats              # Summary statistics
python cli.py recent             # Last 20 events
python cli.py recent -n 50       # Last 50 events
python cli.py search -u <user>   # Events from user
python cli.py search -t police   # Filter by type
python cli.py search --since 2h  # Last 2 hours
```

### User Analysis

```bash
python cli.py users              # List users by activity
python cli.py profile <username> # Detailed user profile
```

### Export

```bash
python cli.py export --format csv      # Export to CSV
python cli.py export --format geojson  # Export for mapping
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
├── cli.py                    # CLI entry point
├── collector_worldwide.py    # Multithreaded worldwide collector
├── database.py               # SQLite operations (WAL mode)
├── analysis.py               # Stats and profiling
├── waze_client.py            # Direct Waze API client
├── web/
│   ├── app.py                # Flask web application
│   └── templates/
│       └── index.html        # Map visualization UI
├── config_*.yaml             # Regional configurations
├── *_grid.py                 # Grid cell generators
├── data/
│   ├── waze_europe.db
│   ├── waze_americas.db
│   ├── waze_asia.db
│   ├── waze_oceania.db
│   └── waze_africa.db
└── logs/
    └── worldwide_collector.log
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

### Collector Startup

```
======================================================================
WORLDWIDE WAZE COLLECTOR
Covering: Europe, Americas, Asia, Oceania, Africa
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

### Database Summary

```
--- DATABASE SUMMARY ---
  EUROPE    : 8,234 events, 8,102 users
  AMERICAS  : 6,891 events, 6,754 users
  ASIA      : 5,432 events, 5,298 users
  OCEANIA   : 4,567 events, 4,489 users
  AFRICA    : 3,585 events, 3,453 users
```
