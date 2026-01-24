# Waze Madrid Logger

A data collection and analysis tool for Waze traffic events in Madrid. Demonstrates location privacy risks in crowdsourced traffic applications.

## Overview

This tool captures Waze traffic reports (police, jams, hazards) along with:
- **Username** of the reporter
- **GPS coordinates** (latitude/longitude)
- **Timestamp** (millisecond precision)
- **Report type** and subtype

By collecting this data over time, it's possible to build detailed movement profiles of individual users - demonstrating significant privacy implications of Waze's crowdsourced model.

**Based on research by [Covert Labs](https://x.com/harrris0n/status/2014197314571952167)**

## Quick Start

### Prerequisites

- Python 3.10+
- Java 11+ (for Waze API server)
- ~100MB disk space

### 1. Clone and setup

```bash
git clone <repo-url>
cd waze-madrid-logger
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Download Waze API server

```bash
mkdir -p lib
curl -L https://github.com/Nimrod007/waze-api/releases/download/v1.0/waze-server.jar -o lib/waze-server.jar
```

### 3. Start collecting

```bash
# Terminal 1: Start Waze API server
java -jar lib/waze-server.jar server

# Terminal 2: Start collector
python cli.py start

# Check status
python cli.py status
```

### 4. Explore the data

```bash
python cli.py stats           # Overview
python cli.py recent          # Latest events
python cli.py users           # Active users
python cli.py profile <user>  # User movement analysis
```

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

### Configuration

```bash
python cli.py config                  # Show config
python cli.py config --interval 180   # Set 3-minute polling
```

## Configuration

Edit `config.yaml`:

```yaml
polling_interval_seconds: 300
waze_server_url: "http://localhost:8080"
database_path: "./data/waze_madrid.db"

grid_cells:
  - name: "gran_via_castellana"
    lat_top: 40.46
    lat_bottom: 40.42
    lon_left: -3.71
    lon_right: -3.68
```

## Project Structure

```
waze-madrid-logger/
├── cli.py              # CLI entry point
├── collector.py        # Collection daemon
├── database.py         # SQLite operations
├── analysis.py         # Stats and profiling
├── grid.py             # Grid cell definitions
├── waze_client.py      # Waze API client
├── config.yaml         # Configuration
├── requirements.txt    # Dependencies
├── lib/
│   └── waze-server.jar
├── data/
│   └── waze_madrid.db
└── exports/
```

## Privacy & Ethics

This tool is for **security research and education** - demonstrating privacy risks in Waze's design.

**Do not use for:**
- Stalking or tracking individuals
- Publishing identifiable data
- Any illegal surveillance

## License

MIT
