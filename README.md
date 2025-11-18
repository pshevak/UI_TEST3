## TerraNova Demo Pipeline

This repository now includes an end-to-end demo loop that feeds the TerraNova UI with synthetic-yet-believable geospatial intelligence so you can show the experience without tying into production data.

### Architecture at a Glance

- **Frontend (existing)**: Static HTML/CSS under the repo root (`index.html`, `map.html`, etc.) powered by Leaflet for map rendering.
- **Demo API (new)**: `backend/main.py` (FastAPI) synthesizes scenario data per persona every time a request hits `/api/scenario`.
- **Data model**: Each persona (home buyer, land manager, county planner) has base seeds for markers, layer clusters, and insight templates. Every API request adds jitter to coordinates, scores, and messaging so it looks “live”.

### Prerequisites

- Python 3.11+ (macOS ships with 3.12/3.13—works fine)
- Node is **not** required unless you prefer `npx http-server` for static hosting
- Recommended: two terminals—one for the API, one for the static site

### Setup Steps

```bash
cd /Users/swara/Documents/UI_TEST3
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

The `.venv` folder is already gitignored. Reactivate it for every new shell: `source .venv/bin/activate`.

### Running the Demo

| Terminal | Command | Purpose |
| --- | --- | --- |
| #1 (backend) | `source .venv/bin/activate && uvicorn backend.main:app --port 8001 --reload` | Starts the FastAPI demo API with hot reload |
| #2 (frontend) | `python3 -m http.server 8000` | Serves the static UI (`map.html`, etc.) |

Then open `http://localhost:8000/map.html`. The front-end automatically calls `http://localhost:8001/api/scenario`. If you need a different backend URL, set `window.TERRANOVA_API_BASE` before `scripts/map.js` loads (see `map.html` for the script tag order).

### What the API Returns

`GET /api/scenario?role=home-buyer&horizon=3`

```jsonc
{
  "role": "Home buyer",
  "center": [39.54, -121.48],
  "markers": [
    { "title": "Feather River Canyon", "details": "...", "coords": [39.52, -121.48] }
  ],
  "layers": {
    "burnSeverity": [{ "coords": [39.26, -121.02], "radius": 23687, "color": "#ff4e1f" }],
    "floodRisk": [ ... ],
    "erosionRisk": [ ... ],
    "soilStability": [ ... ]
  },
  "priorities": [{ "label": "Rebuild risk protection", "score": 92 }, ...],
  "insights": [{ "category": "Action", "title": "...", "detail": "..." }],
  "stats": { "confidence": 0.92, "incidents": 6, "updated": "Feather River Canyon · Updated 105 mins ago" }
}
```

Every response uses persona-specific seeds plus random jitter, so the map, scores, and rail content subtly change each time—perfect for a “live” briefing.

### Frontend Wiring

- `map.html` exposes data hooks via `data-*` attributes (chips, priorities container, insights rail, stats).
- `scripts/map.js`:
  - Infers the API base URL (defaults to `http://localhost:8001`) and falls back to bundled static data if the API is unreachable.
  - Fetches scenarios on load, persona chip clicks, and planning horizon changes.
  - Renders Leaflet layers per toggle (burn, flood, erosion, soils) and keeps popups/markers synced.

### Customizing the Demo

- **Add personas**: extend `ROLE_PROFILES` in `backend/main.py`; chips automatically pick up new roles if you add corresponding buttons in `map.html`.
- **Change regions**: adjust the seed coordinates/radii in `ROLE_PROFILES[role]["layer_seeds"]`.
- **Adjust messaging**: tweak insight templates or priority weights per persona—changes show instantly thanks to `--reload`.
- **Swap basemaps**: `scripts/map.js` still prefers Esri’s `Topographic` layer but falls back to HOT OSM tiles if the Esri script is unavailable.

### Regenerating / Extending Data

For now the “pipeline” lives inside the FastAPI service (each request synthesizes fresh data). If you’d like an offline generator—for example, to persist a JSON snapshot for QA—drop a script in `backend/data/` and load it in `main.py` before applying jitter.

### Troubleshooting

- **CORS errors**: confirm the API runs on 8001 and that you’re accessing the UI via `http://localhost:8000` (not `file://`). FastAPI is configured with permissive CORS for demo purposes.
- **API unreachable**: the UI will log a warning and fall back to the static scenarios defined in `scripts/map.js`. Start the backend to restore live data.
- **Virtualenv issues**: delete `.venv/` and rerun the setup commands above.

Let me know if you want the backend to also serve the static files (so you only run one command) or if you’d like an automated data refresh script.

