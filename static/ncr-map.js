// GasWatch simple NCR city diagram: no tile service, Leaflet or API key.
// Display follows the static Metro Manila reference illustration supplied by the project owner.
// Click/tap a city name (or use the adjacent accessible city dropdown).
(() => {
  'use strict';
  const svg = document.getElementById('ncrOutlineMap');
  if (!svg) return;
  const host = document.getElementById('ncrCityTargets');
  const form = document.getElementById('cityExplorerForm');
  const chooser = document.getElementById('mapCitySelect');
  const fuel = document.getElementById('mapFuelSelect');
  if (!host || !form || !chooser) return;
  const selected = chooser.value;
  const valid = new Set(Array.from(chooser.options, option => option.value));
  const SVG_NS = 'http://www.w3.org/2000/svg';
  // Hit zones align with city labels in the locally stored NCR reference diagram (850 x 1093).
  // Their purpose is city selection, not geographic calculation or station geolocation.
  const zones = [
    ['Caloocan City', 378, 57, 197, 63],
    ['Valenzuela City', 196, 175, 201, 58],
    ['Navotas City', 53, 247, 158, 54],
    ['Malabon City', 212, 274, 165, 55],
    ['Quezon City', 429, 228, 146, 68],
    ['Marikina City', 560, 333, 151, 55],
    ['Manila City', 259, 448, 155, 63],
    ['San Juan City', 393, 412, 113, 83],
    ['Mandaluyong City', 343, 488, 218, 55],
    ['Pasig City', 506, 533, 111, 51],
    ['Makati City', 357, 558, 137, 58],
    ['Pateros', 507, 585, 143, 56],
    ['Pasay City', 276, 609, 103, 79],
    ['Taguig City', 414, 640, 173, 59],
    ['Parañaque City', 269, 734, 190, 51],
    ['Las Piñas City', 275, 836, 145, 62],
    ['Muntinlupa City', 380, 898, 202, 61]
  ];
  function node(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k, String(v)));
    return el;
  }
  function showCity(city) {
    if (!valid.has(city)) return;
    chooser.value = city;
    if (typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.submit();
  }
  zones.forEach(([city,x,y,w,h]) => {
    if (!valid.has(city)) return;
    const active = city === selected;
    const group = node('g', {
      'class': 'ncr-click-area' + (active ? ' is-selected' : ''),
      'role': 'button', 'tabindex': '0',
      'aria-label': `View ${city} fuel prices`,
      'data-city': city
    });
    // Transparent visual overlay with soft red selected/hover outline.
    const box = node('rect', { x, y, width:w, height:h, rx:13, class:'ncr-click-zone' });
    group.appendChild(box);
    // An unobtrusive red indicator just outside the selected city name.
    if (active) {
      const marker = node('circle', { cx:x + 9, cy:y + 8, r:8, class:'ncr-selected-pin' });
      group.appendChild(marker);
    }
    const title = node('title');
    title.textContent = 'Select ' + city;
    group.appendChild(title);
    group.addEventListener('click', () => showCity(city));
    group.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        showCity(city);
      }
    });
    host.appendChild(group);
  });
  chooser.addEventListener('change', () => form.requestSubmit ? form.requestSubmit() : form.submit());
  fuel?.addEventListener('change', () => form.requestSubmit ? form.requestSubmit() : form.submit());
})();
