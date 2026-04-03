# europe_grid.py
"""Generate grid cells covering all of Europe for Waze data collection."""

from dataclasses import dataclass
from typing import Any, Dict, List, TypedDict


@dataclass
class GridCell:
    """A geographic grid cell."""

    name: str
    lat_top: float
    lat_bottom: float
    lon_left: float
    lon_right: float
    country: str = ""
    priority: int = 1  # 1=high (major cities), 2=medium, 3=low

    def to_params(self) -> Dict[str, float]:
        return {
            "lat_top": self.lat_top,
            "lat_bottom": self.lat_bottom,
            "lon_left": self.lon_left,
            "lon_right": self.lon_right,
        }

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


class CitySpec(TypedDict):
    name: str
    lat: float
    lon: float
    country: str


# Major European cities with high-priority grids (0.1° cells for detail)
MAJOR_CITIES: List[CitySpec] = [
    # Spain
    {"name": "madrid", "lat": 40.42, "lon": -3.70, "country": "ES"},
    {"name": "barcelona", "lat": 41.39, "lon": 2.17, "country": "ES"},
    {"name": "valencia", "lat": 39.47, "lon": -0.38, "country": "ES"},
    {"name": "seville", "lat": 37.39, "lon": -5.99, "country": "ES"},
    {"name": "bilbao", "lat": 43.26, "lon": -2.93, "country": "ES"},
    # France
    {"name": "paris", "lat": 48.86, "lon": 2.35, "country": "FR"},
    {"name": "lyon", "lat": 45.76, "lon": 4.84, "country": "FR"},
    {"name": "marseille", "lat": 43.30, "lon": 5.37, "country": "FR"},
    {"name": "toulouse", "lat": 43.60, "lon": 1.44, "country": "FR"},
    {"name": "nice", "lat": 43.71, "lon": 7.26, "country": "FR"},
    # Germany
    {"name": "berlin", "lat": 52.52, "lon": 13.41, "country": "DE"},
    {"name": "munich", "lat": 48.14, "lon": 11.58, "country": "DE"},
    {"name": "hamburg", "lat": 53.55, "lon": 9.99, "country": "DE"},
    {"name": "frankfurt", "lat": 50.11, "lon": 8.68, "country": "DE"},
    {"name": "cologne", "lat": 50.94, "lon": 6.96, "country": "DE"},
    {"name": "dusseldorf", "lat": 51.23, "lon": 6.78, "country": "DE"},
    {"name": "stuttgart", "lat": 48.78, "lon": 9.18, "country": "DE"},
    # Italy
    {"name": "rome", "lat": 41.90, "lon": 12.50, "country": "IT"},
    {"name": "milan", "lat": 45.46, "lon": 9.19, "country": "IT"},
    {"name": "naples", "lat": 40.85, "lon": 14.27, "country": "IT"},
    {"name": "turin", "lat": 45.07, "lon": 7.69, "country": "IT"},
    {"name": "florence", "lat": 43.77, "lon": 11.25, "country": "IT"},
    # UK
    {"name": "london", "lat": 51.51, "lon": -0.13, "country": "UK"},
    {"name": "manchester", "lat": 53.48, "lon": -2.24, "country": "UK"},
    {"name": "birmingham", "lat": 52.49, "lon": -1.90, "country": "UK"},
    {"name": "leeds", "lat": 53.80, "lon": -1.55, "country": "UK"},
    {"name": "glasgow", "lat": 55.86, "lon": -4.25, "country": "UK"},
    {"name": "edinburgh", "lat": 55.95, "lon": -3.19, "country": "UK"},
    # Netherlands
    {"name": "amsterdam", "lat": 52.37, "lon": 4.90, "country": "NL"},
    {"name": "rotterdam", "lat": 51.92, "lon": 4.48, "country": "NL"},
    {"name": "the_hague", "lat": 52.08, "lon": 4.30, "country": "NL"},
    # Belgium
    {"name": "brussels", "lat": 50.85, "lon": 4.35, "country": "BE"},
    {"name": "antwerp", "lat": 51.22, "lon": 4.40, "country": "BE"},
    # Portugal
    {"name": "lisbon", "lat": 38.72, "lon": -9.14, "country": "PT"},
    {"name": "porto", "lat": 41.16, "lon": -8.63, "country": "PT"},
    # Austria
    {"name": "vienna", "lat": 48.21, "lon": 16.37, "country": "AT"},
    # Switzerland
    {"name": "zurich", "lat": 47.37, "lon": 8.54, "country": "CH"},
    {"name": "geneva", "lat": 46.20, "lon": 6.14, "country": "CH"},
    # Poland
    {"name": "warsaw", "lat": 52.23, "lon": 21.01, "country": "PL"},
    {"name": "krakow", "lat": 50.06, "lon": 19.94, "country": "PL"},
    # Czech Republic
    {"name": "prague", "lat": 50.08, "lon": 14.44, "country": "CZ"},
    # Sweden
    {"name": "stockholm", "lat": 59.33, "lon": 18.07, "country": "SE"},
    {"name": "gothenburg", "lat": 57.71, "lon": 11.97, "country": "SE"},
    # Norway
    {"name": "oslo", "lat": 59.91, "lon": 10.75, "country": "NO"},
    # Denmark
    {"name": "copenhagen", "lat": 55.68, "lon": 12.57, "country": "DK"},
    # Finland
    {"name": "helsinki", "lat": 60.17, "lon": 24.94, "country": "FI"},
    # Ireland
    {"name": "dublin", "lat": 53.35, "lon": -6.26, "country": "IE"},
    # Greece
    {"name": "athens", "lat": 37.98, "lon": 23.73, "country": "GR"},
    {"name": "thessaloniki", "lat": 40.64, "lon": 22.94, "country": "GR"},
    # Hungary
    {"name": "budapest", "lat": 47.50, "lon": 19.04, "country": "HU"},
    # Romania
    {"name": "bucharest", "lat": 44.43, "lon": 26.10, "country": "RO"},
    # Bulgaria
    {"name": "sofia", "lat": 42.70, "lon": 23.32, "country": "BG"},
    # Croatia
    {"name": "zagreb", "lat": 45.81, "lon": 15.98, "country": "HR"},
]


def generate_city_grids(cell_size: float = 0.08) -> List[GridCell]:
    """Generate detailed grid cells around major cities."""
    cells = []

    for city in MAJOR_CITIES:
        # Create a 3x3 grid around each city center
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


def generate_europe_coverage_grids(cell_size: float = 1.0) -> List[GridCell]:
    """Generate coarse grid cells covering all of Europe."""
    cells = []

    # Europe bounds (approximate)
    lat_south = 35.0  # Southern Spain/Greece
    lat_north = 71.0  # Northern Scandinavia
    lon_west = -11.0  # Portugal/Ireland
    lon_east = 40.0  # Eastern Europe

    lat = lat_south
    while lat < lat_north:
        lon = lon_west
        while lon < lon_east:
            # Skip ocean areas (rough approximation)
            is_land = True

            # Atlantic Ocean west of Portugal/Spain
            if lon < -10 and lat < 43:
                is_land = False
            # North Atlantic
            if lon < -8 and lat > 58 and lat < 62:
                is_land = False
            # Mediterranean Sea (rough)
            if lat < 38 and lon > 0 and lon < 15:
                is_land = lat > 36 or lon < 5  # Keep coastal areas

            if is_land:
                name = f"eu_{int(lat)}_{int(lon)}".replace("-", "m")
                cells.append(
                    GridCell(
                        name=name,
                        lat_top=round(lat + cell_size, 2),
                        lat_bottom=round(lat, 2),
                        lon_left=round(lon, 2),
                        lon_right=round(lon + cell_size, 2),
                        country="EU",
                        priority=3,
                    )
                )

            lon += cell_size
        lat += cell_size

    return cells


def get_all_europe_cells(include_coarse: bool = True) -> List[GridCell]:
    """Get all grid cells for Europe collection."""
    cells = []

    # High-priority: major city grids (detailed)
    cells.extend(generate_city_grids(cell_size=0.08))

    # Low-priority: coarse Europe coverage
    if include_coarse:
        coarse_cells = generate_europe_coverage_grids(cell_size=1.0)
        # Filter out cells that overlap with city grids
        city_centers = {(c["lat"], c["lon"]) for c in MAJOR_CITIES}
        for cell in coarse_cells:
            # Check if any city is in this coarse cell
            has_city = False
            for clat, clon in city_centers:
                if (
                    cell.lat_bottom <= clat <= cell.lat_top
                    and cell.lon_left <= clon <= cell.lon_right
                ):
                    has_city = True
                    break
            if not has_city:
                cells.append(cell)

    return cells


def save_europe_config(output_path: str = "config_europe.yaml"):
    """Save Europe grid configuration to YAML file."""
    import yaml

    cells = get_all_europe_cells(include_coarse=True)

    # Sort by priority then name
    cells.sort(key=lambda c: (c.priority, c.name))

    config = {
        "polling_interval_seconds": 60,  # 1 minute between cycles
        "waze_server_url": "http://localhost:8080",
        "database_path": "./data/waze_europe.db",
        "collection_mode": "europe",
        "grid_cells": [c.to_dict() for c in cells],
    }

    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {len(cells)} grid cells")
    print(f"  - City grids (priority 1): {sum(1 for c in cells if c.priority == 1)}")
    print(f"  - Coverage grids (priority 3): {sum(1 for c in cells if c.priority == 3)}")
    print(f"Saved to {output_path}")

    return cells


if __name__ == "__main__":
    save_europe_config()
