# asia_grid.py
"""Generate grid cells covering Asia for Waze data collection."""

from typing import List, Dict, Any
from dataclasses import dataclass

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


# Major Asian cities
ASIA_CITIES = [
    # Japan
    {"name": "tokyo", "lat": 35.68, "lon": 139.69, "country": "JP"},
    {"name": "osaka", "lat": 34.69, "lon": 135.50, "country": "JP"},
    {"name": "nagoya", "lat": 35.18, "lon": 136.91, "country": "JP"},
    {"name": "yokohama", "lat": 35.44, "lon": 139.64, "country": "JP"},
    {"name": "fukuoka", "lat": 33.59, "lon": 130.40, "country": "JP"},
    {"name": "sapporo", "lat": 43.06, "lon": 141.35, "country": "JP"},
    {"name": "kyoto", "lat": 35.01, "lon": 135.77, "country": "JP"},
    {"name": "kobe", "lat": 34.69, "lon": 135.20, "country": "JP"},
    # South Korea
    {"name": "seoul", "lat": 37.57, "lon": 126.98, "country": "KR"},
    {"name": "busan", "lat": 35.18, "lon": 129.08, "country": "KR"},
    {"name": "incheon", "lat": 37.46, "lon": 126.71, "country": "KR"},
    {"name": "daegu", "lat": 35.87, "lon": 128.60, "country": "KR"},
    {"name": "daejeon", "lat": 36.35, "lon": 127.38, "country": "KR"},
    # China
    {"name": "beijing", "lat": 39.90, "lon": 116.41, "country": "CN"},
    {"name": "shanghai", "lat": 31.23, "lon": 121.47, "country": "CN"},
    {"name": "guangzhou", "lat": 23.13, "lon": 113.26, "country": "CN"},
    {"name": "shenzhen", "lat": 22.54, "lon": 114.06, "country": "CN"},
    {"name": "chengdu", "lat": 30.57, "lon": 104.07, "country": "CN"},
    {"name": "hong_kong", "lat": 22.32, "lon": 114.17, "country": "HK"},
    {"name": "taipei", "lat": 25.03, "lon": 121.57, "country": "TW"},
    {"name": "hangzhou", "lat": 30.27, "lon": 120.15, "country": "CN"},
    {"name": "xian", "lat": 34.27, "lon": 108.95, "country": "CN"},
    {"name": "wuhan", "lat": 30.59, "lon": 114.31, "country": "CN"},
    {"name": "chongqing", "lat": 29.56, "lon": 106.55, "country": "CN"},
    {"name": "tianjin", "lat": 39.14, "lon": 117.18, "country": "CN"},
    {"name": "nanjing", "lat": 32.06, "lon": 118.80, "country": "CN"},
    # India
    {"name": "mumbai", "lat": 19.08, "lon": 72.88, "country": "IN"},
    {"name": "delhi", "lat": 28.61, "lon": 77.21, "country": "IN"},
    {"name": "bangalore", "lat": 12.97, "lon": 77.59, "country": "IN"},
    {"name": "hyderabad", "lat": 17.39, "lon": 78.49, "country": "IN"},
    {"name": "chennai", "lat": 13.08, "lon": 80.27, "country": "IN"},
    {"name": "kolkata", "lat": 22.57, "lon": 88.36, "country": "IN"},
    {"name": "pune", "lat": 18.52, "lon": 73.86, "country": "IN"},
    {"name": "ahmedabad", "lat": 23.02, "lon": 72.57, "country": "IN"},
    {"name": "jaipur", "lat": 26.91, "lon": 75.79, "country": "IN"},
    # Southeast Asia
    {"name": "singapore", "lat": 1.35, "lon": 103.82, "country": "SG"},
    {"name": "bangkok", "lat": 13.76, "lon": 100.50, "country": "TH"},
    {"name": "jakarta", "lat": -6.21, "lon": 106.85, "country": "ID"},
    {"name": "kuala_lumpur", "lat": 3.14, "lon": 101.69, "country": "MY"},
    {"name": "manila", "lat": 14.60, "lon": 120.98, "country": "PH"},
    {"name": "ho_chi_minh", "lat": 10.82, "lon": 106.63, "country": "VN"},
    {"name": "hanoi", "lat": 21.03, "lon": 105.85, "country": "VN"},
    {"name": "surabaya", "lat": -7.25, "lon": 112.75, "country": "ID"},
    {"name": "bandung", "lat": -6.91, "lon": 107.61, "country": "ID"},
    {"name": "cebu", "lat": 10.32, "lon": 123.89, "country": "PH"},
    {"name": "davao", "lat": 7.19, "lon": 125.46, "country": "PH"},
    {"name": "penang", "lat": 5.42, "lon": 100.31, "country": "MY"},
    {"name": "johor_bahru", "lat": 1.49, "lon": 103.74, "country": "MY"},
    {"name": "chiang_mai", "lat": 18.79, "lon": 98.98, "country": "TH"},
    {"name": "phuket", "lat": 7.89, "lon": 98.40, "country": "TH"},
    # Middle East
    {"name": "dubai", "lat": 25.20, "lon": 55.27, "country": "AE"},
    {"name": "abu_dhabi", "lat": 24.45, "lon": 54.37, "country": "AE"},
    {"name": "riyadh", "lat": 24.71, "lon": 46.68, "country": "SA"},
    {"name": "jeddah", "lat": 21.54, "lon": 39.17, "country": "SA"},
    {"name": "tel_aviv", "lat": 32.09, "lon": 34.78, "country": "IL"},
    {"name": "jerusalem", "lat": 31.77, "lon": 35.23, "country": "IL"},
    {"name": "istanbul", "lat": 41.01, "lon": 28.98, "country": "TR"},
    {"name": "ankara", "lat": 39.93, "lon": 32.86, "country": "TR"},
    {"name": "izmir", "lat": 38.42, "lon": 27.14, "country": "TR"},
    {"name": "doha", "lat": 25.29, "lon": 51.53, "country": "QA"},
    {"name": "kuwait_city", "lat": 29.38, "lon": 47.99, "country": "KW"},
    {"name": "muscat", "lat": 23.59, "lon": 58.41, "country": "OM"},
    {"name": "manama", "lat": 26.23, "lon": 50.59, "country": "BH"},
    {"name": "tehran", "lat": 35.69, "lon": 51.39, "country": "IR"},
    {"name": "beirut", "lat": 33.89, "lon": 35.50, "country": "LB"},
    {"name": "amman", "lat": 31.95, "lon": 35.93, "country": "JO"},
    # Pakistan & Bangladesh
    {"name": "karachi", "lat": 24.86, "lon": 67.01, "country": "PK"},
    {"name": "lahore", "lat": 31.55, "lon": 74.34, "country": "PK"},
    {"name": "islamabad", "lat": 33.68, "lon": 73.05, "country": "PK"},
    {"name": "dhaka", "lat": 23.81, "lon": 90.41, "country": "BD"},
    {"name": "chittagong", "lat": 22.36, "lon": 91.78, "country": "BD"},
    # Central Asia
    {"name": "almaty", "lat": 43.24, "lon": 76.95, "country": "KZ"},
    {"name": "tashkent", "lat": 41.30, "lon": 69.28, "country": "UZ"},
    # Russia (Asian part)
    {"name": "vladivostok", "lat": 43.12, "lon": 131.89, "country": "RU"},
    {"name": "novosibirsk", "lat": 55.01, "lon": 82.92, "country": "RU"},
    {"name": "yekaterinburg", "lat": 56.84, "lon": 60.60, "country": "RU"},
]


def generate_city_grids(cell_size: float = 0.08) -> List[GridCell]:
    """Generate detailed grid cells around major cities."""
    cells = []

    for city in ASIA_CITIES:
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


def generate_asia_coverage_grids(cell_size: float = 2.0) -> List[GridCell]:
    """Generate coarse grid cells covering Asia."""
    cells = []

    regions = [
        # East Asia
        {"name": "east_asia", "lat_s": 20, "lat_n": 54, "lon_w": 100, "lon_e": 145},
        # Southeast Asia
        {"name": "se_asia", "lat_s": -10, "lat_n": 24, "lon_w": 92, "lon_e": 140},
        # South Asia
        {"name": "south_asia", "lat_s": 6, "lat_n": 36, "lon_w": 60, "lon_e": 98},
        # Middle East
        {"name": "middle_east", "lat_s": 12, "lat_n": 42, "lon_w": 26, "lon_e": 64},
        # Central Asia
        {"name": "central_asia", "lat_s": 36, "lat_n": 56, "lon_w": 46, "lon_e": 88},
    ]

    for region in regions:
        lat = region["lat_s"]
        while lat < region["lat_n"]:
            lon = region["lon_w"]
            while lon < region["lon_e"]:
                name = f"as_{region['name'][:2]}_{int(lat)}_{int(lon)}".replace("-", "m")
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


def get_all_asia_cells(include_coarse: bool = True) -> List[GridCell]:
    """Get all grid cells for Asia collection."""
    cells = []
    cells.extend(generate_city_grids(cell_size=0.08))

    if include_coarse:
        coarse_cells = generate_asia_coverage_grids(cell_size=2.0)
        city_centers = {(c["lat"], c["lon"]) for c in ASIA_CITIES}
        for cell in coarse_cells:
            has_city = any(
                cell.lat_bottom <= clat <= cell.lat_top and
                cell.lon_left <= clon <= cell.lon_right
                for clat, clon in city_centers
            )
            if not has_city:
                cells.append(cell)

    return cells


def save_asia_config(output_path: str = "config_asia.yaml"):
    """Save Asia grid configuration to YAML file."""
    import yaml

    cells = get_all_asia_cells(include_coarse=True)
    cells.sort(key=lambda c: (c.priority, c.name))

    config = {
        "polling_interval_seconds": 60,
        "waze_server_url": "http://localhost:8080",
        "database_path": "./data/waze_asia.db",
        "collection_mode": "asia",
        "grid_cells": [c.to_dict() for c in cells]
    }

    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {len(cells)} grid cells for Asia")
    print(f"  - City grids (priority 1): {sum(1 for c in cells if c.priority == 1)}")
    print(f"  - Coverage grids (priority 3): {sum(1 for c in cells if c.priority == 3)}")
    print(f"Saved to {output_path}")

    return cells


if __name__ == "__main__":
    save_asia_config()
