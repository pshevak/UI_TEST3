# reburn/genetic_planner.py

import math
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional

import requests

CELL_SIZE_KM = 1.0  # 1 km x 1 km cells

# Labels we’ll send back to the frontend.
# You can rename these strings to match your UI copy.
ACTIONS = [
    "protect_unburned_refugia",
    "targeted_erosion_control",
    "replant_high_severity",
    "fuel_breaks_and_buffer",
    "monitor_and_wait",
]

# Colors keyed by action label for frontend rendering.
ACTION_COLORS = {
    "protect_unburned_refugia": "#3b82f6",   # blue
    "targeted_erosion_control": "#10b981",   # green
    "replant_high_severity": "#ef4444",      # red
    "fuel_breaks_and_buffer": "#f59e0b",     # amber
    "monitor_and_wait": "#6b7280",           # gray
}

# Default segmentation endpoint if caller wants us to fetch severity grid
DEFAULT_SEGMENT_API = os.environ.get("SEGMENT_API_URL", "http://localhost:8001/api/segment")


@dataclass
class GridCell:
    row: int
    col: int
    center_lat: float
    center_lng: float
    north: float
    south: float
    east: float
    west: float


def _deg_per_km(lat_deg: float) -> Tuple[float, float]:
    """
    Approximate degrees of lat/lon per kilometer at a given latitude.
    """
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(lat_deg))

    return 1.0 / km_per_deg_lat, 1.0 / km_per_deg_lon


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_grid_for_fire(fire: Dict[str, Any], cell_size_km: float = CELL_SIZE_KM) -> Dict[str, Any]:
    """
    Build a grid of ~1 km x 1 km cells over the fire bounding box.
    Returns metadata + cell geometry.
    """
    west = fire["westbc"]
    east = fire["eastbc"]
    north = fire["northbc"]
    south = fire["southbc"]

    mid_lat = 0.5 * (north + south)

    deg_lat_per_km, deg_lon_per_km = _deg_per_km(mid_lat)

    lat_extent_km = (north - south) / deg_lat_per_km
    lon_extent_km = (east - west) / deg_lon_per_km

    n_rows = max(1, int(round(lat_extent_km / cell_size_km)))
    n_cols = max(1, int(round(lon_extent_km / cell_size_km)))

    # actual degree size per cell (may not be exactly 1km but close)
    cell_dlat = (north - south) / n_rows
    cell_dlon = (east - west) / n_cols

    cells: List[GridCell] = []
    for r in range(n_rows):
        for c in range(n_cols):
            cell_south = south + r * cell_dlat
            cell_north = cell_south + cell_dlat
            cell_west = west + c * cell_dlon
            cell_east = cell_west + cell_dlon

            center_lat = 0.5 * (cell_south + cell_north)
            center_lng = 0.5 * (cell_west + cell_east)

            cells.append(
                GridCell(
                    row=r,
                    col=c,
                    center_lat=center_lat,
                    center_lng=center_lng,
                    north=cell_north,
                    south=cell_south,
                    east=cell_east,
                    west=cell_west,
                )
            )

    return {
        "rows": n_rows,
        "cols": n_cols,
        "cells": cells,
        "cell_dlat": cell_dlat,
        "cell_dlon": cell_dlon,
    }


def _normalize_priorities(priorities: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(v, 0.0) for v in priorities.values()) or 1.0
    return {k: max(v, 0.0) / total for k, v in priorities.items()}


def _extract_features(fire: Dict[str, Any]) -> Dict[str, float]:
    """Grab numeric features (same across cells) from the fire record."""
    return {
        "elevation_m": float(fire.get("elevation_m", 0.0) or 0.0),
        "avg_temp_c": float(fire.get("avg_temp_c", 0.0) or 0.0),
        "soil_moisture_pct": float(fire.get("soil_moisture_pct", 0.0) or 0.0),
        "gw_depth_ft": float(fire.get("gw_depth_ft", 0.0) or 0.0),
        "ph_val": float(fire.get("ph_val", 7.0) or 7.0),
        "precip_mm": float(fire.get("precip_mm", 0.0) or 0.0),
        "land_burned_frequency": float(fire.get("land_burned_frequency", 0.0) or 0.0),
        "reburn": float(fire.get("reburn", 0.0) or 0.0),
    }


def _resample_severity_grid(severity_grid: List[List[int]], rows: int, cols: int) -> List[List[int]]:
    """Nearest-neighbor resample of severity grid to match GA grid size."""
    if not severity_grid or rows <= 0 or cols <= 0:
        return [[0 for _ in range(cols)] for _ in range(rows)]

    src_rows = len(severity_grid)
    src_cols = len(severity_grid[0]) if src_rows else 0
    if src_rows == 0 or src_cols == 0:
        return [[0 for _ in range(cols)] for _ in range(rows)]

    def src_idx(r, c):
        sr = min(int(round((r / max(rows - 1, 1)) * (src_rows - 1))), src_rows - 1)
        sc = min(int(round((c / max(cols - 1, 1)) * (src_cols - 1))), src_cols - 1)
        return sr, sc

    out: List[List[int]] = []
    for r in range(rows):
        row_vals = []
        for c in range(cols):
            sr, sc = src_idx(r, c)
            try:
                row_vals.append(int(severity_grid[sr][sc]))
            except Exception:
                row_vals.append(0)
        out.append(row_vals)
    return out


def _fetch_severity_grid(fire_id: str, segment_api_url: Optional[str] = None) -> List[List[int]]:
    """Call segmentation API to get severity grid (0–5) for the fire."""
    api_url = segment_api_url or DEFAULT_SEGMENT_API
    try:
        resp = requests.post(api_url, params={"fireId": fire_id}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        grid = data.get("severities_grid") or data.get("severity_grid") or []
        if isinstance(grid, list):
            return grid
    except Exception:
        # Fail quietly; GA will treat missing as zeros.
        return []
    return []


def score_action_for_cell(
    action_idx: int,
    cell: GridCell,
    grid_meta: Dict[str, Any],
    priorities: Dict[str, float],
    timeline: int,
    fire: Dict[str, Any],
    features: Dict[str, float],
    severity_value: float = 0.0,
) -> float:
    """
    Heuristic scoring function for one cell + one action.
    This is where we encode the “story”:
    - near edges → fuel breaks / protection
    - interior → replant / monitoring
    - wetter & steep areas → erosion control / watershed
    - severity 0–5 influences action preferences
    """

    n_rows = grid_meta["rows"]
    severity_norm = clamp(severity_value / 5.0, 0.0, 1.0)
    n_cols = grid_meta["cols"]

    # geometric features
    dist_to_edge = min(
        cell.row,
        cell.col,
        n_rows - 1 - cell.row,
        n_cols - 1 - cell.col,
    )
    max_edge_dist = max(1, min(n_rows, n_cols) // 2)
    edge_factor = 1.0 - min(dist_to_edge / max_edge_dist, 1.0)  # 1 near edge, 0 interior
    center_factor = 1.0 - edge_factor

    # fire-level features
    burn_freq = float(fire.get("land_burned_frequency", 0.0))  # 0..?
    precip = float(fire.get("precip_mm", 0.0))
    elev = float(fire.get("elevation_m", 0.0))
    avg_temp = float(features.get("avg_temp_c", 0.0))
    soil_moisture = float(features.get("soil_moisture_pct", 0.0))
    gw_depth = float(features.get("gw_depth_ft", 0.0))
    ph_val = float(features.get("ph_val", 7.0))

    # rough normalization
    precip_norm = min(precip / 1000.0, 1.0)  # assume 0–1000mm
    elev_norm = min(elev / 3000.0, 1.0)      # 0–3000m
    reburn_risk = float(fire.get("reburn", False)) or burn_freq
    temp_norm = clamp((avg_temp - 5) / 25.0, 0.0, 1.0)       # 5–30C nominal
    soil_norm = clamp(soil_moisture / 50.0, 0.0, 1.0)        # 0–50%
    gw_norm = clamp(gw_depth / 200.0, 0.0, 1.0)              # 0–200 ft
    ph_norm = clamp(abs(ph_val - 7.0) / 3.0, 0.0, 1.0)       # acidity/alkalinity deviation

    p_comm = priorities["community"]
    p_wshed = priorities["watershed"]
    p_infra = priorities["infrastructure"]

    # action-specific scoring
    if action_idx == 0:  # protect_unburned_refugia
        base = (0.6 * center_factor + 0.4 * edge_factor) * (1.0 - 0.5 * severity_norm)
        weight = 0.5 * p_comm + 0.5 * p_wshed
        time_factor = 0.3 if timeline == 0 else 1.0
    elif action_idx == 1:  # targeted_erosion_control
        base = 0.35 * edge_factor + 0.4 * precip_norm + 0.25 * soil_norm
        weight = 0.6 * p_wshed + 0.4 * p_comm
        time_factor = 1.0 if timeline == 0 else 0.7
        base += 0.2 * severity_norm  # erosion more urgent when severity is higher
    elif action_idx == 2:  # replant_high_severity
        base = 0.4 * center_factor + 0.4 * severity_norm + 0.2 * reburn_risk
        weight = 0.6 * p_comm + 0.4 * p_wshed
        time_factor = 0.3 if timeline == 0 else 1.0
        base += 0.1 * (1.0 - ph_norm)  # neutral soils slightly favor replanting
    elif action_idx == 3:  # fuel_breaks_and_buffer
        base = 0.8 * edge_factor + 0.2 * center_factor + 0.2 * severity_norm
        weight = 0.5 * p_comm + 0.5 * p_infra
        time_factor = 0.8 + 0.2 * (1 if timeline > 0 else 0)  # always useful
    else:  # monitor_and_wait
        base = 0.3 * center_factor + 0.2 * edge_factor + 0.5 * (1.0 - reburn_risk)
        weight = 0.4 * p_comm + 0.3 * p_wshed + 0.3 * p_infra
        time_factor = 0.8
        base *= (1.0 - 0.6 * severity_norm)  # monitoring less useful where severity is high

    # Temperatures/soil/gw can nudge scores slightly
    base += 0.05 * temp_norm + 0.05 * (1.0 - gw_norm)

    noise = random.uniform(-0.05, 0.05)
    return max(0.0, base * weight * time_factor + noise)


def _init_population(num_cells: int, population_size: int) -> List[List[int]]:
    # each individual is a list of action indices, one per cell
    return [
        [random.randrange(len(ACTIONS)) for _ in range(num_cells)]
        for _ in range(population_size)
    ]


def _crossover(parent1: List[int], parent2: List[int]) -> List[int]:
    cut = random.randrange(1, len(parent1))
    return parent1[:cut] + parent2[cut:]


def _mutate(individual: List[int], mutation_rate: float = 0.02) -> None:
    for i in range(len(individual)):
        if random.random() < mutation_rate:
            individual[i] = random.randrange(len(ACTIONS))


def plan_best_next_steps(
    fire: Dict[str, Any],
    priorities_raw: Dict[str, float],
    timeline: int = 2,
    population_size: int = 40,
    n_generations: int = 30,
    elitism: int = 3,
    severity_grid: Optional[List[List[int]]] = None,
    segment_api_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Genetic algorithm that searches over assignments of actions to grid cells.
    Returns a structure ready to be sent to the frontend.
    """
    priorities = _normalize_priorities(priorities_raw)
    features = _extract_features(fire)

    grid = build_grid_for_fire(fire, cell_size_km=CELL_SIZE_KM)
    cells: List[GridCell] = grid["cells"]
    num_cells = len(cells)

    if num_cells == 0:
        return {
            "fireId": fire["id"],
            "rows": 0,
            "cols": 0,
            "cellSizeKm": CELL_SIZE_KM,
            "cells": [],
        }

    # If no severity grid passed, attempt to fetch from segment API.
    if severity_grid is None:
        severity_grid = _fetch_severity_grid(fire.get("id") or fire.get("fire_id", ""), segment_api_url)

    severity_resampled = _resample_severity_grid(severity_grid, grid["rows"], grid["cols"])

    def fitness(individual: List[int]) -> float:
        total = 0.0
        for idx, action_idx in enumerate(individual):
            total += score_action_for_cell(
                action_idx,
                cells[idx],
                grid,
                priorities,
                timeline,
                fire,
                features,
                severity_resampled[cells[idx].row][cells[idx].col],
            )
        return total / num_cells

    population = _init_population(num_cells, population_size)

    for _ in range(n_generations):
        scored = [(fitness(ind), ind) for ind in population]
        scored.sort(key=lambda x: x[0], reverse=True)

        new_population: List[List[int]] = [ind for _, ind in scored[:elitism]]

        while len(new_population) < population_size:
            parents = random.sample(scored[: len(scored) // 2], 2)
            child = _crossover(parents[0][1], parents[1][1])
            _mutate(child)
            new_population.append(child)

        population = new_population

    # final best individual
    best_score, best_individual = max(
        ((fitness(ind), ind) for ind in population), key=lambda x: x[0]
    )

    cells_payload = []
    for idx, cell in enumerate(cells):
        action_idx = best_individual[idx]
        action_name = ACTIONS[action_idx]
        action_score = score_action_for_cell(
            action_idx,
            cell,
            grid,
            priorities,
            timeline,
            fire,
            features,
            severity_resampled[cell.row][cell.col],
        )
        cells_payload.append(
            {
                "id": f"{fire['id']}-r{cell.row}-c{cell.col}",
                "row": cell.row,
                "col": cell.col,
                "centerLat": cell.center_lat,
                "centerLng": cell.center_lng,
                "north": cell.north,
                "south": cell.south,
                "east": cell.east,
                "west": cell.west,
                "action": action_name,
                "score": action_score,
                "severity": severity_resampled[cell.row][cell.col],
                "color": ACTION_COLORS.get(action_name, "#999999"),
            }
        )

    return {
        "fireId": fire["id"],
        "rows": grid["rows"],
        "cols": grid["cols"],
        "cellSizeKm": CELL_SIZE_KM,
        "populationScore": best_score,
        "cells": cells_payload,
    }
