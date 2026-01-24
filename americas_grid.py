# americas_grid.py
"""Generate grid cells covering North and South America for Waze data collection."""

from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class GridCell:
    """A geographic grid cell."""
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


# Major cities in the Americas
AMERICAS_CITIES = [
    # USA - Major metros
    {"name": "new_york", "lat": 40.71, "lon": -74.01, "country": "US"},
    {"name": "los_angeles", "lat": 34.05, "lon": -118.24, "country": "US"},
    {"name": "chicago", "lat": 41.88, "lon": -87.63, "country": "US"},
    {"name": "houston", "lat": 29.76, "lon": -95.37, "country": "US"},
    {"name": "phoenix", "lat": 33.45, "lon": -112.07, "country": "US"},
    {"name": "philadelphia", "lat": 39.95, "lon": -75.17, "country": "US"},
    {"name": "san_antonio", "lat": 29.42, "lon": -98.49, "country": "US"},
    {"name": "san_diego", "lat": 32.72, "lon": -117.16, "country": "US"},
    {"name": "dallas", "lat": 32.78, "lon": -96.80, "country": "US"},
    {"name": "san_jose", "lat": 37.34, "lon": -121.89, "country": "US"},
    {"name": "austin", "lat": 30.27, "lon": -97.74, "country": "US"},
    {"name": "jacksonville", "lat": 30.33, "lon": -81.66, "country": "US"},
    {"name": "san_francisco", "lat": 37.77, "lon": -122.42, "country": "US"},
    {"name": "seattle", "lat": 47.61, "lon": -122.33, "country": "US"},
    {"name": "denver", "lat": 39.74, "lon": -104.99, "country": "US"},
    {"name": "washington_dc", "lat": 38.91, "lon": -77.04, "country": "US"},
    {"name": "boston", "lat": 42.36, "lon": -71.06, "country": "US"},
    {"name": "detroit", "lat": 42.33, "lon": -83.05, "country": "US"},
    {"name": "atlanta", "lat": 33.75, "lon": -84.39, "country": "US"},
    {"name": "miami", "lat": 25.76, "lon": -80.19, "country": "US"},
    {"name": "minneapolis", "lat": 44.98, "lon": -93.27, "country": "US"},
    {"name": "tampa", "lat": 27.95, "lon": -82.46, "country": "US"},
    {"name": "orlando", "lat": 28.54, "lon": -81.38, "country": "US"},
    {"name": "portland", "lat": 45.52, "lon": -122.68, "country": "US"},
    {"name": "las_vegas", "lat": 36.17, "lon": -115.14, "country": "US"},
    {"name": "baltimore", "lat": 39.29, "lon": -76.61, "country": "US"},
    {"name": "charlotte", "lat": 35.23, "lon": -80.84, "country": "US"},
    {"name": "st_louis", "lat": 38.63, "lon": -90.20, "country": "US"},
    {"name": "pittsburgh", "lat": 40.44, "lon": -80.00, "country": "US"},
    {"name": "cincinnati", "lat": 39.10, "lon": -84.51, "country": "US"},
    # Canada
    {"name": "toronto", "lat": 43.65, "lon": -79.38, "country": "CA"},
    {"name": "montreal", "lat": 45.50, "lon": -73.57, "country": "CA"},
    {"name": "vancouver", "lat": 49.28, "lon": -123.12, "country": "CA"},
    {"name": "calgary", "lat": 51.05, "lon": -114.07, "country": "CA"},
    {"name": "edmonton", "lat": 53.55, "lon": -113.49, "country": "CA"},
    {"name": "ottawa", "lat": 45.42, "lon": -75.70, "country": "CA"},
    {"name": "winnipeg", "lat": 49.90, "lon": -97.14, "country": "CA"},
    {"name": "quebec_city", "lat": 46.81, "lon": -71.21, "country": "CA"},
    # Mexico
    {"name": "mexico_city", "lat": 19.43, "lon": -99.13, "country": "MX"},
    {"name": "guadalajara", "lat": 20.67, "lon": -103.35, "country": "MX"},
    {"name": "monterrey", "lat": 25.67, "lon": -100.31, "country": "MX"},
    {"name": "tijuana", "lat": 32.51, "lon": -117.04, "country": "MX"},
    {"name": "puebla", "lat": 19.04, "lon": -98.21, "country": "MX"},
    {"name": "juarez", "lat": 31.69, "lon": -106.42, "country": "MX"},
    {"name": "leon", "lat": 21.12, "lon": -101.69, "country": "MX"},
    {"name": "cancun", "lat": 21.16, "lon": -86.85, "country": "MX"},
    # Brazil
    {"name": "sao_paulo", "lat": -23.55, "lon": -46.63, "country": "BR"},
    {"name": "rio_de_janeiro", "lat": -22.91, "lon": -43.17, "country": "BR"},
    {"name": "brasilia", "lat": -15.79, "lon": -47.88, "country": "BR"},
    {"name": "salvador", "lat": -12.97, "lon": -38.50, "country": "BR"},
    {"name": "belo_horizonte", "lat": -19.92, "lon": -43.94, "country": "BR"},
    {"name": "fortaleza", "lat": -3.73, "lon": -38.53, "country": "BR"},
    {"name": "curitiba", "lat": -25.43, "lon": -49.27, "country": "BR"},
    {"name": "recife", "lat": -8.05, "lon": -34.88, "country": "BR"},
    {"name": "porto_alegre", "lat": -30.03, "lon": -51.23, "country": "BR"},
    # Argentina
    {"name": "buenos_aires", "lat": -34.60, "lon": -58.38, "country": "AR"},
    {"name": "cordoba_ar", "lat": -31.42, "lon": -64.18, "country": "AR"},
    {"name": "rosario", "lat": -32.95, "lon": -60.65, "country": "AR"},
    {"name": "mendoza", "lat": -32.89, "lon": -68.84, "country": "AR"},
    # Colombia
    {"name": "bogota", "lat": 4.71, "lon": -74.07, "country": "CO"},
    {"name": "medellin", "lat": 6.25, "lon": -75.56, "country": "CO"},
    {"name": "cali", "lat": 3.45, "lon": -76.53, "country": "CO"},
    {"name": "barranquilla", "lat": 10.96, "lon": -74.80, "country": "CO"},
    # Chile
    {"name": "santiago", "lat": -33.45, "lon": -70.67, "country": "CL"},
    {"name": "valparaiso", "lat": -33.05, "lon": -71.62, "country": "CL"},
    # Peru
    {"name": "lima", "lat": -12.05, "lon": -77.04, "country": "PE"},
    {"name": "arequipa", "lat": -16.40, "lon": -71.54, "country": "PE"},
    # Venezuela
    {"name": "caracas", "lat": 10.49, "lon": -66.88, "country": "VE"},
    {"name": "maracaibo", "lat": 10.65, "lon": -71.64, "country": "VE"},
    # Ecuador
    {"name": "quito", "lat": -0.18, "lon": -78.47, "country": "EC"},
    {"name": "guayaquil", "lat": -2.19, "lon": -79.89, "country": "EC"},
    # Central America
    {"name": "panama_city", "lat": 8.98, "lon": -79.52, "country": "PA"},
    {"name": "san_jose_cr", "lat": 9.93, "lon": -84.09, "country": "CR"},
    {"name": "guatemala_city", "lat": 14.63, "lon": -90.51, "country": "GT"},
    # Caribbean
    {"name": "havana", "lat": 23.11, "lon": -82.37, "country": "CU"},
    {"name": "santo_domingo", "lat": 18.49, "lon": -69.93, "country": "DO"},
    {"name": "san_juan", "lat": 18.47, "lon": -66.11, "country": "PR"},
]


def generate_city_grids(cell_size: float = 0.08) -> List[GridCell]:
    """Generate detailed grid cells around major cities."""
    cells = []

    for city in AMERICAS_CITIES:
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


def generate_americas_coverage_grids(cell_size: float = 2.0) -> List[GridCell]:
    """Generate coarse grid cells covering the Americas."""
    cells = []

    # North America bounds
    regions = [
        # Continental US
        {"name": "us", "lat_s": 25, "lat_n": 49, "lon_w": -125, "lon_e": -67},
        # Canada (southern)
        {"name": "ca", "lat_s": 49, "lat_n": 60, "lon_w": -140, "lon_e": -52},
        # Mexico
        {"name": "mx", "lat_s": 14, "lat_n": 33, "lon_w": -118, "lon_e": -86},
        # Central America
        {"name": "central", "lat_s": 7, "lat_n": 18, "lon_w": -92, "lon_e": -77},
        # Caribbean
        {"name": "caribbean", "lat_s": 10, "lat_n": 27, "lon_w": -85, "lon_e": -60},
        # South America
        {"name": "sa", "lat_s": -56, "lat_n": 13, "lon_w": -82, "lon_e": -34},
    ]

    for region in regions:
        lat = region["lat_s"]
        while lat < region["lat_n"]:
            lon = region["lon_w"]
            while lon < region["lon_e"]:
                name = f"am_{region['name']}_{int(lat)}_{int(lon)}".replace("-", "m")
                cells.append(GridCell(
                    name=name,
                    lat_top=round(lat + cell_size, 2),
                    lat_bottom=round(lat, 2),
                    lon_left=round(lon, 2),
                    lon_right=round(lon + cell_size, 2),
                    country=region["name"].upper(),
                    priority=3
                ))
                lon += cell_size
            lat += cell_size

    return cells


def get_all_americas_cells(include_coarse: bool = True) -> List[GridCell]:
    """Get all grid cells for Americas collection."""
    cells = []

    # High-priority: major city grids
    cells.extend(generate_city_grids(cell_size=0.08))

    # Low-priority: coarse coverage
    if include_coarse:
        coarse_cells = generate_americas_coverage_grids(cell_size=2.0)
        city_centers = {(c["lat"], c["lon"]) for c in AMERICAS_CITIES}
        for cell in coarse_cells:
            has_city = False
            for clat, clon in city_centers:
                if (cell.lat_bottom <= clat <= cell.lat_top and
                    cell.lon_left <= clon <= cell.lon_right):
                    has_city = True
                    break
            if not has_city:
                cells.append(cell)

    return cells


def save_americas_config(output_path: str = "config_americas.yaml"):
    """Save Americas grid configuration to YAML file."""
    import yaml

    cells = get_all_americas_cells(include_coarse=True)
    cells.sort(key=lambda c: (c.priority, c.name))

    config = {
        "polling_interval_seconds": 60,
        "waze_server_url": "http://localhost:8080",
        "database_path": "./data/waze_americas.db",
        "collection_mode": "americas",
        "grid_cells": [c.to_dict() for c in cells]
    }

    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {len(cells)} grid cells")
    print(f"  - City grids (priority 1): {sum(1 for c in cells if c.priority == 1)}")
    print(f"  - Coverage grids (priority 3): {sum(1 for c in cells if c.priority == 3)}")
    print(f"Saved to {output_path}")

    return cells


if __name__ == "__main__":
    save_americas_config()
