# africa_grid.py
"""Generate grid cells covering Africa for Waze data collection."""

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


# Major African cities
AFRICA_CITIES = [
    # South Africa
    {"name": "johannesburg", "lat": -26.20, "lon": 28.04, "country": "ZA"},
    {"name": "cape_town", "lat": -33.93, "lon": 18.42, "country": "ZA"},
    {"name": "durban", "lat": -29.86, "lon": 31.02, "country": "ZA"},
    {"name": "pretoria", "lat": -25.75, "lon": 28.19, "country": "ZA"},
    {"name": "port_elizabeth", "lat": -33.96, "lon": 25.60, "country": "ZA"},
    # Egypt
    {"name": "cairo", "lat": 30.04, "lon": 31.24, "country": "EG"},
    {"name": "alexandria", "lat": 31.20, "lon": 29.92, "country": "EG"},
    {"name": "giza", "lat": 30.01, "lon": 31.21, "country": "EG"},
    # Nigeria
    {"name": "lagos", "lat": 6.52, "lon": 3.38, "country": "NG"},
    {"name": "abuja", "lat": 9.08, "lon": 7.40, "country": "NG"},
    {"name": "kano", "lat": 12.00, "lon": 8.52, "country": "NG"},
    {"name": "ibadan", "lat": 7.38, "lon": 3.90, "country": "NG"},
    # Kenya
    {"name": "nairobi", "lat": -1.29, "lon": 36.82, "country": "KE"},
    {"name": "mombasa", "lat": -4.05, "lon": 39.67, "country": "KE"},
    # Morocco
    {"name": "casablanca", "lat": 33.57, "lon": -7.59, "country": "MA"},
    {"name": "rabat", "lat": 34.02, "lon": -6.83, "country": "MA"},
    {"name": "marrakech", "lat": 31.63, "lon": -8.00, "country": "MA"},
    {"name": "fes", "lat": 34.03, "lon": -5.00, "country": "MA"},
    {"name": "tangier", "lat": 35.77, "lon": -5.80, "country": "MA"},
    # Algeria
    {"name": "algiers", "lat": 36.75, "lon": 3.06, "country": "DZ"},
    {"name": "oran", "lat": 35.70, "lon": -0.64, "country": "DZ"},
    # Tunisia
    {"name": "tunis", "lat": 36.81, "lon": 10.17, "country": "TN"},
    # Ghana
    {"name": "accra", "lat": 5.56, "lon": -0.19, "country": "GH"},
    # Ethiopia
    {"name": "addis_ababa", "lat": 9.03, "lon": 38.75, "country": "ET"},
    # Tanzania
    {"name": "dar_es_salaam", "lat": -6.79, "lon": 39.21, "country": "TZ"},
    # Uganda
    {"name": "kampala", "lat": 0.35, "lon": 32.58, "country": "UG"},
    # Senegal
    {"name": "dakar", "lat": 14.69, "lon": -17.44, "country": "SN"},
    # Ivory Coast
    {"name": "abidjan", "lat": 5.35, "lon": -4.01, "country": "CI"},
    # Cameroon
    {"name": "douala", "lat": 4.05, "lon": 9.77, "country": "CM"},
    {"name": "yaounde", "lat": 3.87, "lon": 11.52, "country": "CM"},
    # Angola
    {"name": "luanda", "lat": -8.84, "lon": 13.23, "country": "AO"},
    # Zimbabwe
    {"name": "harare", "lat": -17.83, "lon": 31.05, "country": "ZW"},
    # Zambia
    {"name": "lusaka", "lat": -15.39, "lon": 28.32, "country": "ZM"},
    # Rwanda
    {"name": "kigali", "lat": -1.94, "lon": 30.06, "country": "RW"},
    # Mauritius
    {"name": "port_louis", "lat": -20.16, "lon": 57.50, "country": "MU"},
]


def generate_city_grids(cell_size: float = 0.08) -> List[GridCell]:
    """Generate detailed grid cells around major cities."""
    cells = []

    for city in AFRICA_CITIES:
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

                cells.append(GridCell(
                    name=f"{city['name']}{suffix}",
                    lat_top=round(lat_top, 4),
                    lat_bottom=round(lat_bottom, 4),
                    lon_left=round(lon_left, 4),
                    lon_right=round(lon_right, 4),
                    country=city["country"],
                    priority=1
                ))

    return cells


def generate_africa_coverage_grids(cell_size: float = 2.0) -> List[GridCell]:
    """Generate coarse grid cells covering Africa."""
    cells = []

    # Africa bounds
    regions = [
        # North Africa
        {"name": "north", "lat_s": 18, "lat_n": 38, "lon_w": -18, "lon_e": 36},
        # West Africa
        {"name": "west", "lat_s": 4, "lat_n": 18, "lon_w": -18, "lon_e": 16},
        # Central Africa
        {"name": "central", "lat_s": -12, "lat_n": 12, "lon_w": 8, "lon_e": 32},
        # East Africa
        {"name": "east", "lat_s": -12, "lat_n": 12, "lon_w": 28, "lon_e": 52},
        # Southern Africa
        {"name": "south", "lat_s": -36, "lat_n": -12, "lon_w": 10, "lon_e": 42},
    ]

    for region in regions:
        lat = region["lat_s"]
        while lat < region["lat_n"]:
            lon = region["lon_w"]
            while lon < region["lon_e"]:
                name = f"af_{region['name'][:2]}_{int(abs(lat))}{'s' if lat < 0 else 'n'}_{int(abs(lon))}{'w' if lon < 0 else 'e'}"
                cells.append(GridCell(
                    name=name,
                    lat_top=round(lat + cell_size, 2),
                    lat_bottom=round(lat, 2),
                    lon_left=round(lon, 2),
                    lon_right=round(lon + cell_size, 2),
                    country=region["name"].upper()[:2],
                    priority=3
                ))
                lon += cell_size
            lat += cell_size

    return cells


def get_all_africa_cells(include_coarse: bool = True) -> List[GridCell]:
    """Get all grid cells for Africa collection."""
    cells = []
    cells.extend(generate_city_grids(cell_size=0.08))

    if include_coarse:
        coarse_cells = generate_africa_coverage_grids(cell_size=2.0)
        city_centers = {(c["lat"], c["lon"]) for c in AFRICA_CITIES}
        for cell in coarse_cells:
            has_city = any(
                cell.lat_bottom <= clat <= cell.lat_top and
                cell.lon_left <= clon <= cell.lon_right
                for clat, clon in city_centers
            )
            if not has_city:
                cells.append(cell)

    return cells


def save_africa_config(output_path: str = "config_africa.yaml"):
    """Save Africa grid configuration to YAML file."""
    import yaml

    cells = get_all_africa_cells(include_coarse=True)
    cells.sort(key=lambda c: (c.priority, c.name))

    config = {
        "polling_interval_seconds": 60,
        "waze_server_url": "http://localhost:8080",
        "database_path": "./data/waze_africa.db",
        "collection_mode": "africa",
        "grid_cells": [c.to_dict() for c in cells]
    }

    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {len(cells)} grid cells for Africa")
    print(f"  - City grids (priority 1): {sum(1 for c in cells if c.priority == 1)}")
    print(f"  - Coverage grids (priority 3): {sum(1 for c in cells if c.priority == 3)}")
    print(f"Saved to {output_path}")

    return cells


if __name__ == "__main__":
    save_africa_config()
