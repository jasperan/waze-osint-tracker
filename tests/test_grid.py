# tests/test_grid.py
import tempfile
import os
import pytest
from grid import GridCell, load_grid_cells

def test_load_grid_cells_from_config():
    config = {
        "grid_cells": [
            {
                "name": "test_cell",
                "lat_top": 40.46,
                "lat_bottom": 40.42,
                "lon_left": -3.71,
                "lon_right": -3.68
            }
        ]
    }

    cells = load_grid_cells(config)

    assert len(cells) == 1
    assert cells[0].name == "test_cell"
    assert cells[0].lat_top == 40.46
    assert cells[0].lat_bottom == 40.42

def test_grid_cell_to_params():
    cell = GridCell(
        name="test",
        lat_top=40.46,
        lat_bottom=40.42,
        lon_left=-3.71,
        lon_right=-3.68
    )
    params = cell.to_params()

    assert params["lat_top"] == 40.46
    assert params["lat_bottom"] == 40.42
    assert params["lon_left"] == -3.71
    assert params["lon_right"] == -3.68

def test_load_grid_cells_empty_config():
    config = {}
    cells = load_grid_cells(config)
    assert len(cells) == 0
