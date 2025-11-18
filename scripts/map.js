const FALLBACK_SCENARIOS = {
  'home-buyer': {
    role: 'Home buyer',
    roleKey: 'home-buyer',
    center: [39.54, -121.48],
    zoom: 9,
    stats: {
      confidence: 0.92,
      incidents: 7,
      updated: 'Northern Sierra · Last updated 2 hrs ago',
    },
    selectedFireId: 'home-buyer-fire-0',
    layers: {
      burnSeverity: [
        { coords: [39.3, -121.2], radius: 22000, color: '#ff4e1f', intensity: 0.88 },
        { coords: [39.9, -122.2], radius: 18000, color: '#ff9b2f', intensity: 0.64 },
      ],
      floodRisk: [
        { coords: [39.18, -121.6], radius: 20000, color: '#33b5ff', intensity: 0.58 },
      ],
      erosionRisk: [
        { coords: [39.45, -121.05], radius: 15000, color: '#d16cff', intensity: 0.52 },
      ],
      soilStability: [
        { coords: [39.5, -121.3], radius: 24000, color: '#93c47d', intensity: 0.41 },
      ],
    },
    markers: [
      {
        id: 'home-buyer-fire-0',
        coords: [39.54, -121.48],
        title: 'Feather River Canyon',
        details:
          'High burn severity. Prioritize culvert clearing, hydrophobic soil treatment, and wattles along slopes.',
      },
      {
        id: 'home-buyer-fire-1',
        coords: [39.1, -121.4],
        title: 'Mosquito Ridge',
        details: 'Roadside slopes losing cohesion. Deploy wattles and monitor slope stability.',
      },
    ],
    priorities: [
      { label: 'Rebuild risk protection', score: 86 },
      { label: 'Flood risk protection', score: 58 },
      { label: 'Habitat stability', score: 42 },
      { label: 'Infrastructure', score: 70 },
    ],
    insights: [
      {
        category: 'Action',
        title: 'Deploy wattles on Mosquito Ridge Rd.',
        detail: 'High debris risk · due 12 hrs',
      },
      {
        category: 'Monitoring',
        title: 'Stream gauges synced · 4 anomalies',
        detail: 'Sent to hydrology team',
      },
      {
        category: 'Community',
        title: 'Town hall briefing ready',
        detail: 'Shareable guest link active',
      },
    ],
    mapTip:
      'Tap a marker to view burn intensity, debris flow likelihood, and suggested restoration actions.',
  },
  'land-manager': {
    role: 'Land manager',
    roleKey: 'land-manager',
    center: [38.95, -120.11],
    zoom: 9,
    stats: {
      confidence: 0.9,
      incidents: 6,
      updated: 'South Lake Tahoe Rim · Updated 1 hr ago',
    },
    selectedFireId: 'land-manager-fire-0',
    layers: {
      burnSeverity: [
        { coords: [38.9, -120.3], radius: 20000, color: '#ff4e1f', intensity: 0.7 },
      ],
      floodRisk: [
        { coords: [38.85, -120.15], radius: 24000, color: '#33b5ff', intensity: 0.55 },
      ],
      erosionRisk: [
        { coords: [38.78, -120.05], radius: 15000, color: '#d16cff', intensity: 0.62 },
      ],
      soilStability: [
        { coords: [38.96, -120.05], radius: 21000, color: '#93c47d', intensity: 0.46 },
      ],
    },
    markers: [
      {
        id: 'land-manager-fire-0',
        coords: [38.95, -120.11],
        title: 'South Lake Tahoe Rim',
        details:
          'Moderate burn zone. Focus on debris flow barriers and reseeding native grasses before winter storms.',
      },
      {
        id: 'land-manager-fire-1',
        coords: [38.82, -120.04],
        title: 'Echo Summit',
        details: 'Granite faces shedding rockfall when saturated. Stage mesh netting.',
      },
    ],
    priorities: [
      { label: 'Habitat stability', score: 82 },
      { label: 'Flood risk protection', score: 68 },
      { label: 'Rebuild risk protection', score: 63 },
      { label: 'Infrastructure', score: 57 },
    ],
    insights: [
      {
        category: 'Action',
        title: 'Stage mulching crews near Fallen Leaf Lake',
        detail: 'Scarp erosion accelerating',
      },
      {
        category: 'Monitoring',
        title: 'Drone pass confirmed regrowth plots',
        detail: 'NDVI improving +6%',
      },
      {
        category: 'Community',
        title: 'Brief tribal partners on reseeding plan',
        detail: 'Meeting scheduled tomorrow 08:00 PST',
      },
    ],
    mapTip: 'Tap a marker to learn reseeding status and slope stability guidance.',
  },
  'county-planner': {
    role: 'County planner',
    roleKey: 'county-planner',
    center: [40.38, -122.15],
    zoom: 8,
    stats: {
      confidence: 0.93,
      incidents: 8,
      updated: 'Shasta foothills · Updated 45 mins ago',
    },
    selectedFireId: 'county-planner-fire-0',
    layers: {
      burnSeverity: [
        { coords: [40.2, -122.3], radius: 26000, color: '#ff4e1f', intensity: 0.8 },
      ],
      floodRisk: [
        { coords: [40.4, -122.0], radius: 28000, color: '#33b5ff', intensity: 0.67 },
        { coords: [40.55, -122.45], radius: 20000, color: '#1f7bdc', intensity: 0.52 },
      ],
      erosionRisk: [
        { coords: [40.1, -121.8], radius: 21000, color: '#d16cff', intensity: 0.49 },
      ],
      soilStability: [
        { coords: [40.45, -122.25], radius: 25000, color: '#93c47d', intensity: 0.45 },
      ],
    },
    markers: [
      {
        id: 'county-planner-fire-0',
        coords: [40.38, -122.15],
        title: 'Shasta foothills',
        details:
          'Critical habitat overlap. Coordinate BAER crews with CAL FIRE to stabilize ridgelines.',
      },
      {
        id: 'county-planner-fire-1',
        coords: [40.7, -122.9],
        title: 'Trinity Corridor',
        details: 'Debris basins at 68% capacity. Plan mechanical clearing.',
      },
    ],
    priorities: [
      { label: 'Infrastructure', score: 78 },
      { label: 'Flood risk protection', score: 74 },
      { label: 'Rebuild risk protection', score: 66 },
      { label: 'Habitat stability', score: 55 },
    ],
    insights: [
      {
        category: 'Action',
        title: 'Fast-track culvert permits in Happy Valley',
        detail: 'Permit queue trimmed to 4 hrs',
      },
      {
        category: 'Monitoring',
        title: 'Telemetry: 7 pump stations at alert',
        detail: 'Dispatch crews before 22:00',
      },
      {
        category: 'Community',
        title: 'County briefing deck synced to portal',
        detail: 'Share with Board of Sups',
      },
    ],
    mapTip: 'Tap a county to inspect infrastructure readiness and evacuation triggers.',
  },
};

const inferApiBase = () => {
  const { protocol, hostname, port } = window.location;
  if (hostname && hostname !== 'file') {
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      const guessedPort = port === '8000' ? '8001' : port || '8001';
      return `${protocol}//${hostname}:${guessedPort}`;
    }
    return `${protocol}//${hostname}${port ? `:${port}` : ''}`;
  }
  return 'http://localhost:8001';
};

const API_BASE_URL = window.TERRANOVA_API_BASE || inferApiBase();
const state = {
  role: 'home-buyer',
  horizon: 3,
  fireId: null,
};

const map = L.map('map', {
  zoomControl: false,
}).setView([39.3, -120.9], 7);

let baseLayer;
if (window.L?.esri?.basemapLayer) {
  baseLayer = L.esri.basemapLayer('Topographic').addTo(map);
} else {
  baseLayer = L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
  }).addTo(map);
}

const featureLayerGroups = {
  burnSeverity: L.layerGroup(),
  floodRisk: L.layerGroup(),
  erosionRisk: L.layerGroup(),
  soilStability: L.layerGroup(),
};

const markersLayer = L.layerGroup().addTo(map);

Object.keys(featureLayerGroups).forEach((key) => {
  featureLayerGroups[key].addTo(map);
});

L.control.zoom({ position: 'bottomright' }).addTo(map);

const chips = document.querySelectorAll('.chip');
const slider = document.querySelector('.slider input');
const sliderValue = document.querySelector('[data-slider-value]');
const priorityContainer = document.querySelector('[data-priorities]');
const insightContainer = document.querySelector('[data-insights]');
const mapTipText = document.querySelector('[data-map-tip]');
const locationText = document.querySelector('[data-location]');
const confidenceText = document.querySelector('[data-confidence]');
const incidentsText = document.querySelector('[data-incidents]');
const layerToggles = document.querySelectorAll('.layer input[data-layer]');

const setChipActive = (roleKey) => {
  chips.forEach((chip) => {
    const isActive = chip.dataset.role === roleKey;
    chip.classList.toggle('active', isActive);
  });
};

const updateSliderValue = () => {
  if (sliderValue && slider) {
    sliderValue.textContent = `${slider.value} yrs`;
  }
};

const formatScore = (value) => `${value}%`;

const renderPriorities = (priorities = []) => {
  if (!priorityContainer) return;
  if (!priorities.length) {
    priorityContainer.innerHTML = '<p class="muted small">No priorities available.</p>';
    return;
  }
  priorityContainer.innerHTML = priorities
    .map(
      (priority) => `
      <div class="priority">
        <p>${priority.label}</p>
        <div class="progress"><span style="width: ${priority.score}%"></span></div>
        <span class="score">${formatScore(priority.score)}</span>
      </div>
    `,
    )
    .join('');
};

const renderInsights = (insights = []) => {
  if (!insightContainer) return;
  if (!insights.length) {
    insightContainer.innerHTML = `
      <article>
        <p class="rail-label">No insights</p>
        <strong>All clear for now.</strong>
        <span>Refresh the scenario to pull new actions.</span>
      </article>
    `;
    return;
  }
  insightContainer.innerHTML = insights
    .map(
      (insight) => `
        <article>
          <p class="rail-label">${insight.category}</p>
          <strong>${insight.title}</strong>
          <span>${insight.detail}</span>
        </article>
      `,
    )
    .join('');
};

const renderMarkers = (markers = []) => {
  markersLayer.clearLayers();
  markers.forEach((marker) => {
    if (!marker?.coords) return;
    const isSelected = marker.id && marker.id === state.fireId;
    const leafletMarker = L.marker(marker.coords, {
      riseOnHover: true,
      opacity: isSelected ? 1 : 0.85,
    });

    leafletMarker
      .addTo(markersLayer)
      .bindPopup(
        `<strong>${marker.title || 'Field marker'}</strong><p>${marker.details || ''}</p>${
          marker.id ? '<p class="muted small">Click marker to focus this fire.</p>' : ''
        }`,
      );

    if (marker.id) {
      leafletMarker.on('click', () => {
        state.fireId = marker.id;
        loadScenario(state.role, state.horizon, marker.id);
      });
    }
  });
};

const renderLayerGroup = (layerKey, features = []) => {
  const group = featureLayerGroups[layerKey];
  if (!group) return;
  group.clearLayers();
  features.forEach((feature) => {
    if (!feature?.coords) return;
    L.circle(feature.coords, {
      radius: feature.radius || 15000,
      color: feature.color || '#ff9b2f',
      fillColor: feature.color || '#ff9b2f',
      fillOpacity: 0.15 + (feature.intensity || 0) * 0.3,
      weight: 1.2,
    }).addTo(group);
  });
};

const syncLayerVisibility = () => {
  layerToggles.forEach((toggle) => {
    const key = toggle.dataset.layer;
    const group = featureLayerGroups[key];
    if (!group) return;
    if (toggle.checked) {
      map.addLayer(group);
    } else {
      map.removeLayer(group);
    }
  });
};

const flashMapTip = (message) => {
  if (!mapTipText) return;
  const defaultText =
    'Tap a marker to view burn intensity, debris flow likelihood, and suggested restoration actions.';
  mapTipText.textContent = message;
  setTimeout(() => {
    mapTipText.textContent = defaultText;
  }, 2800);
};

const renderLayers = (layers = {}) => {
  Object.entries(featureLayerGroups).forEach(([key]) => {
    renderLayerGroup(key, layers[key] || []);
  });
  syncLayerVisibility();
};

const updateStats = (stats = {}) => {
  if (confidenceText && typeof stats.confidence === 'number') {
    confidenceText.textContent = `${Math.round(stats.confidence * 100)}%`;
  }
  if (incidentsText && typeof stats.incidents === 'number') {
    incidentsText.textContent = `${stats.incidents} alerts`;
  }
  if (locationText && stats.updated) {
    locationText.textContent = stats.updated;
  }
};

const mergeWithFallback = (payload) => {
  const fallback = FALLBACK_SCENARIOS[payload?.roleKey || state.role] || FALLBACK_SCENARIOS['home-buyer'];
  return {
    ...fallback,
    ...payload,
    stats: { ...fallback.stats, ...(payload?.stats || {}) },
    layers: { ...fallback.layers, ...(payload?.layers || {}) },
    markers: payload?.markers?.length ? payload.markers : fallback.markers,
    priorities: payload?.priorities?.length ? payload.priorities : fallback.priorities,
    insights: payload?.insights?.length ? payload.insights : fallback.insights,
    selectedFireId: payload?.selectedFireId || fallback.selectedFireId,
  };
};

const renderScenario = (scenario) => {
  const { center, zoom, markers, layers, priorities, insights, stats, mapTip, roleKey, selectedFireId } = scenario;
  if (Array.isArray(center) && typeof zoom === 'number') {
    map.flyTo(center, zoom, { duration: 1 });
  }
  if (mapTipText && mapTip) {
    mapTipText.textContent = mapTip;
  }
  if (selectedFireId) {
    state.fireId = selectedFireId;
  }
  renderMarkers(markers);
  renderLayers(layers);
  renderPriorities(priorities);
  renderInsights(insights);
  updateStats(stats);
  setChipActive(roleKey || state.role);
};

const fetchScenario = async (roleKey, horizon, fireId) => {
  const params = new URLSearchParams({
    role: roleKey,
    horizon: String(horizon),
  });
  if (fireId) params.append('fireId', fireId);
  const url = `${API_BASE_URL}/api/scenario?${params.toString()}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error('Failed to fetch scenario');
    const data = await response.json();
    return data;
  } catch (error) {
    console.warn('Falling back to static scenario', error);
    return FALLBACK_SCENARIOS[roleKey] || FALLBACK_SCENARIOS['home-buyer'];
  } finally {
    clearTimeout(timeout);
  }
};

const loadScenario = async (roleKey = state.role, horizon = state.horizon, fireId = state.fireId) => {
  state.role = roleKey;
  state.horizon = horizon;
  if (slider) {
    slider.value = horizon;
    updateSliderValue();
  }
  const payload = await fetchScenario(roleKey, horizon, fireId);
  const scenario = mergeWithFallback(payload);
  renderScenario(scenario);
};

if (slider) {
  slider.addEventListener('input', (event) => {
    const value = Number(event.target.value);
    updateSliderValue();
  });
  slider.addEventListener('change', (event) => {
    const value = Number(event.target.value);
    loadScenario(state.role, value, state.fireId);
  });
  updateSliderValue();
}

chips.forEach((chip) => {
  chip.addEventListener('click', () => {
    const roleKey = chip.dataset.role || 'home-buyer';
    setChipActive(roleKey);
    // When switching personas, let the backend pick a sensible default fire.
    state.fireId = null;
    loadScenario(roleKey, state.horizon, state.fireId);
  });
});

layerToggles.forEach((toggle) => {
  toggle.addEventListener('change', () => {
    syncLayerVisibility();
    const label = toggle.nextElementSibling?.textContent?.trim() || 'Layer';
    const stateText = toggle.checked ? 'enabled' : 'disabled';
    flashMapTip(`${label} layer ${stateText}. Tap the map to inspect updates.`);
  });
});

loadScenario();
