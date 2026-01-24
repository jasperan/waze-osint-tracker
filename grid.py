# grid.py
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class GridCell:
    name: str
    lat_top: float
    lat_bottom: float
    lon_left: float
    lon_right: float

    def to_params(self) -> Dict[str, float]:
        """Return params for Waze API query."""
        return {
            "lat_top": self.lat_top,
            "lat_bottom": self.lat_bottom,
            "lon_left": self.lon_left,
            "lon_right": self.lon_right
        }


def load_grid_cells(config: Dict[str, Any]) -> List[GridCell]:
    """Load grid cells from config dictionary."""
    cells = []
    for cell_config in config.get("grid_cells", []):
        cells.append(GridCell(
            name=cell_config["name"],
            lat_top=cell_config["lat_top"],
            lat_bottom=cell_config["lat_bottom"],
            lon_left=cell_config["lon_left"],
            lon_right=cell_config["lon_right"]
        ))
    return cells
