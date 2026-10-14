/* ============================================================
   Каталог buy/ и rent/ — прогрессивное улучшение пре-рендеренных карточек.
   Фильтры/сортировка работают по data-* карточек в DOM (без data.js),
   состояние — только в #hash (#d=becici&pmin=150&sort=price-asc), индексируемых URL нет.
   Строки — из SITE.t('catalog.*'); числа/цены — SITE.util.
   ============================================================ */
(function () {
  'use strict';

  var SITE = window.SITE || {};
  var t = function (key, vars) { return SITE.t ? SITE.t(key, vars) : key; };
  var U = SITE.util || {};
  var doc = document;

  function onReady(fn) {
    if (doc.readyState !== 'loading') fn();
    else doc.addEventListener('DOMContentLoaded', fn);
  }

  /* ---------------- hash state ---------------- */
  var KEYS = ['cat', 'd', 'pmin', 'pmax', 'amin', 'amax', 'beds', 'term', 'sort'];

  function readHash() {
    var raw = (location.hash || '').replace(/^#/, '');
    var state = {};
    if (raw === 'short-term') { state.tab = 'short'; return state; }
    if (raw.indexOf('=') < 0) return null; // обычный якорь (#request, #main) — не состояние
    raw.split('&').forEach(function (pair) {
      var i = pair.indexOf('=');
      if (i < 1) return;
      var k = decodeURIComponent(pair.slice(0, i));
      var v = decodeURIComponent(pair.slice(i + 1));
      if ((KEYS.indexOf(k) >= 0 || k === 'tab') && v) state[k] = v;
    });
    return state;
  }

  function writeHash(state) {
    var parts = [];
    KEYS.concat(['tab']).forEach(function (k) {
      if (state[k]) parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(state[k]));
    });
    var url = location.pathname + location.search + (parts.length ? '#' + parts.join('&') : '');
    if (url !== location.pathname + location.search + location.hash) {
      try { history.replaceState(null, '', url); } catch (e) { /* file:// и т.п. */ }
    }
  }

  function num(v) {
    var n = parseFloat(String(v == null ? '' : v).replace(/[^\d.]/g, ''));
    return isFinite(n) ? n : null;
  }

  /* ---------------- rent tabs ---------------- */
  function initRentTabs(onChange) {
    var list = doc.querySelector('[data-rent-tabs]');
    if (!list) return null;
    var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
    var panels = tabs.map(function (tab) { return doc.getElementById(tab.getAttribute('aria-controls')); });

    function select(index, focus, silent) {
      tabs.forEach(function (tab, i) {
        var on = i === index;
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
        tab.tabIndex = on ? 0 : -1;
        if (panels[i]) panels[i].classList.toggle('is-inactive', !on);
      });
      if (focus) tabs[index].focus();
      if (onChange && !silent) onChange(index === 1 ? 'short' : '');
    }

    tabs.forEach(function (tab, i) {
      tab.addEventListener('click', function () { select(i, false); });
      tab.addEventListener('keydown', function (e) {
        var dir = SITE.dir === 'rtl' ? -1 : 1;
        var next = null;
        if (e.key === 'ArrowRight') next = (i + dir + tabs.length) % tabs.length;
        if (e.key === 'ArrowLeft') next = (i - dir + tabs.length) % tabs.length;
        if (e.key === 'Home') next = 0;
        if (e.key === 'End') next = tabs.length - 1;
        if (next !== null) { e.preventDefault(); select(next, true); }
      });
    });
    var back = doc.querySelector('[data-rent-back]');
    if (back) back.addEventListener('click', function () { select(0, true); });
    select(0, false, true);
    return { select: select };
  }

  /* ---------------- ID search ---------------- */
  function initIdSearch(cards) {
    var box = doc.querySelector('[data-id-search]');
    if (!box) return;
    var toggle = box.querySelector('.id-search-toggle');
    var panel = box.querySelector('.id-search-panel');
    var input = panel.querySelector('input');
    var results = panel.querySelector('.id-search-results');
    var index = cards.filter(function (c) { return c.dataset.objectId; }).map(function (c) {
      var link = c.querySelector('.card-title a');
      return { id: c.dataset.objectId, norm: normalize(c.dataset.objectId), href: link ? link.getAttribute('href') : '#', name: link ? link.textContent.trim() : '' };
    });

    // ID набирают и кириллицей («СТ» вместо «CT») — сравниваем по форме букв
    function normalize(v) {
      return String(v || '').toUpperCase()
        .replace(/[СC]/g, 'C').replace(/Т/g, 'T').replace(/В/g, 'B').replace(/Р/g, 'P').replace(/К/g, 'K')
        .replace(/Н/g, 'H').replace(/А/g, 'A').replace(/Е/g, 'E').replace(/М/g, 'M').replace(/О/g, 'O').replace(/Х/g, 'X')
        .replace(/[^A-Z0-9]/g, '');
    }
    function format(v) {
      var raw = normalize(v).slice(0, 8);
      if (raw.length <= 2) return raw + (raw.length === 2 && /[-\s]$/.test(v) ? '-' : '');
      if (raw.length <= 4) return raw.slice(0, 2) + '-' + raw.slice(2);
      return raw.slice(0, 2) + '-' + raw.slice(2, 4) + '-' + raw.slice(4);
    }
    function matches() {
      var q = normalize(input.value);
      if (!q) return [];
      return index.filter(function (x) { return x.norm.indexOf(q) === 0; }).slice(0, 7);
    }
    function render() {
      var list = matches();
      results.textContent = '';
      if (!input.value) return;
      if (!list.length) {
        var li = doc.createElement('li');
        li.className = 'id-search-empty';
        li.textContent = t('catalog.id_empty');
        results.appendChild(li);
        return;
      }
      list.forEach(function (x) {
        var li = doc.createElement('li');
        var a = doc.createElement('a');
        a.className = 'id-search-result';
        a.href = x.href;
        var b = doc.createElement('b');
        b.textContent = x.id;
        var s = doc.createElement('span');
        s.textContent = x.name;
        a.appendChild(b);
        a.appendChild(s);
        li.appendChild(a);
        results.appendChild(li);
      });
    }
    function setOpen(open) {
      panel.hidden = !open;
      box.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) setTimeout(function () { input.focus(); }, 30);
      else { input.value = ''; results.textContent = ''; }
    }
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(panel.hidden);
    });
    input.addEventListener('input', function () {
      var before = input.value;
      input.value = format(before);
      render();
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { setOpen(false); toggle.focus(); }
      if (e.key === 'Enter') {
        e.preventDefault();
        var first = matches()[0];
        if (first) location.href = first.href;
      }
      if (e.key === 'ArrowDown') {
        var link = results.querySelector('a');
        if (link) { e.preventDefault(); link.focus(); }
      }
    });
    results.addEventListener('keydown', function (e) {
      var links = Array.prototype.slice.call(results.querySelectorAll('a'));
      var i = links.indexOf(doc.activeElement);
      if (e.key === 'ArrowDown' && i < links.length - 1) { e.preventDefault(); links[i + 1].focus(); }
      if (e.key === 'ArrowUp') { e.preventDefault(); (i > 0 ? links[i - 1] : input).focus(); }
      if (e.key === 'Escape') { setOpen(false); toggle.focus(); }
    });
    doc.addEventListener('click', function (e) { if (!box.contains(e.target) && !panel.hidden) setOpen(false); });
  }

  /* ---------------- main ---------------- */
  onReady(function () {
    var form = doc.getElementById('catalog-filters');
    var grid = doc.getElementById('catalog-grid');
    var countEl = doc.getElementById('catalog-count');
    var empty = doc.getElementById('catalog-empty');
    var resetBtns = Array.prototype.slice.call(doc.querySelectorAll('[data-reset]'));
    var cards = grid ? Array.prototype.slice.call(grid.querySelectorAll('.card')) : [];
    cards.forEach(function (c, i) { c.dataset.order = i; });

    var f = null;
    var tabs = initRentTabs(function (tab) {
      var st = f ? currentState() : {};
      st.tab = tab;
      writeHash(st);
    });

    var initial = readHash() || {};
    if (tabs && initial.tab === 'short') tabs.select(1, false, true);

    if (!form) return;
    var unit = Number(form.dataset.priceUnit) || 1;
    f = {
      cat: form.querySelector('[name="cat"]'),
      d: form.querySelector('[name="d"]'),
      pmin: form.querySelector('[name="pmin"]'),
      pmax: form.querySelector('[name="pmax"]'),
      amin: form.querySelector('[name="amin"]'),
      amax: form.querySelector('[name="amax"]'),
      beds: form.querySelector('[name="beds"]'),
      term: form.querySelector('[name="term"]')
    };
    var sortBtns = Array.prototype.slice.call(form.querySelectorAll('[data-sort]'));
    var sort = '';
    var toggle = form.querySelector('[data-filters-toggle]');
    var toggleLabel = form.querySelector('[data-filters-toggle-label]');

    /* --- поле цены (покупка): «000» в поле + ползунок --- */
    var price = initPrice(form, unit);

    function currentState() {
      var st = {};
      ['cat', 'd', 'beds', 'term'].forEach(function (k) { if (f[k] && f[k].value) st[k] = f[k].value; });
      ['pmin', 'pmax', 'amin', 'amax'].forEach(function (k) {
        var v = f[k] ? num(f[k].value) : null;
        if (v !== null && v > 0) st[k] = String(v);
      });
      if (sort) st.sort = sort;
      return st;
    }

    function passes(card, st, skip) {
      var ds = card.dataset;
      if (st.cat && skip !== 'cat' && ds.category !== st.cat) return false;
      if (st.d && skip !== 'd' && ds.district !== st.d) return false;
      var p = Number(ds.price) || 0;
      if ((st.pmin || st.pmax) && !p) return false;
      if (st.pmin && p < Number(st.pmin) * unit) return false;
      if (st.pmax && p > Number(st.pmax) * unit) return false;
      var a = num(ds.area);
      if ((st.amin || st.amax) && a === null) return false;
      if (st.amin && a < Number(st.amin)) return false;
      if (st.amax && a > Number(st.amax)) return false;
      if (st.beds && !((Number(ds.bedrooms) || 0) >= Number(st.beds))) return false;
      if (st.term && (' ' + (ds.terms || '') + ' ').indexOf(' ' + st.term + ' ') < 0) return false;
      return true;
    }

    function sortKey(card) {
      var p = Number(card.dataset.price) || 0;
      var a = num(card.dataset.area) || 0;
      if (sort === 'price-asc') return p ? p : Infinity;
      if (sort === 'price-desc') return p ? -p : Infinity;
      if (sort === 'area-desc') return a ? -a : Infinity;
      return 0;
    }

    function updateDistricts(st) {
      if (!f.d) return;
      Array.prototype.forEach.call(f.d.options, function (opt) {
        if (!opt.value) return;
        var n = cards.filter(function (c) { return c.dataset.district === opt.value && passes(c, st, 'd'); }).length;
        var name = opt.getAttribute('data-name') || opt.textContent;
        opt.textContent = t(n ? 'catalog.district_option' : 'catalog.district_option_none', { name: name, n: n });
        opt.disabled = !n && opt.value !== st.d;
      });
    }

    function apply(opts) {
      opts = opts || {};
      var st = currentState();
      var shown = 0;
      var ordered = cards.slice().sort(function (x, y) {
        var kx = sortKey(x), ky = sortKey(y);
        if (kx !== ky) return kx < ky ? -1 : 1;
        return x.dataset.order - y.dataset.order;
      });
      ordered.forEach(function (card) {
        var ok = passes(card, st);
        card.hidden = !ok;
        if (ok) shown++;
        grid.appendChild(card);
      });
      if (countEl) countEl.textContent = t('catalog.count', { n: shown });
      if (empty) empty.hidden = shown > 0;
      grid.hidden = shown === 0;
      var active = Object.keys(st).filter(function (k) { return k !== 'sort'; }).length;
      resetBtns.forEach(function (b) { if (!b.closest('.catalog-empty')) b.hidden = !active && !sort; });
      if (toggleLabel) toggleLabel.textContent = active ? t('catalog.filters_active', { n: active }) : toggleLabel.dataset.label;
      updateDistricts(st);
      if (!opts.silent) {
        st.tab = tabs && doc.getElementById('rent-tab-short') && doc.getElementById('rent-tab-short').getAttribute('aria-selected') === 'true' ? 'short' : '';
        writeHash(st);
      }
    }
    if (toggleLabel) toggleLabel.dataset.label = toggleLabel.textContent;

    /* --- восстановить состояние из hash --- */
    function restore(st) {
      ['cat', 'd', 'beds', 'term'].forEach(function (k) {
        if (!f[k]) return;
        var v = st[k] || '';
        if (v && !Array.prototype.some.call(f[k].options, function (o) { return o.value === v; })) v = '';
        f[k].value = v;
      });
      ['pmin', 'pmax', 'amin', 'amax'].forEach(function (k) { if (f[k]) f[k].value = st[k] || ''; });
      sort = ['price-asc', 'price-desc', 'area-desc'].indexOf(st.sort) >= 0 ? st.sort : '';
      sortBtns.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.sort === sort ? 'true' : 'false'); });
      if (price) price.sync();
    }
    restore(initial);

    var applyDebounced = U.debounce ? U.debounce(apply, 180) : apply;
    // поиск по ID живёт внутри этой же формы, но к фильтрам не относится:
    // его поле не чистим до цифр и не пересчитываем выдачу на каждый символ
    function fromIdSearch(e) { return !!(e.target.closest && e.target.closest('[data-id-search]')); }
    form.addEventListener('change', function (e) { if (!fromIdSearch(e)) apply(); });
    form.addEventListener('input', function (e) {
      if (fromIdSearch(e)) return;
      if (e.target.matches('input[type="text"]')) {
        e.target.value = e.target.value.replace(/[^\d]/g, '').slice(0, 7);
        applyDebounced();
      }
    });
    form.addEventListener('submit', function (e) { e.preventDefault(); apply(); });
    sortBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        sort = sort === btn.dataset.sort ? '' : btn.dataset.sort;
        sortBtns.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.sort === sort ? 'true' : 'false'); });
        apply();
      });
    });
    resetBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        restore({});
        apply();
        var first = form.querySelector('select, input');
        if (btn.closest('.catalog-empty') && first) first.focus();
      });
    });
    if (price) price.onChange = applyDebounced;

    if (toggle) {
      toggle.addEventListener('click', function () {
        var open = !form.classList.contains('is-open');
        form.classList.toggle('is-open', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }

    window.addEventListener('hashchange', function () {
      var st = readHash();
      if (!st) return;
      if (tabs) tabs.select(st.tab === 'short' ? 1 : 0, false, true);
      restore(st);
      apply({ silent: true });
    });

    initIdSearch(cards);
    apply({ silent: true });
  });

  /* ---------------- цена: «000» + ползунок (только покупка) ---------------- */
  function initPrice(form, unit) {
    var field = form.querySelector('[data-price-field]');
    if (!field) return null;
    var MAX_K = 1000;
    var fMin = field.querySelector('[name="pmin"]');
    var fMax = field.querySelector('[name="pmax"]');
    var sMin = field.querySelector('[data-ps-min]');
    var sMax = field.querySelector('[data-ps-max]');
    var fill = field.querySelector('[data-ps-fill]');
    var caption = field.querySelector('[data-price-caption]');
    var slider = field.querySelector('[data-price-slider]');
    var toggle = field.querySelector('[data-slider-toggle]');
    var api = { onChange: null, sync: sync };
    var fmt = function (k) { return U.formatPrice ? U.formatPrice(k * unit) : '€' + k * unit; };

    function autoWidth(inp) {
      // цифры ≈ 1ch; буквы плейсхолдера («max», «макс») шире — запас +1ch, иначе текст обрезается
      var len = inp.value ? inp.value.length : (inp.placeholder || '').length + 1;
      inp.style.inlineSize = Math.min(8, Math.max(1, len)) + 'ch';
    }

    function sync() {
      var minK = num(fMin.value) || 0;
      var maxRaw = num(fMax.value);
      var noMax = !maxRaw;
      var cMin = Math.max(0, Math.min(MAX_K, minK));
      var cMax = noMax ? MAX_K : Math.max(0, Math.min(MAX_K, maxRaw));
      sMin.value = cMin;
      sMax.value = cMax;
      // ползунок всегда LTR (direction: ltr в CSS) — физические left/width корректны и в иврите
      fill.style.left = (cMin / MAX_K * 100) + '%';
      fill.style.width = (Math.max(0, cMax - cMin) / MAX_K * 100) + '%';
      var text;
      if (!minK && noMax) text = t('catalog.price_any');
      else if (minK && noMax) text = t('catalog.price_from', { min: fmt(minK) });
      else if (!minK) text = t('catalog.price_to', { max: fmt(maxRaw) });
      else text = t('catalog.price_range', { min: fmt(minK), max: fmt(maxRaw) });
      if (caption) caption.textContent = '— ' + text;
      fMin.parentNode.classList.toggle('empty', !fMin.value);
      fMax.parentNode.classList.toggle('empty', !fMax.value);
      autoWidth(fMin);
      autoWidth(fMax);
    }

    function fromSlider() {
      var a = Number(sMin.value), b = Number(sMax.value);
      if (a > b) { var tmp = a; a = b; b = tmp; }
      fMin.value = a > 0 ? a : '';
      fMax.value = b >= MAX_K ? '' : b;
      sync();
      if (api.onChange) api.onChange();
    }
    sMin.addEventListener('input', fromSlider);
    sMax.addEventListener('input', fromSlider);
    fMin.addEventListener('input', sync);
    fMax.addEventListener('input', sync);

    function setOpen(open) {
      slider.classList.toggle('open', open);
      toggle.classList.toggle('active', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(!slider.classList.contains('open'));
    });
    document.addEventListener('click', function (e) {
      if (slider.classList.contains('open') && !slider.contains(e.target) && !toggle.contains(e.target)) setOpen(false);
    });
    slider.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { setOpen(false); toggle.focus(); }
    });
    sync();
    return api;
  }
})();
