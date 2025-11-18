const map = L.map('map', {
  zoomControl: false,
}).setView([39.3, -120.9], 7);

L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors',
}).addTo(map);

const markers = [
  {
    coords: [39.54, -121.48],
    title: 'Feather River Canyon',
    details:
      'High burn severity. Prioritize culvert clearing, hydrophobic soil treatment, and wattles along slopes.'
  },
  {
    coords: [38.95, -120.11],
    title: 'South Lake Tahoe Rim',
    details:
      'Moderate burn zone. Focus on debris flow barriers and reseeding native grasses before winter storms.'
  },
  {
    coords: [40.38, -122.15],
    title: 'Shasta foothills',
    details:
      'Critical habitat overlap. Coordinate BAER crews with CAL FIRE to stabilize ridgelines.'
  }
];

markers.forEach((marker) => {
  L.marker(marker.coords)
    .addTo(map)
    .bindPopup(`<strong>${marker.title}</strong><p>${marker.details}</p>`);
});

const severityZones = [
  { coords: [39.3, -121.2], radius: 22000, color: '#ff4e1f' },
  { coords: [39.9, -122.2], radius: 18000, color: '#ff9b2f' },
  { coords: [38.8, -120.5], radius: 15000, color: '#ffd262' }
];

severityZones.forEach((zone) => {
  L.circle(zone.coords, {
    radius: zone.radius,
    color: zone.color,
    fillColor: zone.color,
    fillOpacity: 0.18,
    weight: 1.5,
  }).addTo(map);
});

L.control.zoom({ position: 'bottomright' }).addTo(map);

const slider = document.querySelector('.slider input');
const sliderValue = document.querySelector('[data-slider-value]');

if (slider && sliderValue) {
  slider.addEventListener('input', () => {
    sliderValue.textContent = `${slider.value} yrs`;
  });
}

const chips = document.querySelectorAll('.chip');
chips.forEach((chip) => {
  chip.addEventListener('click', () => {
    chips.forEach((c) => c.classList.remove('active'));
    chip.classList.add('active');
    const [lat, lng] = (chip.dataset.center || '').split(',').map(Number);
    const zoom = Number(chip.dataset.zoom) || 9;
    if (!Number.isNaN(lat) && !Number.isNaN(lng)) {
      map.flyTo([lat, lng], zoom, { duration: 1.2 });
    }
  });
});

const layerToggles = document.querySelectorAll('.layer input');
const mapTipText = document.querySelector('.map-tip p');

if (layerToggles.length && mapTipText) {
  layerToggles.forEach((toggle) => {
    toggle.addEventListener('change', () => {
      const label = toggle.nextElementSibling?.textContent?.trim();
      const state = toggle.checked ? 'enabled' : 'disabled';
      mapTipText.textContent = `${label} layer ${state}. Tap the map to inspect updates.`;
      setTimeout(() => {
        mapTipText.textContent =
          'Tap a marker to view burn intensity, debris flow likelihood, and suggested restoration actions.';
      }, 2800);
    });
  });
}
