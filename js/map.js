/* ============================================================
   Карта объектов (map/): Leaflet 1.9.4 + OpenStreetMap.
   Данные — инлайн JSON #map-data (собирает pages/map.html из listings; без конфиденциальных).
   Маркеры-ценники; «approx» (центр района) — пунктиром и с небольшим разнесением,
   чтобы объекты одного района не слипались. Фильтр раздела, список ↔ карта на мобильных.
   Строки — SITE.t('map.*').
   ============================================================ */
(function () {
  'use strict';

  var SITE = window.SITE || {};
  var doc = document;
  var t = function (key, vars) { return SITE.t ? SITE.t(key, vars) : key; };

  function onReady(fn) {
    if (doc.readyState !== 'loading') fn();
    else doc.addEventListener('DOMContentLoaded', fn);
  }

  function readData() {
    var el = doc.getElementById('map-data');
    if (!el) return [];
    try { return JSON.parse(el.textContent) || []; } catch (e) { return []; }
  }

  // Короткая цена для маркера: «213 тыс. €» / «€213K»; по запросу — «•••»
  var compact = null;
  try {
    compact = new Intl.NumberFormat(SITE.lang || 'en', { style: 'currency', currency: 'EUR', notation: 'compact', maximumFractionDigits: 1 });
  } catch (e) { compact = null; }
  function shortPrice(item) {
    if (!item.value) return '•••';
    return compact ? compact.format(item.value) : item.price;
  }

  onReady(function () {
    var items = readData();
    var wrap = doc.querySelector('[data-map-wrap]');
    var mapEl = doc.querySelector('[data-map]');
    var list = doc.querySelector('[data-map-list]');
    var countEl = doc.querySelector('[data-map-count]');
    var emptyEl = doc.querySelector('[data-map-empty]');
    var filter = doc.querySelector('[data-map-filter]');
    var viewBox = doc.querySelector('[data-map-view]');
    var cards = list ? Array.prototype.slice.call(list.querySelectorAll('.mini-card')) : [];
    var section = '';
    if (filter) filter.hidden = false;
    if (viewBox) viewBox.hidden = false;

    /* --- вид: список / карта (мобильные) --- */
    var map = null;
    function setView(view) {
      wrap.setAttribute('data-view', view);
      Array.prototype.forEach.call(viewBox.querySelectorAll('[data-view]'), function (b) {
        b.setAttribute('aria-pressed', b.getAttribute('data-view') === view ? 'true' : 'false');
      });
      if (view === 'map' && map) setTimeout(function () { map.invalidateSize(); fit(); }, 30);
    }
    if (viewBox) {
      viewBox.addEventListener('click', function (e) {
        var b = e.target.closest('[data-view]');
        if (b) setView(b.getAttribute('data-view'));
      });
    }

    /* --- карта --- */
    var markers = {};
    var layer = null;
    if (typeof window.L === 'undefined') {
      var err = doc.createElement('p');
      err.className = 'map-error';
      err.textContent = t('map.load_error');
      mapEl.appendChild(err);
    } else {
      var L = window.L;
      map = L.map(mapEl, { scrollWheelZoom: false, zoomControl: false, tap: true }).setView([42.2864, 18.856], 12);
      L.control.zoom({ zoomInTitle: t('map.zoom_in'), zoomOutTitle: t('map.zoom_out'), position: SITE.dir === 'rtl' ? 'topright' : 'topleft' }).addTo(map);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19
      }).addTo(map);
      // колесо мыши — только после клика по карте (не «ловить» прокрутку страницы)
      map.once('focus', function () { map.scrollWheelZoom.enable(); });
      layer = L.layerGroup().addTo(map);

      // разнесение приблизительных точек одного района по небольшой спирали
      var groups = {};
      items.forEach(function (it) {
        var key = it.lat.toFixed(4) + ',' + it.lng.toFixed(4);
        var n = groups[key] = (groups[key] || 0) + 1;
        it._lat = it.lat; it._lng = it.lng;
        if (it.approx && n > 1) {
          var angle = n * 2.4, r = 0.0016 * Math.sqrt(n);
          it._lat = it.lat + r * Math.sin(angle);
          it._lng = it.lng + r * Math.cos(angle) * 1.35;
        }
      });

      items.forEach(function (it) {
        var cls = 'price-pin' + (it.approx ? ' price-pin--approx' : '') + (it.section === 'invest' ? ' price-pin--invest' : '');
        var icon = L.divIcon({ className: 'pin-wrap', html: '<span class="' + cls + '"></span>', iconSize: [0, 0] });
        var m = L.marker([it._lat, it._lng], { icon: icon, title: it.title, alt: it.title, keyboard: true, riseOnHover: true });
        m.bindPopup(function () { return popup(it); }, { maxWidth: 260, minWidth: 240, autoPanPadding: [24, 24] });
        m.on('add', function () {
          var el = m.getElement();
          if (el) el.querySelector('.price-pin').textContent = shortPrice(it);
        });
        m.on('mouseover', function () { hot(it.id, true); });
        m.on('mouseout', function () { hot(it.id, false); });
        markers[it.id] = { marker: m, item: it };
      });
    }

    function popup(it) {
      var box = doc.createElement('div');
      box.className = 'map-pop';
      box.setAttribute('dir', SITE.dir || 'ltr');
      if (it.thumb) {
        var img = doc.createElement('img');
        img.src = it.thumb;
        img.alt = '';
        img.loading = 'lazy';
        box.appendChild(img);
      }
      var body = doc.createElement('div');
      body.className = 'map-pop__body';
      [['map-pop__price', it.price], ['map-pop__title', it.title], ['map-pop__loc', it.district]].forEach(function (row) {
        var p = doc.createElement('p');
        p.className = row[0];
        var bdi = doc.createElement('bdi');
        bdi.textContent = row[1];
        p.appendChild(bdi);
        body.appendChild(p);
      });
      if (it.approx) {
        var ap = doc.createElement('p');
        ap.className = 'map-pop__approx';
        ap.textContent = t('map.approx');
        body.appendChild(ap);
      }
      var a = doc.createElement('a');
      a.className = 'map-pop__link';
      a.href = it.url;
      a.textContent = t('map.details');
      body.appendChild(a);
      box.appendChild(body);
      return box;
    }

    function hot(id, on) {
      cards.forEach(function (c) { if (c.getAttribute('data-id') === id) c.classList.toggle('is-hot', on); });
      var rec = markers[id];
      var el = rec && rec.marker.getElement();
      if (el) el.querySelector('.price-pin').classList.toggle('is-hot', on);
    }

    function visible() {
      return items.filter(function (it) { return !section || it.section === section; });
    }

    function fit() {
      if (!map) return;
      var pts = visible().map(function (it) { return [it._lat, it._lng]; });
      if (pts.length === 1) map.setView(pts[0], 14);
      else if (pts.length) map.fitBounds(pts, { padding: [40, 40], maxZoom: 14 });
    }

    function apply() {
      var shown = visible();
      var ids = {};
      shown.forEach(function (it) { ids[it.id] = true; });
      cards.forEach(function (c) { c.classList.toggle('is-hidden', !ids[c.getAttribute('data-id')]); });
      if (emptyEl) emptyEl.hidden = shown.length > 0;
      if (countEl) countEl.textContent = t('map.count', { n: shown.length });
      if (layer) {
        layer.clearLayers();
        shown.forEach(function (it) { layer.addLayer(markers[it.id].marker); });
        fit();
      }
    }

    if (filter) {
      filter.addEventListener('click', function (e) {
        var b = e.target.closest('[data-section]');
        if (!b || b.disabled) return;
        section = b.getAttribute('data-section');
        Array.prototype.forEach.call(filter.querySelectorAll('[data-section]'), function (x) {
          x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
        });
        apply();
      });
    }

    cards.forEach(function (card) {
      var id = card.getAttribute('data-id');
      card.addEventListener('mouseenter', function () { hot(id, true); });
      card.addEventListener('mouseleave', function () { hot(id, false); });
      var btn = card.querySelector('[data-locate]');
      if (!btn || !markers[id]) return;
      btn.hidden = false;
      btn.addEventListener('click', function () {
        if (viewBox && getComputedStyle(viewBox).display !== 'none') setView('map');
        var rec = markers[id];
        setTimeout(function () {
          map.setView(rec.marker.getLatLng(), Math.max(map.getZoom(), 15));
          rec.marker.openPopup();
        }, 60);
      });
    });

    apply();
  });
})();
