const FALLBACK_FIRES = [
  {
    id: 'camp-fire-2018',
    name: 'Camp Fire',
    state: 'CA',
    lat: 39.73,
    lng: -121.6,
    acres: 153336,
    year: 2018,
    region: 'Paradise & Magalia',
  },
  {
    id: 'dixie-fire-2021',
    name: 'Dixie Fire',
    state: 'CA',
    lat: 40.18,
    lng: -121.23,
    acres: 963309,
    year: 2021,
    region: 'Feather River Watershed',
  },
  {
    id: 'bootleg-fire-2021',
    name: 'Bootleg Fire',
    state: 'OR',
    lat: 42.56,
    lng: -121.5,
    acres: 413765,
    year: 2021,
    region: 'Fremont-Winema NF',
  },
  {
    id: 'maui-fire-2023',
    name: 'Lahaina Wildfire',
    state: 'HI',
    lat: 20.88,
    lng: -156.68,
    acres: 6700,
    year: 2023,
    region: 'West Maui',
  },
];

const TIMELINE_STAGES = [
  { value: 0, label: 'Pre-fire baseline', description: 'Vegetation health before ignition' },
  { value: 1, label: 'Active response (Day 0)', description: 'Fire perimeter with live suppression actions' },
  { value: 2, label: 'Initial assessment (Day 7)', description: 'First MTBS-inspired burn severity mapping' },
  { value: 3, label: 'Stabilization phase (Day 30)', description: 'Treatment crews in the field; erosion control active' },
  { value: 4, label: 'Recovery outlook (Year 1)', description: 'Predicted vegetation recovery and infrastructure repairs' },
];

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

const DEFAULT_PRIORITIES = {
  community: 70,
  watershed: 55,
  infrastructure: 60,
};

const state = {
  fireId: FALLBACK_FIRES[0].id,
  timeline: 2,
  priorities: { ...DEFAULT_PRIORITIES },
  selectedSuggestionIndex: -1,
  selectedState: null,
  selectedYear: null,
  selectedMonth: null,
};

// Initialize year dropdown (1994-2025)
const initializeYearDropdown = () => {
  if (!els.yearSelect) return;
  
  for (let year = 2025; year >= 1994; year--) {
    const option = document.createElement('option');
    option.value = year.toString();
    option.textContent = year.toString();
    els.yearSelect.appendChild(option);
  }
};

// US States data for autocomplete (frontend only)
const US_STATES = [
  { code: 'AL', name: 'Alabama' }, { code: 'AK', name: 'Alaska' },
  { code: 'AZ', name: 'Arizona' }, { code: 'AR', name: 'Arkansas' },
  { code: 'CA', name: 'California' }, { code: 'CO', name: 'Colorado' },
  { code: 'CT', name: 'Connecticut' }, { code: 'DE', name: 'Delaware' },
  { code: 'FL', name: 'Florida' }, { code: 'GA', name: 'Georgia' },
  { code: 'HI', name: 'Hawaii' }, { code: 'ID', name: 'Idaho' },
  { code: 'IL', name: 'Illinois' }, { code: 'IN', name: 'Indiana' },
  { code: 'IA', name: 'Iowa' }, { code: 'KS', name: 'Kansas' },
  { code: 'KY', name: 'Kentucky' }, { code: 'LA', name: 'Louisiana' },
  { code: 'ME', name: 'Maine' }, { code: 'MD', name: 'Maryland' },
  { code: 'MA', name: 'Massachusetts' }, { code: 'MI', name: 'Michigan' },
  { code: 'MN', name: 'Minnesota' }, { code: 'MS', name: 'Mississippi' },
  { code: 'MO', name: 'Missouri' }, { code: 'MT', name: 'Montana' },
  { code: 'NE', name: 'Nebraska' }, { code: 'NV', name: 'Nevada' },
  { code: 'NH', name: 'New Hampshire' }, { code: 'NJ', name: 'New Jersey' },
  { code: 'NM', name: 'New Mexico' }, { code: 'NY', name: 'New York' },
  { code: 'NC', name: 'North Carolina' }, { code: 'ND', name: 'North Dakota' },
  { code: 'OH', name: 'Ohio' }, { code: 'OK', name: 'Oklahoma' },
  { code: 'OR', name: 'Oregon' }, { code: 'PA', name: 'Pennsylvania' },
  { code: 'RI', name: 'Rhode Island' }, { code: 'SC', name: 'South Carolina' },
  { code: 'SD', name: 'South Dakota' }, { code: 'TN', name: 'Tennessee' },
  { code: 'TX', name: 'Texas' }, { code: 'UT', name: 'Utah' },
  { code: 'VT', name: 'Vermont' }, { code: 'VA', name: 'Virginia' },
  { code: 'WA', name: 'Washington' }, { code: 'WV', name: 'West Virginia' },
  { code: 'WI', name: 'Wisconsin' }, { code: 'WY', name: 'Wyoming' },
];

let fireCatalog = [...FALLBACK_FIRES];

const map = L.map('map', { zoomControl: false }).setView([FALLBACK_FIRES[0].lat, FALLBACK_FIRES[0].lng], 8);

if (window.L?.esri?.basemapLayer) {
  L.esri.basemapLayer('Topographic').addTo(map);
} else {
  L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
  }).addTo(map);
}

const featureLayerGroups = {
  burnSeverity: L.layerGroup().addTo(map),
  watershedStress: L.layerGroup().addTo(map),
  erosionRisk: L.layerGroup().addTo(map),
  infrastructureRisk: L.layerGroup().addTo(map),
};

const firePinsLayer = L.layerGroup().addTo(map);
const hotspotLayer = L.layerGroup().addTo(map);

L.control.zoom({ position: 'bottomright' }).addTo(map);

const els = {
  fireList: document.querySelector('[data-fire-list]'),
  fireTitle: document.querySelector('[data-fire-title]'),
  fireMeta: document.querySelector('[data-fire-meta]'),
  mapHeadline: document.querySelector('[data-map-headline]'),
  mapSubhead: document.querySelector('[data-map-subhead]'),
  priorityContainer: document.querySelector('[data-priorities]'),
  insightContainer: document.querySelector('[data-insights]'),
  nextSteps: document.querySelector('[data-next-steps]'),
  mapTip: document.querySelector('[data-map-tip]'),
  confidence: document.querySelector('[data-confidence]'),
  incidents: document.querySelector('[data-incidents]'),
  forecastLabel: document.querySelector('[data-forecast-label]'),
  forecastDesc: document.querySelector('[data-forecast-desc]'),
  forecastSlider: document.querySelector('[data-forecast-slider]'),
  priorityValues: {
    community: document.querySelector('[data-priority-value="community"]'),
    watershed: document.querySelector('[data-priority-value="watershed"]'),
    infrastructure: document.querySelector('[data-priority-value="infrastructure"]'),
  },
  prioritySliders: document.querySelectorAll('[data-priority-slider]'),
  layerToggles: document.querySelectorAll('.layer input[data-layer]'),
  searchInput: document.querySelector('[data-search-input]'),
  autocompleteSuggestions: document.querySelector('[data-autocomplete-suggestions]'),
  yearSelect: document.querySelector('[data-year-select]'),
  monthSelect: document.querySelector('[data-month-select]'),
  searchBtn: document.querySelector('[data-search-btn]'),
};

const debounce = (fn, delay = 350) => {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
};

const formatNumber = (value) => value.toLocaleString();

const setPriorityDisplays = () => {
  Object.entries(state.priorities).forEach(([key, value]) => {
    const target = els.priorityValues[key];
    if (target) target.textContent = `${value}%`;
  });
};

const updateForecastLabels = () => {
  if (!els.forecastSlider) return;
  const stage = TIMELINE_STAGES[state.timeline] || TIMELINE_STAGES[2];
  if (els.forecastLabel) {
    els.forecastLabel.textContent = stage.label;
  }
  if (els.forecastDesc) {
    els.forecastDesc.textContent = stage.description;
  }
  if (els.mapSubhead) {
    els.mapSubhead.textContent = stage.label;
  }
};

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const jitter = (value, delta) => value + (Math.random() * 2 - 1) * delta;

const renderFireList = (fires) => {
  if (!els.fireList) return;
  els.fireList.innerHTML = fires
    .map(
      (fire) => `
      <button class="fire-card ${fire.id === state.fireId ? 'active' : ''}" title="Focus on ${
        fire.name
      }" data-fire-id="${fire.id}">
        <div>
          <strong>${fire.name}</strong>
          <span>${fire.state} · ${fire.year || fire.start_date?.split('-')[0] || ''}</span>
        </div>
        <span class="badge">${formatNumber(fire.acres || 0)} ac</span>
      </button>
    `,
    )
    .join('');

  els.fireList.querySelectorAll('[data-fire-id]').forEach((button) => {
    button.addEventListener('click', () => {
      const fireId = button.dataset.fireId;
      if (!fireId || fireId === state.fireId) return;
      state.fireId = fireId;
      renderFireList(fireCatalog);
      renderFirePins(fireCatalog);
      loadScenario();
    });
  });
};

const renderFirePins = (fires) => {
  firePinsLayer.clearLayers();
  fires.forEach((fire) => {
    if (!fire.lat || !fire.lng) return;
    const isActive = fire.id === state.fireId;
    const marker = L.marker([fire.lat, fire.lng], { opacity: isActive ? 1 : 0.85 }).addTo(firePinsLayer);
    marker.bindPopup(`<strong>${fire.name}</strong><p>${fire.region || ''}</p>`);
    marker.on('click', () => {
      state.fireId = fire.id;
      renderFireList(fireCatalog);
      loadScenario();
    });
  });
};

const renderLayerGroup = (key, features = []) => {
  const group = featureLayerGroups[key];
  if (!group) return;
  group.clearLayers();
  features.forEach((feature) => {
    if (!feature?.coords) return;
    L.circle(feature.coords, {
      radius: feature.radius || 12000,
      color: feature.color || '#ff6a00',
      fillColor: feature.color || '#ff6a00',
      fillOpacity: 0.15 + (feature.intensity || 0) * 0.35,
      weight: 1.1,
    }).addTo(group);
  });
};

const renderLayers = (layers = {}) => {
  Object.keys(featureLayerGroups).forEach((key) => {
    renderLayerGroup(key, layers[key] || []);
  });
};

const syncLayerVisibility = () => {
  els.layerToggles.forEach((toggle) => {
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

const renderHotspots = (markers = []) => {
  hotspotLayer.clearLayers();
  markers.forEach((marker) => {
    if (!marker?.coords) return;
    const popup = `<strong>${marker.title || 'Sector'}</strong><p>${marker.details || ''}</p>`;
    L.marker(marker.coords, { riseOnHover: true }).addTo(hotspotLayer).bindPopup(popup);
  });
};

const renderInsights = (insights = []) => {
  if (!els.insightContainer) return;
  if (!insights.length) {
    els.insightContainer.innerHTML = `
      <article>
        <p class="rail-label">No insights</p>
        <strong>All clear for now.</strong>
        <span>Adjust the sliders to refresh the model.</span>
      </article>
    `;
    return;
  }

  els.insightContainer.innerHTML = insights
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

const renderPriorities = (priorities = []) => {
  if (!els.priorityContainer) return;
  if (!priorities.length) {
    els.priorityContainer.innerHTML = '<p class="muted small">No priorities calculated.</p>';
    return;
  }
  els.priorityContainer.innerHTML = priorities
    .map(
      (priority) => `
        <div class="priority-card">
          <strong>${priority.label} · ${priority.score}%</strong>
          <span>${priority.summary}</span>
        </div>
      `,
    )
    .join('');
};

const renderNextSteps = (steps = []) => {
  if (!els.nextSteps) return;
  if (!steps.length) {
    els.nextSteps.innerHTML = `
      <h3>Next steps</h3>
      <p class="muted small">Adjust the sliders to generate an action plan.</p>
    `;
    return;
  }
  const items = steps.map((step) => `<li>${step}</li>`).join('');
  els.nextSteps.innerHTML = `
    <h3>Next steps</h3>
    <ul>${items}</ul>
  `;
};

const updateStats = (stats = {}) => {
  if (els.confidence && typeof stats.confidence === 'number') {
    els.confidence.textContent = `${Math.round(stats.confidence * 100)}%`;
  }
  if (els.incidents && typeof stats.incidents === 'number') {
    els.incidents.textContent = `${stats.incidents} alerts`;
  }
  if (els.fireMeta && stats.updated && stats.acres) {
    els.fireMeta.textContent = `${stats.updated} · ${formatNumber(stats.acres)} acres`;
  }
};

const updateMapTip = (text) => {
  if (els.mapTip && text) {
    els.mapTip.textContent = text;
  }
};

const updateHeader = (fire = {}, timeline = {}) => {
  if (els.fireTitle) {
    els.fireTitle.textContent = `${fire.name || 'Selected fire'} · ${fire.state || ''}`;
  }
  if (els.mapHeadline) {
    els.mapHeadline.textContent = `${fire.name || 'Fire'} segmentation ready`;
  }
  if (els.mapSubhead && timeline?.label) {
    els.mapSubhead.textContent = timeline.label;
  }
};

const randomInsights = (fire, timeline) => [
  {
    category: 'Action',
    title: 'Crew routing',
    detail: `Assign crews to ${fire.region || 'priority sectors'} within the ${timeline.label || 'current'} window.`,
  },
  {
    category: 'Monitoring',
    title: 'Hydrology sensors',
    detail: '4 gauges exceeded limits; refresh feeds every 15 minutes.',
  },
  {
    category: 'Community',
    title: 'Next briefing',
    detail: 'Push narrated map to the public viewer with a short link.',
  },
];

const randomSteps = (fire, priorities, timeline) => {
  const focus = Object.entries(priorities).sort((a, b) => b[1] - a[1])[0]?.[0] || 'community';
  const templates = {
    community: [
      `Pre-position structure protection teams near the ${fire.region || 'WUI fringe'}.`,
      'Publish a plain-language alert that outlines open roads and shelters.',
    ],
    watershed: [
      'Deploy BAER crews to mulch high-severity headwaters.',
      'Stage sediment-control wattles upstream of drinking water intakes.',
    ],
    infrastructure: [
      'Inspect transmission lines and primary transportation corridors.',
      'Patch scorched culverts with quick-build materials.',
    ],
  };
  const base = templates[focus];
  base.push(`Refresh the ${timeline.label?.toLowerCase() || 'current'} briefing and send to local EOCs.`);
  return base;
};

const buildMockScenario = () => {
  const fire = fireCatalog.find((item) => item.id === state.fireId) || FALLBACK_FIRES[0];
  const timeline = TIMELINE_STAGES[state.timeline] || TIMELINE_STAGES[2];
  const priorities = { ...state.priorities };
  const layers = {};
  Object.keys(featureLayerGroups).forEach((key) => {
    const baseColor = {
      burnSeverity: '#ff4e1f',
      watershedStress: '#33b5ff',
      erosionRisk: '#d16cff',
      infrastructureRisk: '#ffd262',
    }[key];
    layers[key] = Array.from({ length: 2 }).map(() => ({
      coords: [jitter(fire.lat, 0.25), jitter(fire.lng, 0.25)],
      radius: 10000 + Math.random() * 12000,
      color: baseColor,
      intensity: clamp(0.55 + Math.random() * 0.35, 0.2, 1),
    }));
  });

  const stats = {
    confidence: 0.9,
    incidents: 6,
    updated: `${fire.region || fire.state} · Updated ${Math.floor(Math.random() * 60) + 10} mins ago`,
    acres: fire.acres,
  };

  return {
    fire,
    timeline,
    layers,
    markers: Array.from({ length: 3 }).map((_, idx) => ({
      title: `Sector ${idx + 1}`,
      details: 'Model hotspot preview based on MTBS-style segmentation.',
      coords: [jitter(fire.lat, 0.3), jitter(fire.lng, 0.3)],
    })),
    priorities: Object.entries(priorities).map(([key, value]) => ({
      label:
        {
          community: 'Community safety',
          watershed: 'Watershed health',
          infrastructure: 'Infrastructure readiness',
        }[key] || key,
      score: value,
      summary:
        {
          community: 'Focus on structures and evacuation corridors.',
          watershed: 'Stabilize slopes and drinking water sources.',
          infrastructure: 'Keep roads, utilities, and communications online.',
        }[key] || '',
    })),
    insights: randomInsights(fire, timeline),
    nextSteps: randomSteps(fire, priorities, timeline),
    stats,
    mapTip: `${timeline.label} · ${timeline.description}`,
  };
};

const fetchFireCatalog = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/fires`);
    if (!response.ok) throw new Error('Failed to load fire catalog');
    const data = await response.json();
    if (Array.isArray(data.fires) && data.fires.length) {
      fireCatalog = data.fires.map((fire) => ({
        ...fire,
        year: fire.startDate ? new Date(fire.startDate).getFullYear() : undefined,
      }));
      if (!fireCatalog.find((fire) => fire.id === state.fireId)) {
        state.fireId = fireCatalog[0].id;
      }
    }
  } catch (error) {
    console.warn('Using fallback fire catalog', error);
    fireCatalog = [...FALLBACK_FIRES];
  } finally {
    renderFireList(fireCatalog);
    renderFirePins(fireCatalog);
  }
};

const fetchScenario = async () => {
  const params = new URLSearchParams({
    fireId: state.fireId,
    timeline: state.timeline,
    priorityCommunity: state.priorities.community,
    priorityWatershed: state.priorities.watershed,
    priorityInfrastructure: state.priorities.infrastructure,
  });

  try {
    const response = await fetch(`${API_BASE_URL}/api/scenario?${params.toString()}`);
    if (!response.ok) throw new Error('Scenario request failed');
    return await response.json();
  } catch (error) {
    console.warn('Falling back to mock scenario', error);
    return buildMockScenario();
  }
};

const renderScenario = (scenario) => {
  if (!scenario) return;
  renderLayers(scenario.layers);
  renderHotspots(scenario.markers);
  renderPriorities(scenario.priorities);
  renderInsights(scenario.insights);
  renderNextSteps(scenario.nextSteps);
  updateStats(scenario.stats);
  updateMapTip(scenario.mapTip);
  updateHeader(scenario.fire, scenario.timeline);
  if (scenario.fire?.center) {
    map.flyTo(scenario.fire.center, 9, { duration: 1 });
  } else if (scenario.fire?.lat && scenario.fire?.lng) {
    map.flyTo([scenario.fire.lat, scenario.fire.lng], 9, { duration: 1 });
  }
  syncLayerVisibility();
};

const loadScenario = async () => {
  updateForecastLabels();
  setPriorityDisplays();
  const scenario = await fetchScenario();
  renderScenario(scenario);
};

// Event listeners
if (els.prioritySliders) {
  const debouncedScenario = debounce(loadScenario, 400);
  els.prioritySliders.forEach((slider) => {
    slider.addEventListener('input', (event) => {
      const key = event.target.dataset.prioritySlider;
      if (!key) return;
      state.priorities[key] = Number(event.target.value);
      setPriorityDisplays();
      debouncedScenario();
    });
  });
}

if (els.forecastSlider) {
  els.forecastSlider.addEventListener('input', (event) => {
    state.timeline = Number(event.target.value);
    updateForecastLabels();
  });
  els.forecastSlider.addEventListener('change', () => {
    loadScenario();
  });
}

els.layerToggles.forEach((toggle) => {
  toggle.addEventListener('change', () => {
    syncLayerVisibility();
    const label = toggle.nextElementSibling?.textContent?.trim() || 'Layer';
    const stateText = toggle.checked ? 'enabled' : 'disabled';
    if (els.mapTip) {
      const defaultText =
        'Tap a fire pin to load MTBS-style burn severity overlays, then drag the sliders to test scenarios.';
      els.mapTip.textContent = `${label} layer ${stateText}. ${defaultText}`;
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Tooltip system
// ─────────────────────────────────────────────────────────────────────────────
const tooltipBox = document.querySelector('[data-tooltip-box]');
const tooltipElements = document.querySelectorAll('[data-tooltip]');

tooltipElements.forEach((el) => {
  el.addEventListener('mouseenter', (e) => {
    const text = el.dataset.tooltip;
    if (!text || !tooltipBox) return;
    tooltipBox.textContent = text;
    tooltipBox.style.display = 'block';
    positionTooltip(e);
  });

  el.addEventListener('mousemove', (e) => {
    positionTooltip(e);
  });

  el.addEventListener('mouseleave', () => {
    if (tooltipBox) tooltipBox.style.display = 'none';
  });
});

function positionTooltip(e) {
  if (!tooltipBox) return;
  const offsetX = 16;
  const offsetY = 16;
  const x = e.clientX + offsetX;
  const y = e.clientY + offsetY;
  tooltipBox.style.left = `${x}px`;
  tooltipBox.style.top = `${y}px`;
}

// ─────────────────────────────────────────────────────────────────────────────
// LLM Q&A system
// ─────────────────────────────────────────────────────────────────────────────
const qnaInput = document.querySelector('[data-qna-input]');
const qnaSubmit = document.querySelector('[data-qna-submit]');
const qnaResponse = document.querySelector('[data-qna-response]');

if (qnaInput && qnaSubmit && qnaResponse) {
  qnaSubmit.addEventListener('click', async () => {
    const question = qnaInput.value.trim();
    if (!question) {
      qnaResponse.innerHTML = '<p class="muted small">Please type a question first.</p>';
      return;
    }

    qnaResponse.classList.add('loading');
    qnaResponse.textContent = 'Generating answer...';

    try {
      const params = new URLSearchParams({
        fireId: state.fireId || 'camp-fire-2018',
        question,
      });
      const response = await fetch(`${API_BASE_URL}/api/ask?${params.toString()}`);
      if (!response.ok) throw new Error('Failed to fetch answer');
      const data = await response.json();
      
      qnaResponse.classList.remove('loading');
      qnaResponse.innerHTML = `<p><strong>Q:</strong> ${question}</p><p>${data.answer || 'No answer available.'}</p>`;
    } catch (error) {
      console.warn('Q&A fetch failed:', error);
      qnaResponse.classList.remove('loading');
      qnaResponse.innerHTML = `<p class="muted small">Could not generate an answer. Try rephrasing your question or check your connection.</p>`;
    }
  });

  qnaInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      qnaSubmit.click();
    }
  });
}

// Autocomplete functionality
const getStateSuggestions = (query) => {
  if (!query || query.trim().length < 1) {
    return [];
  }
  
  const queryUpper = query.trim().toUpperCase();
  const matches = US_STATES.filter(state => 
    state.code.includes(queryUpper) || 
    state.name.toUpperCase().includes(queryUpper)
  );
  
  // Return top 3 matches
  return matches.slice(0, 3);
};

const renderAutocomplete = (suggestions) => {
  if (!els.autocompleteSuggestions) return;
  
  if (!suggestions || suggestions.length === 0) {
    els.autocompleteSuggestions.style.display = 'none';
    return;
  }
  
  els.autocompleteSuggestions.innerHTML = suggestions
    .map((state, index) => `
      <div class="autocomplete-item" data-suggestion-index="${index}">
        <span class="autocomplete-item-code">${state.code}</span>
        <span class="autocomplete-item-name">${state.name}</span>
      </div>
    `)
    .join('');
  
  els.autocompleteSuggestions.style.display = 'block';
  state.selectedSuggestionIndex = -1;
  
  // Add click handlers
  els.autocompleteSuggestions.querySelectorAll('.autocomplete-item').forEach((item, index) => {
    item.addEventListener('click', () => {
      const selectedState = suggestions[index];
      if (els.searchInput) {
        els.searchInput.value = selectedState.name;
      }
      state.selectedState = selectedState.code;
      els.autocompleteSuggestions.style.display = 'none';
      state.selectedSuggestionIndex = -1;
      updateSearchButtonState();
    });
    
    item.addEventListener('mouseenter', () => {
      state.selectedSuggestionIndex = index;
      updateAutocompleteSelection();
    });
  });
};

const updateAutocompleteSelection = () => {
  if (!els.autocompleteSuggestions) return;
  const items = els.autocompleteSuggestions.querySelectorAll('.autocomplete-item');
  items.forEach((item, index) => {
    if (index === state.selectedSuggestionIndex) {
      item.classList.add('selected');
    } else {
      item.classList.remove('selected');
    }
  });
};

const updateSearchButtonState = () => {
  if (!els.searchBtn) return;
  
  const hasState = state.selectedState !== null;
  const hasYear = state.selectedYear !== null && state.selectedYear !== '';
  const hasMonth = state.selectedMonth !== null && state.selectedMonth !== '';
  
  if (hasState && hasYear && hasMonth) {
    els.searchBtn.disabled = false;
  } else {
    els.searchBtn.disabled = true;
  }
};

// Search input event handlers
if (els.searchInput) {
  let debounceTimeout;
  
  els.searchInput.addEventListener('input', (e) => {
    const query = e.target.value;
    
    clearTimeout(debounceTimeout);
    
    debounceTimeout = setTimeout(() => {
      const suggestions = getStateSuggestions(query);
      renderAutocomplete(suggestions);
    }, 150);
  });
  
  els.searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const items = els.autocompleteSuggestions?.querySelectorAll('.autocomplete-item') || [];
      if (items.length > 0) {
        state.selectedSuggestionIndex = Math.min(
          state.selectedSuggestionIndex + 1,
          items.length - 1
        );
        updateAutocompleteSelection();
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      state.selectedSuggestionIndex = Math.max(state.selectedSuggestionIndex - 1, -1);
      updateAutocompleteSelection();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const items = els.autocompleteSuggestions?.querySelectorAll('.autocomplete-item') || [];
      if (state.selectedSuggestionIndex >= 0 && items[state.selectedSuggestionIndex]) {
        items[state.selectedSuggestionIndex].click();
      }
    } else if (e.key === 'Escape') {
      if (els.autocompleteSuggestions) {
        els.autocompleteSuggestions.style.display = 'none';
      }
    }
  });
  
  // Hide autocomplete when clicking outside
  document.addEventListener('click', (e) => {
    if (!els.searchInput?.contains(e.target) && !els.autocompleteSuggestions?.contains(e.target)) {
      if (els.autocompleteSuggestions) {
        els.autocompleteSuggestions.style.display = 'none';
      }
    }
  });
}

// Year and month dropdown handlers
if (els.yearSelect) {
  els.yearSelect.addEventListener('change', (e) => {
    state.selectedYear = e.target.value;
    updateSearchButtonState();
  });
}

if (els.monthSelect) {
  els.monthSelect.addEventListener('change', (e) => {
    state.selectedMonth = e.target.value;
    updateSearchButtonState();
  });
}

// Search button handler
if (els.searchBtn) {
  els.searchBtn.addEventListener('click', () => {
    if (els.searchBtn.disabled) return;
    
    console.log('Search clicked:', {
      state: state.selectedState,
      year: state.selectedYear,
      month: state.selectedMonth
    });
    
    // TODO: Implement actual search/filter logic here
    // This will filter fires based on selected state, year, and month
  });
}

// Initialize year dropdown on page load
initializeYearDropdown();

fetchFireCatalog().then(loadScenario);
