from __future__ import annotations

import base64
import glob
import io
import json
import logging
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import time
import requests

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
    
import httpx
import numpy as np
import rasterio
from pathlib import Path
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from reburn.genetic_planner import plan_best_next_steps


logger = logging.getLogger("uvicorn.error")

# Add reburn module to path for imports
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(BACKEND_DIR, ".."))
REBURN_DIR = os.path.join(PROJECT_ROOT, "reburn")
if REBURN_DIR not in sys.path:
    sys.path.insert(0, REBURN_DIR)

# Import reburn prediction functions (optional - gracefully handle if not available)
try:
    from model_reburn import predict_reburn_risk, predict_reburn_risk_from_features
    REBURN_MODEL_AVAILABLE = True
    logger.info("Reburn prediction model loaded successfully")
except ImportError as e:
    REBURN_MODEL_AVAILABLE = False
    logger.warning(f"Reburn prediction model not available: {e}")
except FileNotFoundError as e:
    REBURN_MODEL_AVAILABLE = False
    logger.warning(f"Reburn model files not found: {e}")

# Data paths
DATA_ROOT = os.path.join(PROJECT_ROOT, "CA_data")


app = FastAPI(title="TerraNova Demo API", version="0.2.0")
# ==== Frontend paths ====
BASE_DIR = Path(__file__).resolve().parent.parent  # /UI_TEST3
FRONTEND_DIR = BASE_DIR
STYLES_DIR = BASE_DIR / "styles"
SCRIPTS_DIR = BASE_DIR / "scripts"

# Serve CSS & JS
app.mount("/styles", StaticFiles(directory=STYLES_DIR), name="styles")
app.mount("/scripts", StaticFiles(directory=SCRIPTS_DIR), name="scripts")

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_methods=["*"],
  allow_headers=["*"],
)

CALFIRE_ALL_URL = "https://terranova.prajaktashevakari.workers.dev/"

FIRES_CACHE: Dict[str, Any] = {
  "last_refresh": 0.0,
  "data": []  # List[dict]
}

CACHE_TTL_SECONDS = 300  # 5 minutes

FIRE_DATA_PATH = Path(PROJECT_ROOT) / "DATA" / "fires_master.json"
MODEL_SERVICE_URL = os.environ.get("MODEL_SERVICE_URL", "http://localhost:8002/predict")


def load_fire_catalog() -> List[Dict]:
  with open(FIRE_DATA_PATH) as f:
    entries = json.load(f)

  catalog = []
  for entry in entries:
    fire_id = entry.get("fire_id") or entry.get("id")
    name = entry.get("name") or entry.get("fire_name") or fire_id
    state = entry.get("state", "CA")
    acres_val = entry.get("acres")
    acres = acres_val if isinstance(acres_val, (int, float)) else 0
    start_date = entry.get("date") or ""
    lat = entry.get("lat") or 0.0
    lng = entry.get("lng") or 0.0
    summary = entry.get("summary") or f"{name} ({state})"
    catalog.append({
      "id": fire_id,
      "name": name,
      "state": state,
      "lat": lat,
      "lng": lng,
      "acres": acres,
      "start_date": start_date,
      "cause": entry.get("cause", "Unknown"),
      "summary": summary,
      "perimeter_radius": entry.get("perimeter_radius", 15000),
      "region": entry.get("region", state),
      "zipcode": entry.get("zipcode", ""),
      "mtbs_event_id": entry.get("mtbs_event_id", fire_id),
      "_raw": entry,
    })
  return catalog


def build_raster_map(catalog: List[Dict]) -> Dict[str, Dict[str, Path]]:
  mapping: Dict[str, Dict[str, Path]] = {}
  for fire in catalog:
    entry = fire.get("_raw", {})
    fire_id = fire["id"]
    post_name = entry.get("post_fire_file")
    pre_name = entry.get("pre_fire_file") or post_name
    if not post_name:
      continue
    base = Path("DATA") / "postfire_images"
    pre_path = base / pre_name
    post_path = base / post_name
    # Fallback to legacy CA_data/<fire_id>/ if files not present in DATA/postfire_images
    legacy_base = Path("CA_data") / fire_id
    if not pre_path.is_file() and (legacy_base / pre_name).is_file():
      pre_path = legacy_base / pre_name
    if not post_path.is_file() and (legacy_base / post_name).is_file():
      post_path = legacy_base / post_name
    # If pre is missing but post exists, reuse post for pre to allow segmentation
    if not pre_path.is_file() and post_path.is_file():
      pre_path = post_path
    mapping[fire_id] = {
      "pre": pre_path,
      "post": post_path,
    }
  return mapping


FIRE_CATALOG: List[Dict] = load_fire_catalog()
FIRE_LOOKUP: Dict[str, Dict] = {fire["id"]: fire for fire in FIRE_CATALOG}
FIRE_RASTER_MAP: Dict[str, Dict[str, Path]] = build_raster_map(FIRE_CATALOG)

TIMELINE_STAGES = [
  {"value": 0, "label": "Pre-fire baseline", "description": "Vegetation health before ignition", "days_from_ignition": -30},
  {"value": 1, "label": "Active response (Day 0)", "description": "Fire perimeter with live suppression actions", "days_from_ignition": 0},
  {"value": 2, "label": "Initial assessment (Day 7)", "description": "First MTBS-inspired burn severity mapping", "days_from_ignition": 7},
  {"value": 3, "label": "Stabilization phase (Day 30)", "description": "Treatment crews in the field; erosion control active", "days_from_ignition": 30},
  {"value": 4, "label": "Recovery outlook (Year 1)", "description": "Predicted vegetation recovery and infrastructure repairs", "days_from_ignition": 365},
]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
  return max(low, min(high, value))


def resolve_raster_paths(fire_id: str) -> Dict[str, Path]:
  paths = FIRE_RASTER_MAP.get(fire_id)
  if not paths:
    raise HTTPException(status_code=404, detail=f"No rasters configured for fire {fire_id}")

  resolved = {}
  for key, path in paths.items():
    full_path = path if path.is_absolute() else Path(PROJECT_ROOT) / path
    if not full_path.is_file():
      raise HTTPException(status_code=404, detail=f"Missing raster for fire {fire_id}: {full_path}")
    resolved[key] = full_path
  return resolved


def build_pre_post_stack(fire_id: str) -> bytes:
  """Load rasters, align shapes, and emit a GeoTIFF in-memory.
  Default is 6-channel post-fire only to match the 6-channel checkpoint. Set
  SEGMENTATION_CHANNELS=12 if you switch to a 12-channel model."""
  paths = resolve_raster_paths(fire_id)
  pre_path, post_path = paths["pre"], paths["post"]

  def safe_read(ds: rasterio.io.DatasetReader, idxs):
    """Read dataset window-by-window, filling zeros on read errors."""
    count = len(idxs)
    out = np.zeros((count, ds.height, ds.width), dtype=ds.dtypes[0])
    for _, window in ds.block_windows(1):
      try:
        block = ds.read(indexes=idxs, window=window)
      except Exception as exc:
        logger.error("Read failed for %s window %s: %s", ds.name, window, exc)
        block = np.zeros((count, window.height, window.width), dtype=ds.dtypes[0])
      out[:, window.row_off:window.row_off+window.height, window.col_off:window.col_off+window.width] = block
    return out

  def _readable(ds, label: str):
    try:
      ds.read(1, window=((0, 1), (0, 1)))
      return True
    except Exception as exc:
      logger.error("Unreadable %s raster for %s (%s): %s", label, fire_id, ds.name, exc)
      raise HTTPException(status_code=500, detail=f"Unreadable {label} raster for {fire_id}: {exc}")

  with rasterio.open(pre_path) as pre_ds, rasterio.open(post_path) as post_ds:
    _readable(pre_ds, "pre")
    _readable(post_ds, "post")
    if pre_ds.count < 6 or post_ds.count < 6:
      raise HTTPException(status_code=400, detail="Expected at least 6 bands in both pre and post rasters")

    try:
      pre_data = safe_read(pre_ds, list(range(1, 7)))
    except Exception as exc:
      logger.error("Failed reading pre-fire raster for %s: %s", fire_id, exc)
      raise HTTPException(status_code=500, detail=f"Failed to read pre-fire raster for {fire_id}")
    try:
      post_data = safe_read(post_ds, list(range(1, 7)))
    except Exception as exc:
      logger.error("Failed reading post-fire raster for %s: %s", fire_id, exc)
      raise HTTPException(status_code=500, detail=f"Failed to read post-fire raster for {fire_id}")

    height = min(pre_data.shape[1], post_data.shape[1])
    width = min(pre_data.shape[2], post_data.shape[2])
    pre_data = pre_data[:, :height, :width]
    post_data = post_data[:, :height, :width]

    meta = pre_ds.meta.copy()
    # Default to 6-channel post-fire only, matching the current checkpoint.
    use_post_only = os.environ.get("SEGMENTATION_CHANNELS", "6").lower() == "6"
    if use_post_only:
      stacked = post_data
      meta.update({"count": 6, "height": height, "width": width, "dtype": stacked.dtype})
    else:
      stacked = np.concatenate([pre_data, post_data], axis=0)
      meta.update({"count": 12, "height": height, "width": width, "dtype": stacked.dtype})

    with MemoryFile() as memfile:
      with memfile.open(**meta) as dst:
        dst.write(stacked)
      return memfile.read()


def get_reference_grid(fire_id: str):
  """Return reference transform/CRS/size from post-fire raster for alignment."""
  paths = resolve_raster_paths(fire_id)
  post_path = paths["post"]
  with rasterio.open(post_path) as ds:
    return {
      "transform": ds.transform,
      "crs": ds.crs,
      "width": ds.width,
      "height": ds.height,
    }


def compute_severity_grid(mask: np.ndarray, bounds) -> List[List[int]]:
  """Aggregate mask into ~1km tiles (majority class per tile)."""
  height, width = mask.shape
  try:
    minx, miny = bounds[0]
    maxx, maxy = bounds[1]
    pixel_size = abs((maxx - minx) / width) if width else 30.0
  except Exception:
    pixel_size = 30.0

  tile_px = max(1, int(round(1000.0 / pixel_size)))
  grid: List[List[int]] = []
  for row in range(0, height, tile_px):
    row_vals = []
    for col in range(0, width, tile_px):
      block = mask[row:row + tile_px, col:col + tile_px]
      if block.size == 0:
        row_vals.append(0)
        continue
      counts = np.bincount(block.flatten(), minlength=6)
      row_vals.append(int(counts.argmax()))
    grid.append(row_vals)
  return grid

async def compute_burn_summary(fire: Dict) -> Dict[str, Any]:
  """
  Use the existing segmentation model to summarize burn patterns for a fire.

  This DOES NOT change your teammate's U-Net code. It simply reuses the same
  segmentation service (run_segmentation) and aggregates the classes into
  High / Moderate / Low / Unburned for the dashboard pie chart.
  """
  fire_id = fire["id"]

  try:
    data = await run_segmentation(fire_id)
    mask_b64 = data.get("mask_png_base64")
    if not mask_b64:
      raise ValueError("Segmentation response missing mask_png_base64")

    # Decode the segmentation mask (classes 0–5)
    png_bytes = base64.b64decode(mask_b64)
    img = Image.open(io.BytesIO(png_bytes)).convert("P")
    mask = np.array(img, dtype=np.uint8)

    height, width = mask.shape
    bounds = data.get("bounds")
    # Default Landsat resolution if bounds are missing
    pixel_area_m2 = 30.0 * 30.0

    if (
      bounds
      and isinstance(bounds, (list, tuple))
      and len(bounds) == 2
      and isinstance(bounds[0], (list, tuple))
      and isinstance(bounds[1], (list, tuple))
    ):
      try:
        minx, miny = bounds[0]
        maxx, maxy = bounds[1]
        pixel_width = (maxx - minx) / float(width or 1)
        pixel_height = (maxy - miny) / float(height or 1)
        pixel_area_m2 = abs(pixel_width * pixel_height) or pixel_area_m2
      except Exception:
        logger.exception("Failed to infer pixel area from bounds; using 30m default")

    # Convert pixel area to acres (1 acre ≈ 4046.8564224 m²)
    pixel_area_acres = pixel_area_m2 / 4046.8564224

    # Count pixels per class (0–5)
    counts = np.bincount(mask.flatten(), minlength=6)
    unburned_px = int(counts[0])
    low_px = int(counts[1] + counts[2])
    moderate_px = int(counts[3])
    high_px = int(counts[4] + counts[5])

    # Aggregate into 4 buckets for the chart
    labels = ["High", "Moderate", "Low", "Unburned"]
    class_pixels = [high_px, moderate_px, low_px, unburned_px]
    total_px = sum(class_pixels) or 1

    percent = [round((c * 100.0) / total_px, 1) for c in class_pixels]

    burned_px = high_px + moderate_px + low_px
    burned_acres = burned_px * pixel_area_acres
    unburned_acres = unburned_px * pixel_area_acres
    total_acres = burned_acres + unburned_acres

    return {
      "burn": {
        "labels": labels,
        "count": [int(c) for c in class_pixels],
        "percent": percent,
      },
      "acres": {
        "burned": round(float(burned_acres), 1),
        "unburned": round(float(unburned_acres), 1),
        "total": round(float(total_acres), 1),
      },
    }

  except Exception:
    # If segmentation fails, fall back to a simple heuristic based on fire["acres"]
    logger.exception("Failed to compute burn summary from segmentation for %s", fire_id)
    total_acres = float(fire.get("acres") or 0.0)
    # Simple, safe fallback: assume 60% burned, split across High/Mod/Low
    burned_acres = total_acres * 0.6
    unburned_acres = max(total_acres - burned_acres, 0.0)

    labels = ["High", "Moderate", "Low", "Unburned"]
    percent = [20.0, 20.0, 20.0, 40.0]

    return {
      "burn": {
        "labels": labels,
        "count": [],  # optional; dashboard only uses labels+percent
        "percent": percent,
      },
      "acres": {
        "burned": round(float(burned_acres), 1),
        "unburned": round(float(unburned_acres), 1),
        "total": round(float(total_acres), 1),
      },
    }


async def run_segmentation(fire_id: str, model_url: Optional[str] = None) -> Dict:
  """Call model service with prepared stack and return parsed JSON."""
  tif_bytes = build_pre_post_stack(fire_id)
  target_url = model_url or MODEL_SERVICE_URL
  logger.info("Calling model service %s for fire %s (stack bytes=%s)", target_url, fire_id, len(tif_bytes))

  async with httpx.AsyncClient(timeout=60.0) as client:
    resp = await client.post(target_url, files={"tif": ("chip.tif", tif_bytes, "image/tiff")})

  if resp.status_code != 200:
    logger.error("Model service error (%s) for %s: %s", resp.status_code, fire_id, resp.text)
    raise HTTPException(status_code=resp.status_code, detail=resp.text)
  return resp.json()


def pick_fire(fire_id: Optional[str]) -> Dict:
  if fire_id and fire_id in FIRE_LOOKUP:
    return FIRE_LOOKUP[fire_id]
  return FIRE_CATALOG[0]


def parse_priority(value: Optional[float], fallback: float) -> float:
  if value is None:
    value = fallback
  return clamp(float(value) / 100.0, 0.05, 1.0)


def normalize_priorities(raw: Dict[str, float]) -> Dict[str, float]:
  total = sum(raw.values())
  if total == 0:
    return {k: 1 / len(raw) for k in raw}
  return {k: v / total for k, v in raw.items()}


def jitter_coords(lat: float, lng: float, delta: float = 0.05) -> List[float]:
  return [
    round(lat + random.uniform(-delta, delta), 4),
    round(lng + random.uniform(-delta, delta), 4),
  ]


def get_timeline_meta(stage: int) -> Dict:
  idx = clamp(stage, 0, len(TIMELINE_STAGES) - 1)
  return TIMELINE_STAGES[int(idx)]


def generate_hotspots(fire: Dict) -> List[Dict]:
  base_lat, base_lng = fire["lat"], fire["lng"]
  hotspots = []
  for idx in range(3):
    coords = jitter_coords(base_lat, base_lng, delta=0.08)
    hotspots.append({
      "id": f"{fire['id']}-sector-{idx}",
      "title": f"Sector {idx + 1}",
      "details": random.choice([
        "Watershed slopes showing hydrophobic soils.",
        "Dense structure grid; ember threat remains.",
        "Steep canyon with unstable ash covering.",
        "Riparian corridor experiencing debris deposition.",
      ]),
      "coords": coords,
    })
  return hotspots


def generate_layers(fire: Dict, timeline_meta: Dict, priorities: Dict[str, float]) -> Dict[str, List[Dict]]:
  stage_index = timeline_meta["value"]
  decay = 1 - (stage_index / (len(TIMELINE_STAGES) - 1)) * 0.55
  layers: Dict[str, List[Dict]] = {
    "burnSeverity": [],
    "reburnRisk": [],
    "bestNextSteps": [],
  }

  color_map = {
    "burnSeverity": "#ff4e1f",
    "reburnRisk": "#ff6b35",
    "bestNextSteps": "#4ecdc4",
  }

  base_radius = fire["perimeter_radius"]
  center_lat, center_lng = fire["lat"], fire["lng"]

  for layer_key in layers.keys():
    weight = priorities.get({
      "burnSeverity": "community",
      "reburnRisk": "community",
      "bestNextSteps": "community",
    }[layer_key], 0.25)

    for _ in range(2):
      coords = jitter_coords(center_lat, center_lng, delta=0.1)
      radius = int(base_radius * (0.6 + weight * 0.8) * decay * random.uniform(0.8, 1.2))
      intensity = clamp((0.55 + weight * 0.5) * decay + random.uniform(-0.08, 0.08))
      layers[layer_key].append({
        "coords": coords,
        "radius": max(8000, radius),
        "color": color_map[layer_key],
        "intensity": round(intensity, 2),
      })

  return layers


def summarize_priorities(priorities: Dict[str, float]) -> List[Dict]:
  labels = {
    "community": "Community safety",
    "watershed": "Watershed health",
    "infrastructure": "Infrastructure readiness",
  }
  summaries = {
    "community": "Focus on structure protection and WUI buffers.",
    "watershed": "Stabilize slopes and protect drinking water sheds.",
    "infrastructure": "Keep roads, utilities, and comms online.",
  }
  result = []
  for key, value in priorities.items():
    result.append({
      "label": labels[key],
      "score": round(value * 100),
      "summary": summaries[key],
    })
  result.sort(key=lambda item: item["score"], reverse=True)
  return result


def generate_next_steps(fire: Dict, priorities: Dict[str, float], timeline_meta: Dict) -> List[str]:
  top_priority = max(priorities, key=priorities.get)
  steps = []
  if top_priority == "community":
    steps.append(f"Pre-position structure protection crews along the {fire['region']} fringe.")
    steps.append("Activate text alerts that explain road closures in plain language.")
  elif top_priority == "watershed":
    steps.append("Deploy BAER teams to seed and mulch high-severity headwaters.")
    steps.append("Stage portable sediment traps to guard downstream intakes.")
  else:
    steps.append("Inspect primary transmission corridors and backup fiber routes.")
    steps.append("Schedule quick-build repairs for scorched culverts and bridges.")

  steps.append(f"Update the {timeline_meta['label'].lower()} briefing and push to local EOCs.")
  return steps


def generate_insights(fire: Dict, timeline_meta: Dict) -> List[Dict]:
  return [
    {
      "category": "Action",
      "title": "Crew routing",
      "detail": f"Assign crews to {fire['region']} ridge within {timeline_meta['label'].split()[0]} window.",
    },
    {
      "category": "Monitoring",
      "title": "Hydrology sensors",
      "detail": "4 gauges tripped thresholds; auto-sync data every 15 minutes.",
    },
    {
      "category": "Community",
      "title": "Next briefing",
      "detail": "Upload narrated map to public viewer and share short link.",
    },
  ]


def format_stats(fire: Dict) -> Dict:
  raw = fire.get("_raw", {})
  temp_c = raw.get("avg_temp_c")
  temp_f = round((temp_c * 9/5) + 32) if isinstance(temp_c, (int, float)) else random.choice([68, 72, 75, 78])
  condition = "Sunny"
  weather = f"{temp_f}°F, {condition}"

  # Try to get real reburn risk prediction from ML model
  reburn_risk = "Medium"  # Default fallback
  if REBURN_MODEL_AVAILABLE:
    try:
      fire_id = fire.get("id")
      if fire_id:
        prediction = predict_reburn_risk(fire_id, return_confidence=True)
        reburn_risk = prediction["risk_level"]
    except (ValueError, FileNotFoundError):
      # Fire not in dataset or model not available - use fallback based on land_burned_frequency
      freq = raw.get("land_burned_frequency", 0)
      if freq and freq > 0:
        reburn_risk = "High" if freq > 1 else "Medium"
      else:
        reburn_risk = "Low"
    except Exception as e:
      logger.warning(f"Error predicting reburn risk for {fire.get('id')}: {e}")
  else:
    # Fallback to heuristic based on land_burned_frequency
    freq = raw.get("land_burned_frequency", 0)
    if freq and freq > 0:
      reburn_risk = "High" if freq > 1 else "Medium"
    else:
      reburn_risk = "Low"

  incidents = raw.get("incidents") or random.randint(3, 8)
  updated = f"{fire.get('region', fire.get('state', ''))} · Updated {random.randint(15, 80)} mins ago"
  return {
    "weather": weather,
    "reburnRisk": reburn_risk,
    "incidents": incidents,
    "updated": updated,
    "acres": fire["acres"],
  }


def _normalize_calfire_incident(item: dict) -> dict:
  # Make it match your frontend’s expected shape.
  # Add/remove fields here as needed.
  start_raw = item.get("StartedDateOnly") or item.get("Started") or ""
  start_date = start_raw[:10] if isinstance(start_raw, str) else ""

  return {
    "id": item.get("UniqueId") or item.get("Id") or item.get("Name"),
    "name": item.get("Name") or "Unknown Fire",
    "state": "CA",
    "lat": item.get("Latitude"),
    "lng": item.get("Longitude"),
    "acres": item.get("AcresBurned"),
    "start_date": start_date,
    "county": item.get("County"),
    "location": item.get("Location"),
    "percent_contained": item.get("PercentContained"),
    "is_active": item.get("IsActive"),
    "updated": item.get("Updated"),
    "url": item.get("Url"),
    "type": item.get("Type"),
  }

def _refresh_fires_cache(force: bool = False) -> None:
  now = time.time()
  if (not force) and (now - FIRES_CACHE["last_refresh"] < CACHE_TTL_SECONDS):
    return

  try:
    resp = requests.get(CALFIRE_ALL_URL, timeout=15)
    resp.raise_for_status()

    raw = resp.json()
    normalized = []
    for x in raw:
      lat, lng = x.get("Latitude"), x.get("Longitude")
      if lat is None or lng is None:
        continue
      normalized.append(_normalize_calfire_incident(x))

    # Sort "most recent first": updated desc (fallback to start_date)
    normalized.sort(
      key=lambda f: (f.get("updated") or "", f.get("start_date") or ""),
      reverse=True
    )

    FIRES_CACHE["data"] = normalized
    FIRES_CACHE["last_refresh"] = now
  except Exception as e:
    logger.warning(f"Failed to refresh fires cache from external API: {e}")
    # Don't update cache on failure, will use existing data or fallback to local catalog


@app.get("/api/fires")
async def list_fires(
  state: Optional[str] = Query(None, description="Filter by state code (e.g., CA, OR)"),
  year: Optional[int] = Query(None, description="Filter by year"),
  source: Optional[str] = Query(None, description="Data source: 'local' for local catalog, 'live' for external API, default uses local"),
):
  """
  Returns list of fires, optionally filtered by state and year.
  Results are sorted by most recent first.
  
  By default uses the local fire catalog (data/fires_master.json).
  Pass source=live to fetch from external CAL FIRE API.
  """
  # Use local catalog by default, external API only if explicitly requested
  if source == "live":
    _refresh_fires_cache()
    filtered_fires = list(FIRES_CACHE["data"])
  else:
    # Use local fire catalog from data/fires_master.json
    filtered_fires = list(FIRE_CATALOG)

  # Apply filters
  if state:
    state_upper = state.upper().strip()
    filtered_fires = [f for f in filtered_fires if (f.get("state") or "").upper() == state_upper]

  if year:
    filtered_fires = [
      f for f in filtered_fires
      if f.get("start_date") and int(str(f["start_date"]).split("-")[0]) == year
    ]

  # Sort by year descending (newest first)
  def get_sort_key(fire: Dict) -> tuple:
    date_str = fire.get("start_date", "") or ""
    if date_str:
      try:
        parts = date_str.split("-")
        if len(parts) >= 3:
          y = int(parts[0])
          m = int(parts[1])
          d = int(parts[2])
          return (-y, -m, -d)
      except (ValueError, IndexError):
        pass
    return (0, 0, 0)

  filtered_fires = sorted(filtered_fires, key=get_sort_key)

  return filtered_fires


@app.get("/api/scenario")
async def get_scenario(
  fireId: Optional[str] = Query(None, description="Fire identifier"),
  timeline: int = Query(2, ge=0, le=4),
  priorityCommunity: int = Query(70, ge=0, le=100),
  priorityWatershed: int = Query(55, ge=0, le=100),
  priorityInfrastructure: int = Query(60, ge=0, le=100),
):
  fire = pick_fire(fireId)
  timeline_meta = get_timeline_meta(timeline)

  raw_priorities = {
    "community": parse_priority(priorityCommunity, 70),
    "watershed": parse_priority(priorityWatershed, 55),
    "infrastructure": parse_priority(priorityInfrastructure, 60),
  }
  normalized_priorities = normalize_priorities(raw_priorities)

  layers = generate_layers(fire, timeline_meta, normalized_priorities)
  priorities_summary = summarize_priorities(normalized_priorities)
  hotspots = generate_hotspots(fire)
  next_steps = generate_next_steps(fire, normalized_priorities, timeline_meta)
  insights = generate_insights(fire, timeline_meta)
  stats = format_stats(fire)

  # 🔹 NEW: run the genetic planner using the full raw fire record
  # fire["_raw"] is the original entry from fires_master.json with westbc/eastbc/northbc/southbc, etc.
  raw_fire_record = fire.get("_raw", fire)
  grid_plan = plan_best_next_steps(
      fire=raw_fire_record,
      priorities_raw=raw_priorities,  # let GA do its own normalization
      timeline=timeline,
  )

  response = {
    "fire": {
      "id": fire["id"],
      "name": fire["name"],
      "state": fire["state"],
      "region": fire["region"],
      "summary": fire["summary"],
      "acres": fire["acres"],
      "startDate": fire["start_date"],
      "cause": fire["cause"],
      "center": [fire["lat"], fire["lng"]],
    },
    "timeline": timeline_meta,
    "stats": stats,
    "layers": layers,
    "markers": hotspots,
    "priorities": priorities_summary,
    "nextSteps": next_steps,
    "mapTip": f"{timeline_meta['label']} · {timeline_meta['description']}",
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    # 🔹 NEW: 1km x 1km grid of “best next steps” for the map layer
    "gridPlan": grid_plan,
  }
  return response


@app.post("/api/segment")
async def segment_fire(
  fireId: str = Query(..., description="Fire identifier"),
  modelUrl: Optional[str] = Query(None, description="Override model service URL"),
):
  """
  Build a pre+post stack for the requested fire and forward to the segmentation service.
  Returns a base64 PNG mask plus spatial metadata (bounds/CRS/size) for map overlay.
  """
  target_url = modelUrl or MODEL_SERVICE_URL
  data = await run_segmentation(fireId, target_url)

  severity_grid: List[List[int]] = []
  if data.get("mask_png_base64") and data.get("bounds"):
    try:
      png_bytes = base64.b64decode(data["mask_png_base64"])
      mask = np.array(Image.open(io.BytesIO(png_bytes)).convert("P"), dtype=np.uint8)
      severity_grid = compute_severity_grid(mask, data.get("bounds"))
    except Exception:
      logger.exception("Failed to compute severity grid for %s", fireId)

  return {
    "fireId": fireId,
    "maskPng": data.get("mask_png_base64"),
    "bounds": data.get("bounds"),
    "crs": data.get("crs"),
    "size": {"width": data.get("width"), "height": data.get("height")},
    "palette": data.get("palette_rgb"),
    "classes": data.get("classes"),
    "modelUrl": target_url,
    "severities_grid": severity_grid,
  }


@app.get("/api/segment-mask/{fire_id}.tif")
async def segment_mask_tif(fire_id: str):
  """
  Run segmentation and return a georeferenced GeoTIFF mask for frontend georaster overlay.
  Class 0 remains in the data (client can render transparent).
  """
  try:
    data = await run_segmentation(fire_id)

    if not data.get("mask_png_base64") or not data.get("bounds"):
      raise HTTPException(status_code=500, detail="Segmentation response missing data")

    png_bytes = base64.b64decode(data["mask_png_base64"])
    img = Image.open(io.BytesIO(png_bytes)).convert("P")
    mask = np.array(img, dtype=np.uint8)

    # Trust the mask array dimensions; ignore declared size if it disagrees.
    height, width = mask.shape
    bounds = data["bounds"]
    crs_str = data.get("crs", "EPSG:4326")
    logger.info("Segment mask for %s: mask shape %sx%s, bounds=%s, crs=%s", fire_id, width, height, bounds, crs_str)

    minx, miny = bounds[0]
    maxx, maxy = bounds[1]

    pixel_width = (maxx - minx) / width
    pixel_height = (maxy - miny) / height
    transform = from_origin(minx, maxy, pixel_width, pixel_height)

    # Reproject onto the original post-fire raster grid to match previous overlays
    ref = get_reference_grid(fire_id)
    dst_crs = ref["crs"]
    dst_transform = ref["transform"]
    dst_width = ref["width"]
    dst_height = ref["height"]

    src_crs = CRS.from_string(crs_str)

    try:
      from rasterio.warp import reproject, Resampling
      dst_mask = np.zeros((dst_height, dst_width), dtype=mask.dtype)
      reproject(
        source=mask,
        destination=dst_mask,
        src_transform=transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.nearest,
      )
      mask = dst_mask
      transform = dst_transform
      width, height = dst_width, dst_height
      src_crs = dst_crs
      logger.info("Reprojected mask for %s onto reference grid (%sx%s)", fire_id, width, height)
    except Exception:
      logger.exception("Reprojection to reference grid failed for %s; returning source grid", fire_id)

    with MemoryFile() as memfile:
      with memfile.open(
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=mask.dtype,
        crs=src_crs,
        transform=transform,
      ) as dst:
        dst.write(mask, 1)
      tif_bytes = memfile.read()

    return StreamingResponse(io.BytesIO(tif_bytes), media_type="image/tiff")

  except HTTPException:
    # Already meaningful; let FastAPI handle.
    raise
  except Exception as exc:
    logger.exception("Failed to build segment mask for %s", fire_id)
    raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/ask")
async def ask_about_fire(fireId: str = Query("camp-fire-2018"), question: str = Query("")):
  """
  Simple LLM-style Q&A endpoint that returns plain-language fire summaries.
  In production, replace this with actual LLM calls (OpenAI, Anthropic, etc.).
  """
  fire_info = next((f for f in FIRE_CATALOG if f["id"] == fireId), FIRE_CATALOG[0])
  
  # Template-based responses for common questions
  question_lower = question.lower()
  
  if "cause" in question_lower or "start" in question_lower or "ignit" in question_lower:
    answer = f"The {fire_info['name']} started on {fire_info['startDate']} in {fire_info['region']}, {fire_info['state']}. The cause was determined to be {fire_info['cause'].lower()}."
  
  elif "damage" in question_lower or "severe" in question_lower or "impact" in question_lower:
    answer = f"The {fire_info['name']} burned approximately {fire_info['acres']:,} acres. {fire_info['summary']} Our burn severity model classifies the area into high, moderate, and low severity zones to help prioritize recovery efforts."
  
  elif "when" in question_lower or "date" in question_lower:
    answer = f"The {fire_info['name']} ignited on {fire_info['startDate']}. The initial MTBS-style assessment typically occurs within 7 days of ignition, with follow-up mapping at 30 days and long-term recovery tracking extending to 1-5 years."
  
  elif "where" in question_lower or "location" in question_lower:
    answer = f"The {fire_info['name']} occurred in {fire_info['region']}, {fire_info['state']}. You can see the exact location on the map above, with burn severity overlays showing the spatial extent of damage."
  
  elif "recovery" in question_lower or "rehab" in question_lower or "restoration" in question_lower:
    answer = f"Recovery from the {fire_info['name']} is ongoing. Our model tracks burn severity changes over time, helping land managers prioritize watershed stabilization, erosion control, and vegetation reseeding. Adjust the forecast slider to see predicted recovery at different time horizons."
  
  elif "model" in question_lower or "algorithm" in question_lower or "how" in question_lower:
    answer = f"Our burn severity segmentation model analyzes Landsat imagery to classify each 30m pixel as unburned, low, moderate, or high severity. The model was trained on MTBS reference data and uses spectral indices (NDVI, NBR) to detect vegetation loss. The priority sliders let you weight community safety, watershed health, and infrastructure concerns to customize the analysis."
  
  else:
    answer = f"The {fire_info['name']} burned {fire_info['acres']:,} acres in {fire_info['region']}, {fire_info['state']}, starting {fire_info['startDate']}. Cause: {fire_info['cause']}. {fire_info['summary']} Use the map controls to explore burn severity layers, adjust priorities, and see how conditions change over time. Ask more specific questions about the fire's cause, damage, location, recovery, or our modeling approach."
  
  return {
    "fireId": fireId,
    "question": question,
    "answer": answer,
    "generatedAt": datetime.now(timezone.utc).isoformat(),
  }


@app.get("/api/burn-severity/{fire_id}.tif")
async def get_burn_severity_raster(fire_id: str):
  """
  Returns MTBS GeoTIFF raster file (dnbr6.tif) for burn severity.
  
  Maps fire_id to MTBS event_id and finds the dnbr6.tif file.
  """
  fire = pick_fire(fire_id)
  mtbs_event_id = fire.get("mtbs_event_id")
  
  if not mtbs_event_id:
    raise HTTPException(
      status_code=404,
      detail=f"No MTBS data available for fire: {fire_id}"
    )
  
  # GeoTIFF data now lives under UI_TEST3/CA_data/{mtbs_event_id}
  ca_data_dir = os.path.join(DATA_ROOT, mtbs_event_id)
  
  if not os.path.exists(ca_data_dir):
    raise HTTPException(
      status_code=404,
      detail=f"MTBS data directory not found: {ca_data_dir}"
    )
  
  # Look for dnbr6.tif file (pattern: {event_id}_*_dnbr6.tif)
  pattern = os.path.join(ca_data_dir, f"{mtbs_event_id}_*_dnbr6.tif")
  matching_files = glob.glob(pattern)
  
  if not matching_files:
    raise HTTPException(
      status_code=404,
      detail=f"MTBS burn severity raster (dnbr6.tif) not found for fire: {fire_id}"
    )
  
  file_path = matching_files[0]  # Use first match
  
  return FileResponse(
    file_path,
    media_type="image/tiff",
    headers={
      "Content-Disposition": f"inline; filename={fire_id}_burn_severity.tif",
      "Access-Control-Allow-Origin": "*"
    }
  )


@app.get("/api/reburn-risk/{fire_id}.tif")
async def get_reburn_risk_raster(fire_id: str):
  """
  Returns GeoTIFF raster file for reburn risk classification.
  Maps fire_id to MTBS event_id and finds the reburn_risk.tif file.
  """
  fire = pick_fire(fire_id)
  mtbs_event_id = fire.get("mtbs_event_id")
  
  if not mtbs_event_id:
    raise HTTPException(
      status_code=404,
      detail=f"No MTBS data available for fire: {fire_id}"
    )
  
  # GeoTIFF data now lives under UI_TEST3/CA_data/{mtbs_event_id}
  ca_data_dir = os.path.join(DATA_ROOT, mtbs_event_id)
  
  if not os.path.exists(ca_data_dir):
    raise HTTPException(
      status_code=404,
      detail=f"MTBS data directory not found: {ca_data_dir}"
    )
  
  # Look for reburn_risk.tif file (pattern: {event_id}_*_reburn_risk.tif)
  pattern = os.path.join(ca_data_dir, f"{mtbs_event_id}_*_reburn_risk.tif")
  matching_files = glob.glob(pattern)
  
  if not matching_files:
    raise HTTPException(
      status_code=404,
      detail=f"Reburn risk raster not found for fire: {fire_id}"
    )
  
  file_path = matching_files[0]  # Use first match
  
  return FileResponse(
    file_path,
    media_type="image/tiff",
    headers={
      "Content-Disposition": f"inline; filename={fire_id}_reburn_risk.tif",
      "Access-Control-Allow-Origin": "*"
    }
  )


@app.get("/api/best-next-steps/{fire_id}.tif")
async def get_best_next_steps_raster(fire_id: str):
  """
  Returns GeoTIFF raster file for best next steps classification (grid-based).
  Maps fire_id to MTBS event_id and finds the best_next_steps_grid.tif file.
  """
  fire = pick_fire(fire_id)
  mtbs_event_id = fire.get("mtbs_event_id")
  
  if not mtbs_event_id:
    raise HTTPException(
      status_code=404,
      detail=f"No MTBS data available for fire: {fire_id}"
    )
  
  # GeoTIFF data now lives under UI_TEST3/CA_data/{mtbs_event_id}
  ca_data_dir = os.path.join(DATA_ROOT, mtbs_event_id)
  
  if not os.path.exists(ca_data_dir):
    raise HTTPException(
      status_code=404,
      detail=f"MTBS data directory not found: {ca_data_dir}"
    )
  
  # Look for best_next_steps_grid.tif file (prefer grid version)
  pattern_grid = os.path.join(ca_data_dir, f"{mtbs_event_id}_*_best_next_steps_grid.tif")
  matching_files = glob.glob(pattern_grid)
  
  # Fallback to non-grid version if grid doesn't exist
  if not matching_files:
    pattern = os.path.join(ca_data_dir, f"{mtbs_event_id}_*_best_next_steps.tif")
    matching_files = glob.glob(pattern)
  
  if not matching_files:
    raise HTTPException(
      status_code=404,
      detail=f"Best next steps raster not found for fire: {fire_id}"
    )
  
  file_path = matching_files[0]  # Use first match
  
  return FileResponse(
    file_path,
    media_type="image/tiff",
    headers={
      "Content-Disposition": f"inline; filename={fire_id}_best_next_steps.tif",
      "Access-Control-Allow-Origin": "*"
    }
  )


@app.get("/api/predict-reburn-risk")
async def predict_reburn_risk_endpoint(
  fireId: Optional[str] = Query(None, description="Fire ID to look up in dataset (e.g., 'ca3617411872220040812')"),
  elevation_m: Optional[float] = Query(None, description="Elevation in meters"),
  avg_temp_c: Optional[float] = Query(None, description="Average temperature in Celsius"),
  soil_moisture_pct: Optional[float] = Query(None, description="Soil moisture percentage"),
  gw_depth_ft: Optional[float] = Query(None, description="Groundwater depth in feet"),
  ph_val: Optional[float] = Query(None, description="pH value"),
  precip_mm: Optional[float] = Query(None, description="Precipitation in mm"),
  land_burned_frequency: Optional[int] = Query(None, description="Land burned frequency (integer)"),
  state: Optional[str] = Query(None, description="State code (e.g., 'CA')"),
):
  """
  Predict reburn risk for a fire.
  
  Two modes:
  1. Lookup mode: Provide fireId to look up features from dataset
  2. Direct input mode: Provide all feature values directly
  
  Returns prediction with probability, risk level, and confidence.
  """
  if not REBURN_MODEL_AVAILABLE:
    raise HTTPException(
      status_code=503,
      detail="Reburn prediction model not available. Please ensure the model has been trained and model_reburn.py is accessible."
    )
  
  try:
    # Mode 1: Lookup by fireId
    if fireId:
      prediction = predict_reburn_risk(fireId, return_confidence=True)
      return {
        **prediction,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
      }
    
    # Mode 2: Direct feature input
    # Check if all required features are provided
    required_features = {
      "elevation_m": elevation_m,
      "avg_temp_c": avg_temp_c,
      "soil_moisture_pct": soil_moisture_pct,
      "gw_depth_ft": gw_depth_ft,
      "ph_val": ph_val,
      "precip_mm": precip_mm,
      "land_burned_frequency": land_burned_frequency,
      "state": state,
    }
    
    missing = [k for k, v in required_features.items() if v is None]
    if missing:
      raise HTTPException(
        status_code=400,
        detail=f"Missing required features for direct input mode: {', '.join(missing)}. "
               f"Either provide 'fireId' for lookup mode, or provide all feature values."
      )
    
    features = {
      "elevation_m": float(elevation_m),
      "avg_temp_c": float(avg_temp_c),
      "soil_moisture_pct": float(soil_moisture_pct),
      "gw_depth_ft": float(gw_depth_ft),
      "ph_val": float(ph_val),
      "precip_mm": float(precip_mm),
      "land_burned_frequency": int(land_burned_frequency),
      "state": str(state),
    }
    
    prediction = predict_reburn_risk_from_features(features, return_confidence=True)
    return {
      **prediction,
      "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    
  except ValueError as e:
    raise HTTPException(status_code=404, detail=str(e))
  except FileNotFoundError as e:
    raise HTTPException(
      status_code=503,
      detail="Model or dataset not available. Please ensure the model has been trained."
    )
  except Exception as e:
    logger.exception(f"Prediction error for fireId={fireId}")
    raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")


@app.get("/api/analysis-summary")
async def analysis_summary(
  fireId: str = Query(..., description="Fire identifier for analysis dashboard"),
):
  """
  Aggregate burn-severity and reburn metrics for the analysis dashboard.

  This calls the existing segmentation service (run_segmentation) to compute:
    - High / Moderate / Low / Unburned % (for the pie chart)
    - Burned vs unburned acres
  And it reuses the reburn model / heuristics for:
    - reburnRiskPercent
    - historicFireCount
  """
  # 1) Resolve fire object from catalog
  fire = pick_fire(fireId)
  raw = fire.get("_raw", {}) or {}

  # 2) Burn pattern & acres (from segmentation)
  burn_acres_summary = await compute_burn_summary(fire)

  # 3) Historic fire count (if available in your JSON)
  historic_count = raw.get("land_burned_frequency") or raw.get("historic_fire_count") or 0
  try:
    historic_count = int(historic_count)
  except (TypeError, ValueError):
    historic_count = 0

  # 4) Reburn risk percent & level
  reburn_percent = 0
  reburn_level = "Low"

  if REBURN_MODEL_AVAILABLE:
    try:
      prediction = predict_reburn_risk(fire["id"], return_confidence=True)
      prob = float(prediction.get("reburn_probability", 0.0))
      reburn_percent = int(round(prob * 100))
      reburn_level = prediction.get("risk_level", "Low")
    except Exception as e:
      logger.warning("Error computing reburn risk in analysis-summary for %s: %s", fire["id"], e)

  # If model not available or failed, fall back to frequency-based heuristic
  if reburn_percent == 0:
    freq = historic_count
    if freq >= 3:
      reburn_percent, reburn_level = 70, "High"
    elif freq == 2:
      reburn_percent, reburn_level = 50, "Medium"
    elif freq == 1:
      reburn_percent, reburn_level = 30, "Medium"
    else:
      reburn_percent, reburn_level = 10, "Low"

  return {
    "fireId": fire["id"],
    "fireName": fire["name"],
    "state": fire["state"],
    "region": fire.get("region"),
    "acres": burn_acres_summary["acres"],
    "burn": burn_acres_summary["burn"],
    "reburnRiskPercent": reburn_percent,
    "reburnRiskLevel": reburn_level,
    "historicFireCount": historic_count,
    "generatedAt": datetime.now(timezone.utc).isoformat(),
  }

@app.get("/api/health")
async def health_check():
  return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat(), "reburn_model": REBURN_MODEL_AVAILABLE}

# ==== HTML pages ====

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open(FRONTEND_DIR / "index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/analysis", response_class=HTMLResponse)
async def serve_analysis():
    with open(FRONTEND_DIR / "analysis.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/map", response_class=HTMLResponse)
async def serve_map():
    with open(FRONTEND_DIR / "map.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    with open(FRONTEND_DIR / "login.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/best-next-steps")
def api_best_next_steps(fireId: str = Query(..., alias="fireId")):
    """
    Returns a 1km x 1km grid with recommended 'best next step' per cell
    for the selected fire.
    """
    result = plan_best_next_steps(fireId)
    return result