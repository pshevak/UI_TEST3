from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="TerraNova Demo API", version="0.1.0")

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_methods=["*"],
  allow_headers=["*"],
)


ROLE_PROFILES: Dict[str, Dict] = {
  "home-buyer": {
    "label": "Home buyer",
    "location": "Feather River Canyon",
    "center": [39.54, -121.48],
    "zoom": 9,
    "chip_center": [39.54, -121.48],
    "markers": [
      {
        "title": "Feather River Canyon",
        "details": "High burn severity. Prioritize culvert clearing and hydrophobic soil treatment.",
        "coords": [39.54, -121.48],
      },
      {
        "title": "Mosquito Ridge",
        "details": "Roadside slopes losing cohesion. Deploy wattles and monitor slope stability.",
        "coords": [39.26, -120.97],
      },
    ],
    "layer_seeds": {
      "burnSeverity": [
        {"coords": [39.3, -121.2], "radius": 22000, "color": "#ff4e1f"},
        {"coords": [39.6, -121.0], "radius": 15000, "color": "#ff9b2f"},
      ],
      "floodRisk": [
        {"coords": [39.1, -121.4], "radius": 26000, "color": "#33b5ff"},
        {"coords": [39.55, -121.65], "radius": 18000, "color": "#1f7bdc"},
      ],
      "erosionRisk": [
        {"coords": [39.4, -120.9], "radius": 19000, "color": "#d16cff"},
      ],
      "soilStability": [
        {"coords": [39.5, -121.2], "radius": 24000, "color": "#93c47d"},
      ],
    },
    "priority_weights": {
      "Rebuild risk protection": 0.95,
      "Flood risk protection": 0.75,
      "Habitat stability": 0.45,
      "Infrastructure": 0.65,
    },
    "insight_pool": [
      ("Action", "Deploy wattles on Mosquito Ridge Rd.", "High debris risk · due 12 hrs"),
      ("Monitoring", "Stream gauges synced · 4 anomalies", "Sent to hydrology team"),
      ("Community", "Town hall briefing ready", "Shareable guest link active"),
      ("Action", "Inspect culverts near Yankee Jims Rd.", "Post-storm inspection route drafted"),
    ],
  },
  "land-manager": {
    "label": "Land manager",
    "location": "South Lake Tahoe Rim",
    "center": [38.95, -120.11],
    "zoom": 9,
    "chip_center": [38.95, -120.11],
    "markers": [
      {
        "title": "South Lake Tahoe Rim",
        "details": "Moderate burn zone. Focus on debris flow barriers and reseeding native grasses.",
        "coords": [38.95, -120.11],
      },
      {
        "title": "Echo Summit",
        "details": "Granite faces shedding rockfall when saturated. Stage mesh netting.",
        "coords": [38.82, -120.04],
      },
    ],
    "layer_seeds": {
      "burnSeverity": [
        {"coords": [38.9, -120.3], "radius": 20000, "color": "#ff4e1f"},
        {"coords": [39.05, -119.9], "radius": 14000, "color": "#ff9b2f"},
      ],
      "floodRisk": [
        {"coords": [38.85, -120.15], "radius": 24000, "color": "#33b5ff"},
      ],
      "erosionRisk": [
        {"coords": [38.78, -120.05], "radius": 15000, "color": "#d16cff"},
        {"coords": [38.93, -120.22], "radius": 13000, "color": "#d16cff"},
      ],
      "soilStability": [
        {"coords": [38.96, -120.05], "radius": 21000, "color": "#93c47d"},
      ],
    },
    "priority_weights": {
      "Rebuild risk protection": 0.65,
      "Flood risk protection": 0.7,
      "Habitat stability": 0.9,
      "Infrastructure": 0.6,
    },
    "insight_pool": [
      ("Action", "Stage mulching crews near Fallen Leaf Lake", "Scarp erosion accelerating"),
      ("Monitoring", "Drone pass confirmed regrowth plots", "NDVI improving +6%"),
      ("Community", "Brief tribal partners on reseeding plan", "Meeting scheduled 08:00 PST"),
      ("Action", "Coordinate BAER crews with CAL FIRE", "Stabilize ridgelines before storm"),
    ],
  },
  "county-planner": {
    "label": "County planner",
    "location": "Shasta foothills",
    "center": [40.38, -122.15],
    "zoom": 8,
    "chip_center": [40.38, -122.15],
    "markers": [
      {
        "title": "Shasta foothills",
        "details": "Critical habitat overlap. Align BAER crews with CAL FIRE task force.",
        "coords": [40.38, -122.15],
      },
      {
        "title": "Trinity Corridor",
        "details": "Debris basins at 68% capacity. Plan mechanical clearing.",
        "coords": [40.7, -122.9],
      },
    ],
    "layer_seeds": {
      "burnSeverity": [
        {"coords": [40.2, -122.3], "radius": 26000, "color": "#ff4e1f"},
      ],
      "floodRisk": [
        {"coords": [40.4, -122.0], "radius": 28000, "color": "#33b5ff"},
        {"coords": [40.55, -122.45], "radius": 20000, "color": "#1f7bdc"},
      ],
      "erosionRisk": [
        {"coords": [40.1, -121.8], "radius": 21000, "color": "#d16cff"},
      ],
      "soilStability": [
        {"coords": [40.45, -122.25], "radius": 25000, "color": "#93c47d"},
      ],
    },
    "priority_weights": {
      "Rebuild risk protection": 0.7,
      "Flood risk protection": 0.8,
      "Habitat stability": 0.6,
      "Infrastructure": 0.9,
    },
    "insight_pool": [
      ("Action", "Fast-track culvert permits in Happy Valley", "Permit queue trimmed to 4 hrs"),
      ("Monitoring", "Telemetry: 7 pump stations at alert", "Dispatch crews before 22:00"),
      ("Community", "County briefing deck synced to portal", "Share with Board of Sups"),
      ("Action", "Update evacuation trigger zones", "Model shift accounts for debris flow"),
    ],
  },
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
  return max(low, min(high, value))


def random_pct(base: float, variance: float = 0.08) -> float:
  return clamp(base + random.uniform(-variance, variance))


def generate_priorities(role_key: str, horizon: int) -> List[Dict]:
  weights = ROLE_PROFILES[role_key]["priority_weights"]
  priorities = []
  horizon_factor = (horizon - 3) / 14  # subtle adjustment
  for label, weight in weights.items():
    base = random_pct(weight, 0.07)
    adjusted = clamp(base + horizon_factor * (0.5 - weight))
    priorities.append({
      "label": label,
      "score": round(adjusted * 100),
    })
  priorities.sort(key=lambda item: item["score"], reverse=True)
  return priorities


def jitter_coords(lat: float, lng: float, delta: float = 0.12) -> List[float]:
  return [
    round(lat + random.uniform(-delta, delta), 4),
    round(lng + random.uniform(-delta, delta), 4),
  ]


def generate_markers(role_key: str) -> List[Dict]:
  """Return jittered fire markers for a role, each with a stable fireId."""
  markers: List[Dict] = []
  for idx, marker in enumerate(ROLE_PROFILES[role_key]["markers"]):
    coords = jitter_coords(marker["coords"][0], marker["coords"][1], delta=0.06)
    details = marker["details"]
    if random.random() < 0.4:
      details += " Incoming storm cell raises priority."
    fire_id = f"{role_key}-fire-{idx}"
    markers.append({
      "id": fire_id,
      "title": marker["title"],
      "details": details,
      "coords": coords,
    })
  return markers


def generate_layers(role_key: str, horizon: int, fire_coords: List[float] | None = None) -> Dict[str, List[Dict]]:
  """
  Generate synthetic layer clusters for the map.

  - fire_coords: when provided, clusters are biased around the selected fire.
  - horizon: nudges radius/intensity to simulate predicted change over years.
  """
  layer_payload: Dict[str, List[Dict]] = {}
  horizon_factor = clamp(horizon / 10.0, 0.1, 1.0)  # 1–10 yrs → 0.1–1.0

  for layer_key, features in ROLE_PROFILES[role_key]["layer_seeds"].items():
    layer_payload[layer_key] = []
    for feat in features:
      base_lat, base_lng = feat["coords"]

      if fire_coords:
        # Blend original seed with fire center so clusters follow the selected fire.
        base_lat = (base_lat + fire_coords[0]) / 2.0
        base_lng = (base_lng + fire_coords[1]) / 2.0

      coords = jitter_coords(base_lat, base_lng, delta=0.18)

      # Horizon stretches footprint slightly and decays intensity to mimic recovery.
      radius_scale = 0.85 + horizon_factor * 0.4  # ~0.9x at 1 yr → ~1.25x at 10 yrs
      radius = int(feat["radius"] * radius_scale * random.uniform(0.9, 1.15))

      base_intensity = random.uniform(0.55, 0.98)
      recovery_rate = 0.4  # how fast severity eases with horizon
      intensity = clamp(base_intensity * (1.0 - recovery_rate * (horizon_factor - 0.1)))

      layer_payload[layer_key].append({
        "coords": coords,
        "radius": radius,
        "color": feat["color"],
        "intensity": round(intensity, 2),
      })

  return layer_payload


def generate_insights(role_key: str) -> List[Dict]:
  pool = ROLE_PROFILES[role_key]["insight_pool"]
  picks = random.sample(pool, k=min(3, len(pool)))
  insights = []
  for insight_type, title, detail in picks:
    if "due" in detail and random.random() < 0.5:
      hours = random.randint(6, 18)
      detail = f"Due in {hours} hrs · auto-routed"
    insights.append({
      "category": insight_type,
      "title": title,
      "detail": detail,
    })
  return insights


def format_update_message(location: str) -> str:
  minutes = random.randint(30, 120)
  return f"{location} · Updated {minutes} mins ago"


@app.get("/api/scenario")
async def get_scenario(
  role: str = Query("home-buyer"),
  horizon: int = Query(3, ge=1, le=10),
  fireId: str | None = Query(None, description="Optional fire identifier to focus the optimization around"),
):
  role_key = role.lower().replace(" ", "-")
  if role_key not in ROLE_PROFILES:
    role_key = "home-buyer"

  profile = ROLE_PROFILES[role_key]
  priorities = generate_priorities(role_key, horizon)
  markers = generate_markers(role_key)
  selected_fire_id = fireId
  fire_coords = None

  if not selected_fire_id and markers:
    selected_fire_id = markers[0]["id"]

  if selected_fire_id:
    for marker in markers:
      if marker["id"] == selected_fire_id:
        fire_coords = marker["coords"]
        break

  layers = generate_layers(role_key, horizon, fire_coords)
  insights = generate_insights(role_key)

  confidence = round(random.uniform(0.85, 0.97), 2)
  incidents = random.randint(5, 9)

  response = {
    "role": profile["label"],
    "roleKey": role_key,
    "selectedFireId": selected_fire_id,
    "center": profile["center"],
    "zoom": profile["zoom"],
    "chipCenter": profile["chip_center"],
    "stats": {
      "confidence": confidence,
      "incidents": incidents,
      "updated": format_update_message(profile["location"]),
    },
    "markers": markers,
    "layers": layers,
    "priorities": priorities,
    "insights": insights,
    "mapTip": "Tap a marker to inspect burn intensity, debris flow likelihood, and recommended actions.",
    "generatedAt": datetime.now(timezone.utc).isoformat(),
  }
  return response


@app.get("/api/health")
async def health_check():
  return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

