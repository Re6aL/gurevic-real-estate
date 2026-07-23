// ============================================================
// Gurevic Real Estate — страница карты (map.html)
// Leaflet + OSM: маркеры-ценники, панель мини-карточек,
// переключение Карта/Список (в духе findrealestate.com)
// ============================================================

(function () {
  const mapEl = document.getElementById('map');
  if (!mapEl || typeof L === 'undefined') return;

  let typeFilter = '';
  const items = () => LISTINGS.filter(l => !typeFilter || l.type === typeFilter);

  // цена коротко для маркера: €145k / €1.2M / — (по запросу)
  function fmtShort(l) {
    if (!l.price) return '···';
    if (l.price >= 1e6) return '€' + (l.price / 1e6).toFixed(1).replace('.0', '') + 'M';
    return '€' + Math.round(l.price / 1000) + 'k';
  }

  const map = L.map('map', { scrollWheelZoom: true }).setView([42.2864, 18.856], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 19,
  }).addTo(map);

  let markers = [];

  function popupHTML(l) {
    return `
      <div style="min-width:180px">
        <b style="color:var(--navy)">${fmtPrice(l)}</b><br>
        ${l.title}<br>
        <span style="color:#6b7a89;font-size:.85em">📍 ${l.location}</span><br>
        <a href="object.html?id=${l.id}">Смотреть объект →</a>
      </div>`;
  }

  function miniCardHTML(l) {
    const params = [];
    if (l.area) params.push(`${l.areaNote || l.area + ' м²'}`);
    if (l.landArea) params.push(`уч. ${l.landArea} м²`);
    if (l.rooms) params.push(l.rooms);
    return `
      <div class="mini-card" data-id="${l.id}">
        <div class="ph" style="--h:${l.hue}"><span>📷</span></div>
        <div class="mc-body">
          <div class="mc-price">${fmtPrice(l)}</div>
          <div class="mc-title">${l.title}</div>
          <div class="mc-loc">📍 ${l.location}</div>
          <div class="mc-params">${params.join(' · ')}</div>
        </div>
      </div>`;
  }

  function render() {
    const list = items();
    document.getElementById('map-count').textContent = `объектов: ${list.length}`;

    // маркеры
    markers.forEach(m => map.removeLayer(m));
    markers = [];
    const bounds = [];
    list.forEach(l => {
      const c = objCoords(l);
      if (!c) return;
      const icon = L.divIcon({
        className: '',
        html: `<span class="price-pin ${l.invest ? 'invest' : ''}" data-id="${l.id}">${fmtShort(l)}</span>`,
        iconSize: [0, 0],
      });
      const m = L.marker(c, { icon }).addTo(map).bindPopup(popupHTML(l));
      m._lid = l.id;
      markers.push(m);
      bounds.push(c);
    });
    if (bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });

    // панель мини-карточек (клик — перелёт к маркеру, дабл-клик — на объект)
    const panel = document.getElementById('map-list');
    panel.innerHTML = list.map(miniCardHTML).join('') ||
      '<div class="empty-state">Нет объектов этого типа</div>';
    panel.querySelectorAll('.mini-card').forEach(card => {
      card.addEventListener('click', () => {
        const m = markers.find(x => x._lid === card.dataset.id);
        if (m) { map.setView(m.getLatLng(), 15); m.openPopup(); }
        panel.querySelectorAll('.mini-card').forEach(x => x.classList.toggle('hot', x === card));
      });
      card.addEventListener('dblclick', () => location.href = 'object.html?id=' + card.dataset.id);
    });

    // режим «Список» — обычные большие карточки
    document.getElementById('list-view').innerHTML = list.map(cardHTML).join('');
  }

  // фильтр типов
  document.querySelectorAll('.map-deal-tabs .deal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.map-deal-tabs .deal-tab').forEach(t => t.classList.toggle('active', t === tab));
      typeFilter = tab.dataset.mtype;
      render();
    });
  });

  // переключение Карта / Список
  const vtMap = document.getElementById('vt-map');
  const vtList = document.getElementById('vt-list');
  function setView(mode) {
    vtMap.classList.toggle('active', mode === 'map');
    vtList.classList.toggle('active', mode === 'list');
    document.getElementById('map-view').style.display = mode === 'map' ? '' : 'none';
    document.getElementById('list-view').hidden = mode !== 'list';
    if (mode === 'map') setTimeout(() => map.invalidateSize(), 50);
  }
  vtMap.addEventListener('click', () => setView('map'));
  vtList.addEventListener('click', () => setView('list'));

  render();
})();
