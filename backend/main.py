from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="TerraNova Demo API", version="0.2.0")

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_methods=["*"],
  allow_headers=["*"],
)


FIRE_CATALOG: List[Dict] = [
  {
    "id": "camp-fire-2018",
    "name": "Camp Fire",
    "state": "CA",
    "lat": 39.73,
    "lng": -121.6,
    "acres": 153_336,
    "start_date": "2018-11-08",
    "cause": "Electrical",
    "summary": "Largest loss of life in CA wildfire history; Paradise community heavily impacted.",
    "perimeter_radius": 25000,
    "region": "Paradise & Magalia",
  },
  {
    "id": "dixie-fire-2021",
    "name": "Dixie Fire",
    "state": "CA",
    "lat": 40.18,
    "lng": -121.23,
    "acres": 963_309,
    "start_date": "2021-07-13",
    "cause": "Powerline",
    "summary": "Second-largest CA wildfire; complex terrain through Plumas and Lassen counties.",
    "perimeter_radius": 36000,
    "region": "Feather River Watershed",
  },
  {
    "id": "bootleg-fire-2021",
    "name": "Bootleg Fire",
    "state": "OR",
    "lat": 42.56,
    "lng": -121.5,
    "acres": 413_765,
    "start_date": "2021-07-06",
    "cause": "Lightning",
    "summary": "Major fire in southern Oregon; threatened critical transmission corridors.",
    "perimeter_radius": 28000,
    "region": "Fremont-Winema NF",
  },
  {
    "id": "maui-fire-2023",
    "name": "Lahaina Wildfire",
    "state": "HI",
    "lat": 20.88,
    "lng": -156.68,
    "acres": 6_700,
    "start_date": "2023-08-08",
    "cause": "Under investigation",
    "summary": "Urban-interface fire on Maui with catastrophic impacts to Lahaina town.",
    "perimeter_radius": 12000,
    "region": "West Maui",
  },
]

FIRE_LOOKUP: Dict[str, Dict] = {fire["id"]: fire for fire in FIRE_CATALOG}

TIMELINE_STAGES = [
  {"value": 0, "label": "Pre-fire baseline", "description": "Vegetation health before ignition", "days_from_ignition": -30},
  {"value": 1, "label": "Active response (Day 0)", "description": "Fire perimeter with live suppression actions", "days_from_ignition": 0},
  {"value": 2, "label": "Initial assessment (Day 7)", "description": "First MTBS-inspired burn severity mapping", "days_from_ignition": 7},
  {"value": 3, "label": "Stabilization phase (Day 30)", "description": "Treatment crews in the field; erosion control active", "days_from_ignition": 30},
  {"value": 4, "label": "Recovery outlook (Year 1)", "description": "Predicted vegetation recovery and infrastructure repairs", "days_from_ignition": 365},
]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
  return max(low, min(high, value))


def pick_fire(fire_id: Optional[str]) -> Dict:
  if fire_id and fire_id in FIRE_LOOKUP:
    return FIRE_LOOKUP[fire_id]
  return FIRE_CATALOG[0]


def parse_priority(value: float | None, fallback: float) -> float:
  if value is None:
    value = fallback
  return clamp(float(value) / 100.0, 0.05, 1.0)


def normalize_priorities(raw: Dict[str, float]) -> Dict[str, float]:
  total = sum(raw.values())
  if total == 0:
    return {k: 1 / len(raw) for k in raw}
  return {k: v / total for k, v in raw.items()}


def jitter_coords(lat: float, lng: float, delta: float = 0.18) -> List[float]:
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
    coords = jitter_coords(base_lat, base_lng, delta=0.25)
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
    "watershedStress": [],
    "erosionRisk": [],
    "infrastructureRisk": [],
  }

  color_map = {
    "burnSeverity": "#ff4e1f",
    "watershedStress": "#33b5ff",
    "erosionRisk": "#d16cff",
    "infrastructureRisk": "#ffd262",
  }

  base_radius = fire["perimeter_radius"]
  center_lat, center_lng = fire["lat"], fire["lng"]

  for layer_key in layers.keys():
    weight = priorities.get({
      "burnSeverity": "community",
      "watershedStress": "watershed",
      "erosionRisk": "watershed",
      "infrastructureRisk": "infrastructure",
    }[layer_key], 0.25)

    for _ in range(2):
      coords = jitter_coords(center_lat, center_lng, delta=0.22)
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
  confidence = round(random.uniform(0.82, 0.97), 2)
  incidents = random.randint(3, 8)
  updated = f"{fire['region']} · Updated {random.randint(15, 80)} mins ago"
  return {
    "confidence": confidence,
    "incidents": incidents,
    "updated": updated,
    "acres": fire["acres"],
  }


@app.get("/api/fires")
async def list_fires(
  state: Optional[str] = Query(None, description="Filter by state code (e.g., CA, OR)"),
  year: Optional[int] = Query(None, description="Filter by year"),
):
  """
  Returns list of fires, optionally filtered by state and year.
  Results are sorted by most recent first.
  """
  filtered_fires = FIRE_CATALOG.copy()
  
  # Apply filters
  if state:
    state_upper = state.upper().strip()
    filtered_fires = [f for f in filtered_fires if f["state"].upper() == state_upper]
  
  if year:
    filtered_fires = [
      f for f in filtered_fires 
      if f["start_date"] and int(f["start_date"].split("-")[0]) == year
    ]
  
  # Sort by year descending (newest first), then by date within same year
  def get_sort_key(fire: Dict) -> tuple:
    date_str = fire.get("start_date", "") or ""
    if date_str:
      try:
        # Extract year, month, day for proper sorting
        parts = date_str.split("-")
        if len(parts) >= 3:
          year = int(parts[0])
          month = int(parts[1])
          day = int(parts[2])
          # Return tuple for sorting: (-year, -month, -day) for descending order
          return (-year, -month, -day)
      except (ValueError, IndexError):
        pass
    return (0, 0, 0)  # Put fires without dates at the end
  
  sorted_fires = sorted(filtered_fires, key=get_sort_key)
  
  return {"fires": sorted_fires}


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
    "insights": insights,
    "mapTip": f"{timeline_meta['label']} · {timeline_meta['description']}",
    "generatedAt": datetime.now(timezone.utc).isoformat(),
  }
  return response


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


@app.get("/api/health")
async def health_check():
  return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

