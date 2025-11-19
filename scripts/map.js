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
  reburnRisk: L.layerGroup().addTo(map),
  bestNextSteps: L.layerGroup().addTo(map),
};

const firePinsLayer = L.layerGroup().addTo(map);
const hotspotLayer = L.layerGroup().addTo(map);

// Track raster layers for cleanup
const rasterLayers = {
  burnSeverity: null,
  reburnRisk: null,
  bestNextSteps: null
};

L.control.zoom({ position: 'bottomright' }).addTo(map);

const els = {
  fireList: document.querySelector('[data-fire-list]'),
  mapLegend: document.querySelector('[data-map-legend]'),
  legendTitle: document.querySelector('[data-legend-title]'),
  legendItems: document.querySelector('[data-legend-items]'),
  fireTitle: document.querySelector('[data-fire-title]'),
  fireMeta: document.querySelector('[data-fire-meta]'),
  mapHeadline: document.querySelector('[data-map-headline]'),
  mapSubhead: document.querySelector('[data-map-subhead]'),
  priorityContainer: document.querySelector('[data-priorities]'),
  insightContainer: document.querySelector('[data-insights]'),
  nextSteps: document.querySelector('[data-next-steps]'),
  mapTip: document.querySelector('[data-map-tip]'),
  weather: document.querySelector('[data-weather]'),
  reburnRisk: document.querySelector('[data-reburn-risk]'),
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
  
  // Show "no fires found" message if empty
  if (!fires || fires.length === 0) {
    els.fireList.innerHTML = `
      <div class="no-fires-message">
        <p>No fires found for your selection</p>
      </div>
    `;
    return;
  }
  
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
      // Re-render to update active state
      renderFireList(fires);
      renderFirePins(fires);
      // Only clicking a fire updates the map
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
      renderFireList(fires);
      renderFirePins(fires);
      loadScenario();
    });
  });
};

// Function to render MTBS burn severity raster
const renderBurnSeverityRaster = async (fireId) => {
  // Check if georaster libraries are loaded
  const parseGeorasterFn = window.parseGeoraster || (window.georaster && window.georaster.parseGeoraster);
  const GeoRasterLayerClass = window.GeoRasterLayer || (window.georasterLayerForLeaflet && window.georasterLayerForLeaflet.GeoRasterLayer);
  
  if (!parseGeorasterFn || !GeoRasterLayerClass) {
    console.error('Georaster libraries not loaded. Available globals:', Object.keys(window).filter(k => k.toLowerCase().includes('georaster')));
    console.error('parseGeoraster available:', !!parseGeorasterFn);
    console.error('GeoRasterLayer available:', !!GeoRasterLayerClass);
    return;
  }
  
  // Define MTBS Albers Conical Equal Area projection (if proj4 is available)
  // MTBS uses: Albers Conical Equal Area with standard parallels 29.5 and 45.5, central meridian -96.0
  if (typeof proj4 !== 'undefined') {
    // EPSG:5070 is USA_Contiguous_Albers_Equal_Area_Conic
    // But MTBS uses custom parameters, so we'll define it
    try {
      proj4.defs('ESRI:102003', '+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23.0 +lon_0=-96.0 +x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs');
      console.log('MTBS Albers projection defined');
    } catch (e) {
      console.warn('Could not define projection:', e);
    }
  }
  
  // Clear existing raster layer - AGGRESSIVE CLEARING
  if (rasterLayers.burnSeverity) {
    try {
      // Remove from map directly if it's there
      if (map.hasLayer(rasterLayers.burnSeverity)) {
        map.removeLayer(rasterLayers.burnSeverity);
      }
      // Remove from group
      if (featureLayerGroups.burnSeverity.hasLayer(rasterLayers.burnSeverity)) {
        featureLayerGroups.burnSeverity.removeLayer(rasterLayers.burnSeverity);
      }
    } catch (e) {
      console.warn('Error clearing burn severity raster:', e);
    }
    rasterLayers.burnSeverity = null;
  }
  
  // Clear any existing circles and all layers from group
  featureLayerGroups.burnSeverity.clearLayers();
  
  // Ensure group is removed from map before adding new layer
  if (map.hasLayer(featureLayerGroups.burnSeverity)) {
    map.removeLayer(featureLayerGroups.burnSeverity);
  }
  
  try {
    console.log('Loading MTBS burn severity raster for fire:', fireId);
    // Load GeoTIFF from backend
    const response = await fetch(`${API_BASE_URL}/api/burn-severity/${fireId}.tif`);
    
    if (!response.ok) {
      console.warn('MTBS raster not available (status:', response.status, '), using fallback circles');
      return; // Will fall back to circles
    }
    
    const arrayBuffer = await response.arrayBuffer();
    console.log('GeoTIFF loaded, size:', arrayBuffer.byteLength, 'bytes');
    
    // IMPORTANT: Define MTBS projection BEFORE parsing georaster
    // GeoRasterLayer needs the projection to be defined in proj4 during initialization
    if (typeof proj4 !== 'undefined') {
      // MTBS Albers Conical Equal Area projection definition
      // From metadata: standard parallels 29.5 and 45.5, central meridian -96.0, latitude of origin 23.0
      const mtbsAlbersDef = '+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23.0 +lon_0=-96.0 +x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs';
      
      // Define in multiple formats that GeoRasterLayer might look for
      const projectionCodes = [
        '32767',           // Numeric code as string (common for user-defined)
        'EPSG:32767',      // EPSG format
        'EPSG:5070',       // USA Contiguous Albers (similar parameters)
        'ESRI:102003',     // ESRI Albers code
        'MTBS_ALBERS'      // Custom name
      ];
      
      projectionCodes.forEach(code => {
        if (!proj4.defs(code)) {
          proj4.defs(code, mtbsAlbersDef);
          console.log(`Defined projection: ${code}`);
        }
      });
    }
    
    // Now parse the georaster (GeoRasterLayer will use the projection we just defined)
    const georaster = await parseGeorasterFn(arrayBuffer);
    console.log('Georaster parsed successfully:', {
      width: georaster.width,
      height: georaster.height,
      pixelWidth: georaster.pixelWidth,
      pixelHeight: georaster.pixelHeight,
      projection: georaster.projection,
      noDataValue: georaster.noDataValue
    });
    
    // If georaster has a numeric projection code, convert it to string format
    // GeoRasterLayer expects projection codes as strings that proj4 can recognize
    if (georaster.projection && typeof georaster.projection === 'number') {
      const projCode = georaster.projection;
      console.log('Numeric projection code detected:', projCode);
      // Convert to string format - GeoRasterLayer will look for this in proj4
      // We've already defined it as both "32767" and "EPSG:32767"
      georaster.projection = String(projCode);
      console.log('Converted projection to string:', georaster.projection);
    } else if (georaster.projection && typeof georaster.projection === 'string') {
      console.log('Projection code is already a string:', georaster.projection);
    }
    
    // MTBS 6-Class Burn Severity Color Map
    const mtbsColorMap = {
      0: [255, 255, 255, 0],      // Unburned - transparent
      1: [0, 100, 0, 200],        // Low severity - dark green
      2: [144, 238, 144, 200],    // Low-Moderate - light green
      3: [255, 255, 0, 200],      // Moderate - yellow
      4: [255, 165, 0, 200],      // High - orange
      5: [255, 0, 0, 200],        // High (increased) - red
    };
    
    // Create raster layer with exact pixel mapping
    // GeoRasterLayer will automatically handle projection conversion using proj4
    // It reads projection from georaster and converts to Web Mercator (Leaflet's default)
    const rasterLayer = new GeoRasterLayerClass({
      georaster: georaster,
      opacity: 0.7,  // Semi-transparent overlay
      pixelValuesToColorFn: (values) => {
        const severity = Math.round(values[0]); // Get severity value (0-5)
        return mtbsColorMap[severity] || [255, 255, 255, 0];
      },
      resolution: 256,  // Higher = more detail
      updateWhenIdle: true,  // Update when idle to prevent tile caching issues
      keepBuffer: 0  // Don't keep buffer - ensures clean switching
      // Note: GeoRasterLayer automatically reads projection from georaster
      // and uses proj4 to convert to Web Mercator for Leaflet
    });
    
    rasterLayer.addTo(featureLayerGroups.burnSeverity);
    rasterLayers.burnSeverity = rasterLayer;
    
    console.log('MTBS burn severity raster layer added to map successfully');
    
    // Force map refresh to ensure new layer is visible at all zoom levels
    map.invalidateSize();
    
    // Ensure layer is visible
    syncLayerVisibility();
    
  } catch (error) {
    console.error('Failed to load MTBS burn severity raster:', error);
    console.error('Error details:', error.message, error.stack);
    // Fallback: will use circles from backend
  }
};

// Function to render reburn risk raster - EXACTLY like burn severity, just different image
const renderReburnRiskRaster = async (fireId) => {
  // Check if georaster libraries are loaded
  const parseGeorasterFn = window.parseGeoraster || (window.georaster && window.georaster.parseGeoraster);
  const GeoRasterLayerClass = window.GeoRasterLayer || (window.georasterLayerForLeaflet && window.georasterLayerForLeaflet.GeoRasterLayer);
  
  if (!parseGeorasterFn || !GeoRasterLayerClass) {
    console.error('Georaster libraries not loaded. Available globals:', Object.keys(window).filter(k => k.toLowerCase().includes('georaster')));
    console.error('parseGeoraster available:', !!parseGeorasterFn);
    console.error('GeoRasterLayer available:', !!GeoRasterLayerClass);
    return;
  }
  
  // Define MTBS Albers Conical Equal Area projection (if proj4 is available)
  // MTBS uses: Albers Conical Equal Area with standard parallels 29.5 and 45.5, central meridian -96.0
  if (typeof proj4 !== 'undefined') {
    // EPSG:5070 is USA_Contiguous_Albers_Equal_Area_Conic
    // But MTBS uses custom parameters, so we'll define it
    try {
      proj4.defs('ESRI:102003', '+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23.0 +lon_0=-96.0 +x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs');
      console.log('MTBS Albers projection defined');
    } catch (e) {
      console.warn('Could not define projection:', e);
    }
  }
  
  // Clear existing raster layer - AGGRESSIVE CLEARING
  if (rasterLayers.reburnRisk) {
    try {
      // Remove from map directly if it's there
      if (map.hasLayer(rasterLayers.reburnRisk)) {
        map.removeLayer(rasterLayers.reburnRisk);
      }
      // Remove from group
      if (featureLayerGroups.reburnRisk.hasLayer(rasterLayers.reburnRisk)) {
        featureLayerGroups.reburnRisk.removeLayer(rasterLayers.reburnRisk);
      }
    } catch (e) {
      console.warn('Error clearing reburn risk raster:', e);
    }
    rasterLayers.reburnRisk = null;
  }
  
  // Clear any existing circles and all layers from group
  featureLayerGroups.reburnRisk.clearLayers();
  
  // Ensure group is removed from map before adding new layer
  if (map.hasLayer(featureLayerGroups.reburnRisk)) {
    map.removeLayer(featureLayerGroups.reburnRisk);
  }
  
  try {
    console.log('Loading reburn risk raster for fire:', fireId);
    // Load GeoTIFF from backend
    const response = await fetch(`${API_BASE_URL}/api/reburn-risk/${fireId}.tif`);
    
    if (!response.ok) {
      console.warn('Reburn risk raster not available (status:', response.status, '), using fallback circles');
      return; // Will fall back to circles
    }
    
    const arrayBuffer = await response.arrayBuffer();
    console.log('GeoTIFF loaded, size:', arrayBuffer.byteLength, 'bytes');
    
    // IMPORTANT: Define MTBS projection BEFORE parsing georaster
    // GeoRasterLayer needs the projection to be defined in proj4 during initialization
    if (typeof proj4 !== 'undefined') {
      // MTBS Albers Conical Equal Area projection definition
      // From metadata: standard parallels 29.5 and 45.5, central meridian -96.0, latitude of origin 23.0
      const mtbsAlbersDef = '+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23.0 +lon_0=-96.0 +x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs';
      
      // Define in multiple formats that GeoRasterLayer might look for
      const projectionCodes = [
        '32767',           // Numeric code as string (common for user-defined)
        'EPSG:32767',      // EPSG format
        'EPSG:5070',       // USA Contiguous Albers (similar parameters)
        'ESRI:102003',     // ESRI Albers code
        'MTBS_ALBERS'      // Custom name
      ];
      
      projectionCodes.forEach(code => {
        if (!proj4.defs(code)) {
          proj4.defs(code, mtbsAlbersDef);
          console.log(`Defined projection: ${code}`);
        }
      });
    }
    
    // Now parse the georaster (GeoRasterLayer will use the projection we just defined)
    const georaster = await parseGeorasterFn(arrayBuffer);
    console.log('Georaster parsed successfully:', {
      width: georaster.width,
      height: georaster.height,
      pixelWidth: georaster.pixelWidth,
      pixelHeight: georaster.pixelHeight,
      projection: georaster.projection,
      noDataValue: georaster.noDataValue
    });
    
    // If georaster has a numeric projection code, convert it to string format
    // GeoRasterLayer expects projection codes as strings that proj4 can recognize
    if (georaster.projection && typeof georaster.projection === 'number') {
      const projCode = georaster.projection;
      console.log('Numeric projection code detected:', projCode);
      // Convert to string format - GeoRasterLayer will look for this in proj4
      // We've already defined it as both "32767" and "EPSG:32767"
      georaster.projection = String(projCode);
      console.log('Converted projection to string:', georaster.projection);
    } else if (georaster.projection && typeof georaster.projection === 'string') {
      console.log('Projection code is already a string:', georaster.projection);
    }
    
    // Reburn Risk Color Map: 0=Low (green), 1=Medium (orange), 2=High (red), 255=NoData/Unburned (transparent)
    const reburnColorMap = {
      0: [0, 153, 0, 200],        // Low - green
      1: [255, 165, 0, 200],      // Medium - orange
      2: [255, 0, 0, 200],        // High - red
      255: [255, 255, 255, 0],    // NoData/Unburned - transparent
    };
    
    // Create raster layer with exact pixel mapping
    // GeoRasterLayer will automatically handle projection conversion using proj4
    // It reads projection from georaster and converts to Web Mercator (Leaflet's default)
    const rasterLayer = new GeoRasterLayerClass({
      georaster: georaster,
      opacity: 0.7,  // Semi-transparent overlay
      pixelValuesToColorFn: (values) => {
        const risk = Math.round(values[0]); // Get risk value (0-2, or 255 for NoData)
        return reburnColorMap[risk] || [255, 255, 255, 0];
      },
      resolution: 256,  // Higher = more detail
      updateWhenIdle: true,  // Update when idle to prevent tile caching issues
      keepBuffer: 0  // Don't keep buffer - ensures clean switching
      // Note: GeoRasterLayer automatically reads projection from georaster
      // and uses proj4 to convert to Web Mercator for Leaflet
    });
    
    rasterLayer.addTo(featureLayerGroups.reburnRisk);
    rasterLayers.reburnRisk = rasterLayer;
    
    console.log('Reburn risk raster layer added to map successfully');
    
    // Force map refresh to ensure new layer is visible at all zoom levels
    map.invalidateSize();
    
    // Ensure layer is visible
    syncLayerVisibility();
    
  } catch (error) {
    console.error('Failed to load reburn risk raster:', error);
    console.error('Error details:', error.message, error.stack);
    // Fallback: will use circles from backend
  }
};

// Function to render best next steps raster - EXACTLY like burn severity, just different image
const renderBestNextStepsRaster = async (fireId) => {
  // Check if georaster libraries are loaded
  const parseGeorasterFn = window.parseGeoraster || (window.georaster && window.georaster.parseGeoraster);
  const GeoRasterLayerClass = window.GeoRasterLayer || (window.georasterLayerForLeaflet && window.georasterLayerForLeaflet.GeoRasterLayer);
  
  if (!parseGeorasterFn || !GeoRasterLayerClass) {
    console.error('Georaster libraries not loaded. Available globals:', Object.keys(window).filter(k => k.toLowerCase().includes('georaster')));
    console.error('parseGeoraster available:', !!parseGeorasterFn);
    console.error('GeoRasterLayer available:', !!GeoRasterLayerClass);
    return;
  }
  
  // Define MTBS Albers Conical Equal Area projection (if proj4 is available)
  // MTBS uses: Albers Conical Equal Area with standard parallels 29.5 and 45.5, central meridian -96.0
  if (typeof proj4 !== 'undefined') {
    // EPSG:5070 is USA_Contiguous_Albers_Equal_Area_Conic
    // But MTBS uses custom parameters, so we'll define it
    try {
      proj4.defs('ESRI:102003', '+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23.0 +lon_0=-96.0 +x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs');
      console.log('MTBS Albers projection defined');
    } catch (e) {
      console.warn('Could not define projection:', e);
    }
  }
  
  // Clear existing raster layer - AGGRESSIVE CLEARING
  if (rasterLayers.bestNextSteps) {
    try {
      // Remove from map directly if it's there
      if (map.hasLayer(rasterLayers.bestNextSteps)) {
        map.removeLayer(rasterLayers.bestNextSteps);
      }
      // Remove from group
      if (featureLayerGroups.bestNextSteps.hasLayer(rasterLayers.bestNextSteps)) {
        featureLayerGroups.bestNextSteps.removeLayer(rasterLayers.bestNextSteps);
      }
    } catch (e) {
      console.warn('Error clearing best next steps raster:', e);
    }
    rasterLayers.bestNextSteps = null;
  }
  
  // Clear any existing circles and all layers from group
  featureLayerGroups.bestNextSteps.clearLayers();
  
  // Ensure group is removed from map before adding new layer
  if (map.hasLayer(featureLayerGroups.bestNextSteps)) {
    map.removeLayer(featureLayerGroups.bestNextSteps);
  }
  
  try {
    console.log('Loading best next steps raster for fire:', fireId);
    // Load GeoTIFF from backend
    const response = await fetch(`${API_BASE_URL}/api/best-next-steps/${fireId}.tif`);
    
    if (!response.ok) {
      console.warn('Best next steps raster not available (status:', response.status, '), using fallback circles');
      return; // Will fall back to circles
    }
    
    const arrayBuffer = await response.arrayBuffer();
    console.log('GeoTIFF loaded, size:', arrayBuffer.byteLength, 'bytes');
    
    // IMPORTANT: Define MTBS projection BEFORE parsing georaster
    // GeoRasterLayer needs the projection to be defined in proj4 during initialization
    if (typeof proj4 !== 'undefined') {
      // MTBS Albers Conical Equal Area projection definition
      // From metadata: standard parallels 29.5 and 45.5, central meridian -96.0, latitude of origin 23.0
      const mtbsAlbersDef = '+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23.0 +lon_0=-96.0 +x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs';
      
      // Define in multiple formats that GeoRasterLayer might look for
      const projectionCodes = [
        '32767',           // Numeric code as string (common for user-defined)
        'EPSG:32767',      // EPSG format
        'EPSG:5070',       // USA Contiguous Albers (similar parameters)
        'ESRI:102003',     // ESRI Albers code
        'MTBS_ALBERS'      // Custom name
      ];
      
      projectionCodes.forEach(code => {
        if (!proj4.defs(code)) {
          proj4.defs(code, mtbsAlbersDef);
          console.log(`Defined projection: ${code}`);
        }
      });
    }
    
    // Now parse the georaster (GeoRasterLayer will use the projection we just defined)
    const georaster = await parseGeorasterFn(arrayBuffer);
    console.log('Georaster parsed successfully:', {
      width: georaster.width,
      height: georaster.height,
      pixelWidth: georaster.pixelWidth,
      pixelHeight: georaster.pixelHeight,
      projection: georaster.projection,
      noDataValue: georaster.noDataValue
    });
    
    // If georaster has a numeric projection code, convert it to string format
    // GeoRasterLayer expects projection codes as strings that proj4 can recognize
    if (georaster.projection && typeof georaster.projection === 'number') {
      const projCode = georaster.projection;
      console.log('Numeric projection code detected:', projCode);
      // Convert to string format - GeoRasterLayer will look for this in proj4
      // We've already defined it as both "32767" and "EPSG:32767"
      georaster.projection = String(projCode);
      console.log('Converted projection to string:', georaster.projection);
    } else if (georaster.projection && typeof georaster.projection === 'string') {
      console.log('Projection code is already a string:', georaster.projection);
    }
    
    // Best Next Steps Color Map
    const stepsColorMap = {
      0: [128, 128, 128, 200],    // Abandon/Monitor - gray
      1: [255, 255, 0, 200],      // Fuel Reduction - yellow
      2: [0, 102, 0, 200],        // Reforest - dark green
      3: [153, 102, 51, 200],     // Soil Stabilization - brown
      255: [255, 255, 255, 0],   // NoData - transparent
    };
    
    // Create raster layer with exact pixel mapping
    // GeoRasterLayer will automatically handle projection conversion using proj4
    // It reads projection from georaster and converts to Web Mercator (Leaflet's default)
    const rasterLayer = new GeoRasterLayerClass({
      georaster: georaster,
      opacity: 0.7,  // Semi-transparent overlay
      pixelValuesToColorFn: (values) => {
        const step = Math.round(values[0]); // Get step value (0-3, or 255 for NoData)
        if (step === 255 || isNaN(step)) {
          return [255, 255, 255, 0]; // Transparent
        }
        return stepsColorMap[step] || [255, 255, 255, 0];
      },
      resolution: 256,  // Higher = more detail
      updateWhenIdle: true,  // Update when idle to prevent tile caching issues
      keepBuffer: 0  // Don't keep buffer - ensures clean switching
      // Note: GeoRasterLayer automatically reads projection from georaster
      // and uses proj4 to convert to Web Mercator for Leaflet
    });
    
    rasterLayer.addTo(featureLayerGroups.bestNextSteps);
    rasterLayers.bestNextSteps = rasterLayer;
    
    console.log('Best next steps raster layer added to map successfully');
    
    // Force map refresh to ensure new layer is visible at all zoom levels
    map.invalidateSize();
    
    // Ensure layer is visible
    syncLayerVisibility();
    
  } catch (error) {
    console.error('Failed to load best next steps raster:', error);
    console.error('Error details:', error.message, error.stack);
    // Fallback: will use circles from backend
  }
};

const renderLayerGroup = async (key, features = []) => {
  const group = featureLayerGroups[key];
  if (!group) return;
  
  // Special handling for raster layers - use GeoTIFF if available
  if (key === 'burnSeverity' && state.fireId) {
    await renderBurnSeverityRaster(state.fireId);
    return; // Don't render circles for burn severity when raster is available
  }
  
  if (key === 'reburnRisk' && state.fireId) {
    await renderReburnRiskRaster(state.fireId);
    return; // Don't render circles for reburn risk when raster is available
  }
  
  if (key === 'bestNextSteps' && state.fireId) {
    await renderBestNextStepsRaster(state.fireId);
    return; // Don't render circles for best next steps when raster is available
  }
  
  // For other layers, or if raster fails, use circles as before
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

const renderLayers = async (layers = {}) => {
  const promises = Object.keys(featureLayerGroups).map((key) => {
    return renderLayerGroup(key, layers[key] || []);
  });
  await Promise.all(promises);
};

const syncLayerVisibility = () => {
  els.layerToggles.forEach((toggle) => {
    const key = toggle.dataset.layer;
    const group = featureLayerGroups[key];
    if (!group) return;
    
    // Only add/remove if the toggle state matches what's on the map
    const isOnMap = map.hasLayer(group);
    
    if (toggle.checked && !isOnMap) {
      // Only add if checked and not already on map
      map.addLayer(group);
    } else if (!toggle.checked && isOnMap) {
      // Only remove if unchecked and currently on map
      map.removeLayer(group);
    }
  });
};

// Update legend based on selected layer
const updateLegend = (layerKey) => {
  if (!els.mapLegend || !els.legendItems || !els.legendTitle) return;
  
  const legends = {
    burnSeverity: {
      title: 'Burn Severity',
      items: [
        { color: 'transparent', label: 'Unburned', border: '1px dashed rgba(255, 255, 255, 0.3)' },
        { color: 'rgba(0, 100, 0, 0.78)', label: 'Low severity' },
        { color: 'rgba(144, 238, 144, 0.78)', label: 'Low-Moderate' },
        { color: 'rgba(255, 255, 0, 0.78)', label: 'Moderate' },
        { color: 'rgba(255, 165, 0, 0.78)', label: 'High' },
        { color: 'rgba(255, 0, 0, 0.78)', label: 'High (increased)' }
      ]
    },
    reburnRisk: {
      title: 'Reburn Risk',
      items: [
        { color: 'rgba(0, 153, 0, 0.78)', label: 'Low' },
        { color: 'rgba(255, 165, 0, 0.78)', label: 'Medium' },
        { color: 'rgba(255, 0, 0, 0.78)', label: 'High' }
      ]
    },
    bestNextSteps: {
      title: 'Best Next Steps',
      items: [
        { color: 'rgba(128, 128, 128, 0.78)', label: 'Abandon/Monitor' },
        { color: 'rgba(255, 255, 0, 0.78)', label: 'Fuel Reduction' },
        { color: 'rgba(0, 102, 0, 0.78)', label: 'Reforest' },
        { color: 'rgba(153, 102, 51, 0.78)', label: 'Soil Stabilization' }
      ]
    }
  };
  
  const legend = legends[layerKey];
  if (!legend) {
    els.mapLegend.style.display = 'none';
    return;
  }
  
  // Update title
  els.legendTitle.textContent = legend.title;
  
  // Clear and populate legend items
  els.legendItems.innerHTML = legend.items.map(item => {
    const borderStyle = item.border ? `border: ${item.border};` : '';
    return `
    <div class="legend-item">
      <div class="legend-color" style="background-color: ${item.color}; ${borderStyle}"></div>
      <span class="legend-label">${item.label}</span>
    </div>
  `;
  }).join('');
  
  // Show legend
  els.mapLegend.style.display = 'block';
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
  if (els.weather && stats.weather) {
    els.weather.textContent = stats.weather;
  }
  if (els.reburnRisk && stats.reburnRisk) {
    els.reburnRisk.textContent = stats.reburnRisk;
    // Update risk class for color coding
    els.reburnRisk.className = `risk-${stats.reburnRisk.toLowerCase()}`;
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
    // Format: "Canyon Fire, State zipcode" - e.g., "Canyon Fire, CA 93436"
    let location = '';
    if (fire.zipcode && fire.state) {
      location = `${fire.state} ${fire.zipcode}`;
    } else if (fire.zipcode) {
      location = fire.zipcode;
    } else if (fire.region) {
      location = fire.region;
    } else if (fire.state) {
      location = fire.state;
    }
    els.mapHeadline.textContent = `${fire.name || 'Fire'}, ${location}`;
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
      reburnRisk: '#ff6b35',
      bestNextSteps: '#4ecdc4',
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

const fetchFireCatalog = async (filters = null) => {
  try {
    let url = `${API_BASE_URL}/api/fires`;
    const params = new URLSearchParams();
    
    if (filters) {
      if (filters.state) {
        params.append('state', filters.state);
      }
      if (filters.year) {
        params.append('year', filters.year);
      }
    }
    
    if (params.toString()) {
      url += `?${params.toString()}`;
    }
    
    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to load fire catalog');
    const data = await response.json();
    if (Array.isArray(data.fires) && data.fires.length) {
      fireCatalog = data.fires.map((fire) => ({
        ...fire,
        year: fire.startDate ? new Date(fire.startDate).getFullYear() : 
              (fire.start_date ? new Date(fire.start_date).getFullYear() : undefined),
      }));
    } else {
      fireCatalog = [];
    }
  } catch (error) {
    console.warn('Using fallback fire catalog', error);
    fireCatalog = [...FALLBACK_FIRES];
  }
  
  // Return the catalog - don't render here
  return fireCatalog;
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

const renderScenario = async (scenario) => {
  if (!scenario) return;
  await renderLayers(scenario.layers);
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
  
  // Update legend for the currently checked layer
  const checkedToggle = Array.from(els.layerToggles).find(t => t.checked);
  if (checkedToggle) {
    const activeKey = checkedToggle.dataset.layer;
    updateLegend(activeKey);
  }
};

const loadScenario = async () => {
  updateForecastLabels();
  setPriorityDisplays();
  const scenario = await fetchScenario();
  await renderScenario(scenario);
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

// Helper function to completely clear ALL layers from the map
const clearAllLayers = () => {
  console.log('Clearing all map layers...');
  
  // FIRST: Completely destroy all raster layers (including their tile caches)
  if (rasterLayers.burnSeverity) {
    try {
      const layer = rasterLayers.burnSeverity;
      
      // Remove from map directly (multiple attempts)
      if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
      
      // Remove from group
      if (featureLayerGroups.burnSeverity.hasLayer(layer)) {
        featureLayerGroups.burnSeverity.removeLayer(layer);
      }
      
      // Destroy the layer completely (clears internal tile cache)
      if (layer.remove) {
        layer.remove();
      }
      if (layer.removeFrom) {
        layer.removeFrom(map);
      }
      
      // Aggressively clear tile cache - check multiple possible properties
      if (layer._tiles) {
        Object.keys(layer._tiles).forEach(key => {
          const tile = layer._tiles[key];
          if (tile) {
            if (tile.el && tile.el.parentNode) {
              tile.el.parentNode.removeChild(tile.el);
            }
            if (tile.el) {
              tile.el.remove();
            }
          }
        });
        layer._tiles = {};
      }
      
      // Clear any canvas elements
      if (layer._canvas) {
        if (layer._canvas.parentNode) {
          layer._canvas.parentNode.removeChild(layer._canvas);
        }
        layer._canvas = null;
      }
      
      // Clear any container
      if (layer._container) {
        if (layer._container.parentNode) {
          layer._container.parentNode.removeChild(layer._container);
        }
        layer._container = null;
      }
      
      // Force remove from map's internal layers
      if (map._layers) {
        const layerId = layer._leaflet_id;
        if (layerId && map._layers[layerId]) {
          delete map._layers[layerId];
        }
      }
      
    } catch (e) {
      console.warn('Error removing burn severity raster:', e);
    }
    rasterLayers.burnSeverity = null;
  }
  
  if (rasterLayers.reburnRisk) {
    try {
      const layer = rasterLayers.reburnRisk;
      
      // Remove from map directly (multiple attempts)
      if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
      
      // Remove from group
      if (featureLayerGroups.reburnRisk.hasLayer(layer)) {
        featureLayerGroups.reburnRisk.removeLayer(layer);
      }
      
      // Destroy the layer completely (clears internal tile cache)
      if (layer.remove) {
        layer.remove();
      }
      if (layer.removeFrom) {
        layer.removeFrom(map);
      }
      
      // Aggressively clear tile cache
      if (layer._tiles) {
        Object.keys(layer._tiles).forEach(key => {
          const tile = layer._tiles[key];
          if (tile) {
            if (tile.el && tile.el.parentNode) {
              tile.el.parentNode.removeChild(tile.el);
            }
            if (tile.el) {
              tile.el.remove();
            }
          }
        });
        layer._tiles = {};
      }
      
      // Clear any canvas elements
      if (layer._canvas) {
        if (layer._canvas.parentNode) {
          layer._canvas.parentNode.removeChild(layer._canvas);
        }
        layer._canvas = null;
      }
      
      // Clear any container
      if (layer._container) {
        if (layer._container.parentNode) {
          layer._container.parentNode.removeChild(layer._container);
        }
        layer._container = null;
      }
      
      // Force remove from map's internal layers
      if (map._layers) {
        const layerId = layer._leaflet_id;
        if (layerId && map._layers[layerId]) {
          delete map._layers[layerId];
        }
      }
      
    } catch (e) {
      console.warn('Error removing reburn risk raster:', e);
    }
    rasterLayers.reburnRisk = null;
  }
  
  if (rasterLayers.bestNextSteps) {
    try {
      const layer = rasterLayers.bestNextSteps;
      
      // Remove from map directly (multiple attempts)
      if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
      
      // Remove from group
      if (featureLayerGroups.bestNextSteps.hasLayer(layer)) {
        featureLayerGroups.bestNextSteps.removeLayer(layer);
      }
      
      // Destroy the layer completely (clears internal tile cache)
      if (layer.remove) {
        layer.remove();
      }
      if (layer.removeFrom) {
        layer.removeFrom(map);
      }
      
      // Aggressively clear tile cache
      if (layer._tiles) {
        Object.keys(layer._tiles).forEach(key => {
          const tile = layer._tiles[key];
          if (tile) {
            if (tile.el && tile.el.parentNode) {
              tile.el.parentNode.removeChild(tile.el);
            }
            if (tile.el) {
              tile.el.remove();
            }
          }
        });
        layer._tiles = {};
      }
      
      // Clear any canvas elements
      if (layer._canvas) {
        if (layer._canvas.parentNode) {
          layer._canvas.parentNode.removeChild(layer._canvas);
        }
        layer._canvas = null;
      }
      
      // Clear any container
      if (layer._container) {
        if (layer._container.parentNode) {
          layer._container.parentNode.removeChild(layer._container);
        }
        layer._container = null;
      }
      
      // Force remove from map's internal layers
      if (map._layers) {
        const layerId = layer._leaflet_id;
        if (layerId && map._layers[layerId]) {
          delete map._layers[layerId];
        }
      }
      
    } catch (e) {
      console.warn('Error removing best next steps raster:', e);
    }
    rasterLayers.bestNextSteps = null;
  }
  
  // SECOND: Clear all features from all layer groups and remove groups from map
  Object.keys(featureLayerGroups).forEach(key => {
    const group = featureLayerGroups[key];
    
    // Remove all layers from the group (including any remaining rasters)
    try {
      group.eachLayer((layer) => {
        try {
          group.removeLayer(layer);
          // Also try removing directly from map if it's there
          if (map.hasLayer(layer)) {
            map.removeLayer(layer);
          }
        } catch (e) {
          console.warn(`Error removing layer from ${key}:`, e);
        }
      });
    } catch (e) {
      console.warn(`Error iterating layers in ${key}:`, e);
    }
    
    // Clear the group completely
    group.clearLayers();
    
    // FORCE remove the group from map (even if it says it's not there)
    try {
      if (map.hasLayer(group)) {
        map.removeLayer(group);
      }
    } catch (e) {
      console.warn(`Error removing ${key} group from map:`, e);
    }
  });
  
  // Force a map refresh to ensure everything is cleared
  if (map && typeof map.invalidateSize === 'function') {
    map.invalidateSize();
  }
  
  // Force redraw of all tiles - this clears any cached tile layers
  if (map && map.eachLayer) {
    map.eachLayer((layer) => {
      // If it's a tile layer (has _tileZoom or _tiles), try to redraw it
      if (layer.redraw && typeof layer.redraw === 'function') {
        try {
          layer.redraw();
        } catch (e) {
          // Ignore errors
        }
      }
    });
  }
  
  // Force a complete map refresh
  if (map && map._renderer) {
    try {
      map._renderer._update();
    } catch (e) {
      // Ignore errors
    }
  }
  
  console.log('All layers cleared completely');
};

// Handle zoom events to ensure only active layer is visible
map.on('zoomend', () => {
  // After zoom, ensure only the checked layer is visible
  const checkedToggle = Array.from(els.layerToggles).find(t => t.checked);
  if (checkedToggle) {
    const activeKey = checkedToggle.dataset.layer;
    
    // Aggressively clear any stray layers that might have been cached
    Object.keys(featureLayerGroups).forEach(key => {
      if (key !== activeKey) {
        const group = featureLayerGroups[key];
        
        // Remove group from map
        if (map.hasLayer(group)) {
          map.removeLayer(group);
        }
        
        // Clear all layers from the group
        group.clearLayers();
        
        // Also clear the raster layer if it exists
        const rasterKey = key === 'burnSeverity' ? 'burnSeverity' : 
                         key === 'reburnRisk' ? 'reburnRisk' : 
                         key === 'bestNextSteps' ? 'bestNextSteps' : null;
        if (rasterKey && rasterLayers[rasterKey]) {
          try {
            const layer = rasterLayers[rasterKey];
            if (map.hasLayer(layer)) {
              map.removeLayer(layer);
            }
            if (group.hasLayer(layer)) {
              group.removeLayer(layer);
            }
            if (layer.remove) {
              layer.remove();
            }
            // Aggressively clear tile cache
            if (layer._tiles) {
              Object.keys(layer._tiles).forEach(tileKey => {
                const tile = layer._tiles[tileKey];
                if (tile) {
                  if (tile.el && tile.el.parentNode) {
                    tile.el.parentNode.removeChild(tile.el);
                  }
                  if (tile.el) {
                    tile.el.remove();
                  }
                }
              });
              layer._tiles = {};
            }
            // Clear canvas and container
            if (layer._canvas && layer._canvas.parentNode) {
              layer._canvas.parentNode.removeChild(layer._canvas);
              layer._canvas = null;
            }
            if (layer._container && layer._container.parentNode) {
              layer._container.parentNode.removeChild(layer._container);
              layer._container = null;
            }
            // Remove from map's internal layers
            if (map._layers && layer._leaflet_id) {
              delete map._layers[layer._leaflet_id];
            }
          } catch (e) {
            console.warn(`Error clearing ${rasterKey} on zoom:`, e);
          }
        }
      }
    });
    
    // Force multiple map refreshes
    map.invalidateSize();
    setTimeout(() => map.invalidateSize(), 50);
  }
});

els.layerToggles.forEach((toggle) => {
  toggle.addEventListener('change', async () => {
    const key = toggle.dataset.layer;
    
    // ALWAYS clear ALL layers first - ensures clean state
    clearAllLayers();
    
    // Force map to redraw and clear any cached tiles
    map.invalidateSize();
    
    // Make layers mutually exclusive - uncheck all others when one is checked
    if (toggle.checked) {
      // Uncheck all other toggles FIRST
      els.layerToggles.forEach((otherToggle) => {
        if (otherToggle !== toggle) {
          otherToggle.checked = false;
        }
      });
      
      // Longer delay to ensure clearing is complete and map has refreshed
      await new Promise(resolve => setTimeout(resolve, 200));
      
      // Force multiple map refreshes to clear all cached tiles
      map.invalidateSize();
      map._resetView(map.getCenter(), map.getZoom(), { reset: true });
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // Now load the selected layer's raster
      if (state.fireId) {
        if (key === 'burnSeverity') {
          await renderBurnSeverityRaster(state.fireId);
          updateLegend('burnSeverity');
        } else if (key === 'reburnRisk') {
          await renderReburnRiskRaster(state.fireId);
          updateLegend('reburnRisk');
        } else if (key === 'bestNextSteps') {
          await renderBestNextStepsRaster(state.fireId);
          updateLegend('bestNextSteps');
        }
      }
      
      // Force final refresh after layer is loaded - multiple times to ensure
      map.invalidateSize();
      setTimeout(() => map.invalidateSize(), 100);
      setTimeout(() => map.invalidateSize(), 300);
    } else {
      // Layer unchecked - hide legend
      if (els.mapLegend) {
        els.mapLegend.style.display = 'none';
      }
    }
    // If unchecked, layers are already cleared by clearAllLayers()
    
    // Sync visibility after everything is loaded/cleared
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
  
  if (hasState && hasYear) {
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

// Search button handler
if (els.searchBtn) {
  els.searchBtn.addEventListener('click', async () => {
    if (els.searchBtn.disabled) return;
    
    // Also check if user typed state code directly in input
    let stateCode = state.selectedState;
    if (!stateCode && els.searchInput?.value) {
      const inputValue = els.searchInput.value.trim().toUpperCase();
      // Check if it's a 2-letter state code
      if (inputValue.length === 2) {
        const foundState = US_STATES.find(s => s.code === inputValue);
        if (foundState) {
          stateCode = foundState.code;
          state.selectedState = stateCode;
        }
      } else {
        // Check if it matches a state name
        const foundState = US_STATES.find(s => s.name.toUpperCase() === inputValue);
        if (foundState) {
          stateCode = foundState.code;
          state.selectedState = stateCode;
        }
      }
    }
    
    const filters = {
      state: stateCode,
      year: state.selectedYear ? parseInt(state.selectedYear) : null,
    };
    
    // Fetch filtered fires
    const filteredFires = await fetchFireCatalog(filters);
    
    // Sort filtered results by year descending (newest first)
    const sortedFilteredFires = [...filteredFires].sort((a, b) => {
      const getYear = (fire) => {
        const dateStr = fire.start_date || fire.startDate || '';
        if (dateStr) {
          const year = parseInt(dateStr.split('-')[0]);
          return isNaN(year) ? 0 : year;
        }
        return 0;
      };
      
      const yearA = getYear(a);
      const yearB = getYear(b);
      
      if (yearA === yearB) {
        const dateA = a.start_date || a.startDate || '';
        const dateB = b.start_date || b.startDate || '';
        return dateB.localeCompare(dateA);
      }
      
      return yearB - yearA; // Descending order (newest first)
    });
    
    console.log('Filtered fires (sorted by year descending):', sortedFilteredFires.map(f => `${f.name} (${f.start_date || f.startDate})`));
    
    // Display filtered results (don't update map)
    renderFireList(sortedFilteredFires);
    renderFirePins(sortedFilteredFires);
  });
}

// Initialize year dropdown on page load
initializeYearDropdown();

// Load top 4 most recent fires by default (sorted by recency)
fetchFireCatalog().then((allFires) => {
  // Backend already sorts by date, but ensure we sort by year descending (newest first)
  const sortedFires = [...allFires].sort((a, b) => {
    // Extract year from date string (format: YYYY-MM-DD)
    const getYear = (fire) => {
      const dateStr = fire.start_date || fire.startDate || '';
      if (dateStr) {
        const year = parseInt(dateStr.split('-')[0]);
        return isNaN(year) ? 0 : year;
      }
      return 0;
    };
    
    const yearA = getYear(a);
    const yearB = getYear(b);
    
    // If same year, sort by full date
    if (yearA === yearB) {
      const dateA = a.start_date || a.startDate || '';
      const dateB = b.start_date || b.startDate || '';
      return dateB.localeCompare(dateA); // Newest first
    }
    
    // Sort by year descending (newest first)
    return yearB - yearA;
  });
  
  const top4Fires = sortedFires.slice(0, 4);
  console.log('Top 4 fires (sorted by year descending):', top4Fires.map(f => `${f.name} (${f.start_date || f.startDate})`));
  
  renderFireList(top4Fires);
  renderFirePins(top4Fires);
  
  // Load scenario for first fire (newest) if available
  if (top4Fires.length > 0) {
    state.fireId = top4Fires[0].id;
    loadScenario();
  }
});
