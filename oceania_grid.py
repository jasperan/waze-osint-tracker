# oceania_grid.py
"""Generate grid cells for Oceania Waze data collection."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class GridCell:
    name: str
    lat_top: float
    lat_bottom: float
    lon_left: float
    lon_right: float
    country: str = ""
    priority: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "lat_top": self.lat_top,
            "lat_bottom": self.lat_bottom,
            "lon_left": self.lon_left,
            "lon_right": self.lon_right,
            "country": self.country,
            "priority": self.priority,
        }


# Major Oceanian cities
OCEANIA_CITIES = [
    # Australia
    {"name": "sydney", "lat": -33.87, "lon": 151.21, "country": "AU"},
    {"name": "melbourne", "lat": -37.81, "lon": 144.96, "country": "AU"},
    {"name": "brisbane", "lat": -27.47, "lon": 153.03, "country": "AU"},
    {"name": "perth", "lat": -31.95, "lon": 115.86, "country": "AU"},
    {"name": "adelaide", "lat": -34.93, "lon": 138.60, "country": "AU"},
    {"name": "gold_coast", "lat": -28.02, "lon": 153.43, "country": "AU"},
    {"name": "canberra", "lat": -35.28, "lon": 149.13, "country": "AU"},
    {"name": "newcastle", "lat": -32.93, "lon": 151.78, "country": "AU"},
    {"name": "wollongong", "lat": -34.42, "lon": 150.89, "country": "AU"},
    {"name": "hobart", "lat": -42.88, "lon": 147.33, "country": "AU"},
    {"name": "geelong", "lat": -38.15, "lon": 144.36, "country": "AU"},
    {"name": "townsville", "lat": -19.26, "lon": 146.82, "country": "AU"},
    {"name": "cairns", "lat": -16.92, "lon": 145.77, "country": "AU"},
    {"name": "darwin", "lat": -12.46, "lon": 130.84, "country": "AU"},
    # New Zealand
    {"name": "auckland", "lat": -36.85, "lon": 174.76, "country": "NZ"},
    {"name": "wellington", "lat": -41.29, "lon": 174.78, "country": "NZ"},
    {"name": "christchurch", "lat": -43.53, "lon": 172.64, "country": "NZ"},
    {"name": "hamilton_nz", "lat": -37.79, "lon": 175.28, "country": "NZ"},
    {"name": "tauranga", "lat": -37.69, "lon": 176.17, "country": "NZ"},
    {"name": "dunedin", "lat": -45.87, "lon": 170.50, "country": "NZ"},
    # Pacific Islands (limited Waze presence but included)
    {"name": "suva", "lat": -18.14, "lon": 178.44, "country": "FJ"},
    {"name": "port_moresby", "lat": -9.44, "lon": 147.18, "country": "PG"},
    {"name": "noumea", "lat": -22.28, "lon": 166.46, "country": "NC"},
    {"name": "honolulu", "lat": 21.31, "lon": -157.86, "country": "US"},  # Hawaii
]


def generate_city_grids(cell_size: float = 0.08) -> List[GridCell]:
    """Generate detailed grid cells around major cities."""
    cells = []

    for city in OCEANIA_CITIES:
        lat_center = city["lat"]
        lon_center = city["lon"]

        for lat_offset in [-1, 0, 1]:
            for lon_offset in [-1, 0, 1]:
                lat_bottom = lat_center + (lat_offset * cell_size) - (cell_size / 2)
                lat_top = lat_bottom + cell_size
                lon_left = lon_center + (lon_offset * cell_size) - (cell_size / 2)
                lon_right = lon_left + cell_size

                suffix = ""
                if lat_offset == -1:
                    suffix += "_s"
                elif lat_offset == 1:
                    suffix += "_n"
                if lon_offset == -1:
                    suffix += "_w"
                elif lon_offset == 1:
                    suffix += "_e"

                cells.append(
                    GridCell(
                        name=f"{city['name']}{suffix}",
                        lat_top=round(lat_top, 4),
                        lat_bottom=round(lat_bottom, 4),
                        lon_left=round(lon_left, 4),
                        lon_right=round(lon_right, 4),
                        country=city["country"],
                        priority=1,
                    )
                )

    return cells


def generate_oceania_coverage_grids(cell_size: float = 2.0) -> List[GridCell]:
    """Generate coarse grid cells covering Oceania land masses."""
    cells = []

    regions = [
        # Australia
        {"name": "au", "lat_s": -44, "lat_n": -10, "lon_w": 112, "lon_e": 154},
        # New Zealand
        {"name": "nz", "lat_s": -48, "lat_n": -34, "lon_w": 166, "lon_e": 180},
        # Papua New Guinea & nearby
        {"name": "pg", "lat_s": -12, "lat_n": 0, "lon_w": 140, "lon_e": 156},
        # Pacific Islands (sparse coverage)
        {"name": "pac", "lat_s": -24, "lat_n": -12, "lon_w": 164, "lon_e": 180},
    ]

    for region in regions:
        lat = region["lat_s"]
        while lat < region["lat_n"]:
            lon = region["lon_w"]
            while lon < region["lon_e"]:
                name = f"oc_{region['name']}_{int(abs(lat))}{'s' if lat < 0 else 'n'}_{int(lon)}"
                cells.append(
                    GridCell(
                        name=name,
                        lat_top=round(lat + cell_size, 2),
                        lat_bottom=round(lat, 2),
                        lon_left=round(lon, 2),
                        lon_right=round(lon + cell_size, 2),
                        country=region["name"].upper(),
                        priority=3,
                    )
                )
                lon += cell_size
            lat += cell_size

    return cells


def get_all_oceania_cells(include_coarse: bool = True) -> List[GridCell]:
    """Get all grid cells for Oceania collection."""
    cells = []
    cells.extend(generate_city_grids(cell_size=0.08))

    if include_coarse:
        coarse_cells = generate_oceania_coverage_grids(cell_size=2.0)
        city_centers = {(c["lat"], c["lon"]) for c in OCEANIA_CITIES}
        for cell in coarse_cells:
            has_city = any(
                cell.lat_bottom <= clat <= cell.lat_top and cell.lon_left <= clon <= cell.lon_right
                for clat, clon in city_centers
            )
            if not has_city:
                cells.append(cell)

    return cells


def save_oceania_config(output_path: str = "config_oceania.yaml"):
    """Save Oceania grid configuration to YAML file."""
    import yaml

    cells = get_all_oceania_cells(include_coarse=True)
    cells.sort(key=lambda c: (c.priority, c.name))

    config = {
        "polling_interval_seconds": 60,
        "waze_server_url": "http://localhost:8080",
        "database_path": "./data/waze_oceania.db",
        "collection_mode": "oceania",
        "grid_cells": [c.to_dict() for c in cells],
    }

    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {len(cells)} grid cells for Oceania")
    print(f"  - City grids (priority 1): {sum(1 for c in cells if c.priority == 1)}")
    print(f"  - Coverage grids (priority 3): {sum(1 for c in cells if c.priority == 3)}")
    print(f"Saved to {output_path}")

    return cells


if __name__ == "__main__":
    save_oceania_config()
