// ============================================================
// Gurevic Real Estate — рендер карточек и фильтры
// ============================================================

function fmtPrice(l) {
  if (l.priceNote) return l.priceNote;
  const p = '€' + l.price.toLocaleString('ru-RU').replace(/,/g, ' ');
  return l.deal === 'rent' ? p + ' / мес' : p;
}

function paramsLine(l) {
  const parts = [];
  if (l.area) parts.push(`<span>📐 ${l.areaNote || l.area + ' м²'}</span>`);
  if (l.landArea) parts.push(`<span>🌿 участок ${l.landArea} м²</span>`);
  if (l.rooms) parts.push(`<span>🛏 ${l.rooms}</span>`);
  return parts.join('');
}

// Плейсхолдер фото: градиент с подписью, hue задаёт «палитру» объекта
function ph(hue, label, cls = '') {
  return `<div class="ph ${cls}" style="--h:${hue}"><span>📷 ${label}</span></div>`;
}

// Реальное фото из синхронизации Notion; при его отсутствии остаётся заглушка.
const LISTING_PLACEHOLDERS = {
  apartment: 'img/placeholders/apartment.png',
  house: 'img/placeholders/house.png',
  land: 'img/placeholders/land.png',
  commercial: 'img/placeholders/complex.png',
  hotel: 'img/placeholders/complex.png',
};

function listingPlaceholderImage(l) {
  return LISTING_PLACEHOLDERS[l.type] || LISTING_PLACEHOLDERS.apartment;
}

function listingImageHTML(l, cls = '', alt = 'Фото объекта') {
  const src = Array.isArray(l.images) && l.images[0];
  return src
    ? `<img class="listing-image ${cls}" src="${src}" alt="${alt}" loading="lazy">`
    : `<img class="listing-image ${cls} listing-illustration" src="${listingPlaceholderImage(l)}" alt="Иллюстрация: ${DICT.type[l.type] || 'объект недвижимости'}" loading="lazy">`;
}

function isComplexListing(l) {
  return Boolean(l.isComplex || l.investKind === 'Девелопмент');
}

function cardHTML(l) {
  const badges = [`<span class="badge ${l.deal === 'rent' ? 'deal-rent' : ''}">${DICT.deal[l.deal]}</span>`];
  if (isComplexListing(l)) badges.push('<span class="badge invest">Комплекс</span>');
  if (l.invest) badges.push(`<span class="badge invest">${l.investKind}</span>`);
  if (l.placeholder) badges.push('<span class="badge demo">Демо-объект</span>');
  return `
  <article class="card">
    <a href="object.html?id=${l.id}" style="position:relative; display:block;">
      <div class="badge-row">${badges.join('')}</div>
      ${listingImageHTML(l, 'card-image')}
    </a>
    <div class="card-body">
      <div class="card-price">${fmtPrice(l)}</div>
      <div class="card-title">${l.title}</div>
      <div class="card-loc">${l.location}</div>
      <div class="card-params">${paramsLine(l)}</div>
      <div class="card-short">${l.short}</div>
      <div class="card-actions"><a class="btn btn-navy" href="object.html?id=${l.id}">Подробнее</a></div>
    </div>
  </article>`;
}

// ---------- главная страница ----------
const state = { deal: 'sale', type: '', location: '', priceMin: '', priceMax: '', areaMin: '', areaMax: '', sort: '' };

function applyFilters() {
  // комплексы вынесены в отдельный блок «Жилые комплексы», инвестиции — в свой
  let items = LISTINGS.filter(l => !l.invest && !isComplexListing(l));
  if (state.deal) items = items.filter(l => l.deal === state.deal);
  if (state.type) items = items.filter(l => l.type === state.type);
  if (state.location) items = items.filter(l => l.location === state.location);
  // цена вводится в тысячах € → умножаем на 1000
  if (state.priceMin) items = items.filter(l => l.price >= +state.priceMin * 1000);
  if (state.priceMax) items = items.filter(l => l.price <= +state.priceMax * 1000);
  if (state.areaMin) items = items.filter(l => (l.area || 0) >= +state.areaMin);
  if (state.areaMax) items = items.filter(l => (l.area || 0) <= +state.areaMax);
  // объекты «цена по запросу» (price 0) — всегда в конце
  if (state.sort === 'price-asc') items.sort((a, b) => (a.price || Infinity) - (b.price || Infinity));
  if (state.sort === 'price-desc') items.sort((a, b) => (b.price || 0) - (a.price || 0));
  return items;
}

function renderListings() {
  const grid = document.getElementById('listings');
  if (!grid) return;
  const items = applyFilters();
  document.getElementById('listings-count').textContent =
    items.length ? `объектов: ${items.length}` : '';
  grid.innerHTML = items.length
    ? items.map(cardHTML).join('')
    : '<div class="empty-state">По выбранным условиям объектов нет.<br>Сбросьте фильтры или напишите нам в чат — подберём вручную.</div>';
}

// если раздел пуст (в CRM пока нет таких объектов) — прячем секцию и пункт меню
function hideEmptySection(sectionId, empty) {
  const sec = document.getElementById(sectionId);
  if (sec) sec.style.display = empty ? 'none' : '';
  document.querySelectorAll(`.nav a[href$="#${sectionId}"]`).forEach(a => {
    a.style.display = empty ? 'none' : '';
  });
}

function renderInvest() {
  const grid = document.getElementById('invest-cards');
  if (!grid) return;
  const items = LISTINGS.filter(l => l.invest);
  hideEmptySection('invest', !items.length);
  grid.innerHTML = items.map(l => cardHTML(l).replace(
    '<div class="card-price">',
    `<div class="invest-kind">${l.investKind}</div><div class="card-price">`
  )).join('');
}

function renderComplexes() {
  const grid = document.getElementById('complex-cards');
  if (!grid) return;
  const items = LISTINGS.filter(isComplexListing);
  hideEmptySection('complexes', !items.length);
  grid.innerHTML = items.map(l => {
    const n = (l.units || []).length;
    const avail = (l.units || []).filter(u => u.status === 'available').length;
    const card = cardHTML(l);
    if (!n) return card;
    // добавляем строку «доступно вариантов» перед кнопкой
    return card.replace(
      '<div class="card-actions">',
      `<div class="card-params" style="color:var(--gold-dark);font-weight:700">🏢 вариантов в комплексе: ${n} · свободно: ${avail}</div><div class="card-actions">`
    );
  }).join('');
}

// ---------- герой: слайд-шоу + сглаженный zoom при прокрутке ----------
function initHeroSlideshow() {
  const slides = document.querySelectorAll('.hero-slide');
  if (!slides.length) return;
  let idx = 0;
  slides[0].classList.add('active');
  setInterval(() => {
    const previous = slides[idx];
    previous.classList.remove('active');
    previous.classList.add('leaving');
    idx = (idx + 1) % slides.length;
    slides[idx].classList.add('active');
    window.setTimeout(() => previous.classList.remove('leaving'), 3000);
  }, 12000);

  // Плавно догоняем целевой масштаб, не пересчитывая layout страницы.
  const bg = document.getElementById('hero-bg');
  const hero = document.querySelector('.hero');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let currentScale = 1;
  let targetScale = 1;
  let frame = 0;

  function animateScale() {
    currentScale += (targetScale - currentScale) * 0.12;
    if (Math.abs(targetScale - currentScale) < 0.0005) currentScale = targetScale;
    bg.style.transform = `scale(${currentScale.toFixed(4)})`;
    frame = currentScale === targetScale ? 0 : requestAnimationFrame(animateScale);
  }

  function updateScale() {
    const progress = Math.min(Math.max(window.scrollY / Math.max(hero.offsetHeight, 1), 0), 1);
    targetScale = reduceMotion.matches ? 1 : 1 + progress * 0.08;
    if (!frame) frame = requestAnimationFrame(animateScale);
  }

  window.addEventListener('scroll', updateScale, { passive: true });
  reduceMotion.addEventListener('change', updateScale);
  updateScale();
}

function initFilters() {
  const typeSel = document.getElementById('f-type');
  const locSel = document.getElementById('f-location');
  if (!typeSel) return;

  Object.entries(DICT.type).forEach(([k, v]) => {
    if (k === 'hotel') return; // отели живут в блоке инвестиций
    typeSel.insertAdjacentHTML('beforeend', `<option value="${k}">${v}</option>`);
  });
  // Районы не захардкожены: строим список только из опубликованных объектов.
  // При смене сделки/типа пустые пункты остаются для ориентира, но выбрать их нельзя.
  function updateLocationOptions() {
    const catalogue = LISTINGS.filter(l => !l.invest && !l.isComplex);
    const locations = [...new Set(catalogue.map(l => l.location).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, 'ru'));
    const counts = new Map();
    catalogue
      .filter(l => (!state.deal || l.deal === state.deal) && (!state.type || l.type === state.type))
      .forEach(l => counts.set(l.location, (counts.get(l.location) || 0) + 1));

    locSel.innerHTML = '<option value="">Любой</option>';
    locations.forEach(loc => {
      const count = counts.get(loc) || 0;
      const selected = state.location === loc;
      locSel.insertAdjacentHTML('beforeend',
        `<option value="${loc}"${!count && !selected ? ' disabled' : ''}${selected ? ' selected' : ''}>${loc}${count ? ` · ${count}` : ' · нет предложений'}</option>`
      );
    });
    if (state.location && !locations.includes(state.location)) state.location = '';
  }

  updateLocationOptions();

  // вкладки сделки
  document.querySelectorAll('.deal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      if (tab.dataset.deal === 'invest') {
        document.getElementById('invest').scrollIntoView({ behavior: 'smooth' });
        return;
      }
      document.querySelectorAll('.deal-tab').forEach(t => t.classList.toggle('active', t === tab));
      state.deal = tab.dataset.deal;
      if (!LISTINGS.some(l => !l.invest && !l.isComplex && l.deal === state.deal && (!state.type || l.type === state.type) && l.location === state.location)) state.location = '';
      updateLocationOptions();
      renderListings();
    });
  });

  // селекты и поля от/до
  typeSel.addEventListener('change', () => {
    state.type = typeSel.value;
    if (!LISTINGS.some(l => !l.invest && !l.isComplex && l.deal === state.deal && (!state.type || l.type === state.type) && l.location === state.location)) state.location = '';
    updateLocationOptions();
    renderListings();
  });
  locSel.addEventListener('change', () => { state.location = locSel.value; renderListings(); });
  const bind = (id, key) => document.getElementById(id)
    .addEventListener('input', e => { state[key] = e.target.value; renderListings(); });
  bind('f-area-min', 'areaMin');
  bind('f-area-max', 'areaMax');

  initPriceControl();

  // иконочная сортировка (повторный клик снимает)
  document.querySelectorAll('.sort-icon').forEach(icon => {
    icon.addEventListener('click', () => {
      const v = icon.dataset.sort;
      const already = state.sort === v;
      state.sort = already ? '' : v;
      document.querySelectorAll('.sort-icon').forEach(i => i.classList.toggle('active', !already && i === icon));
      renderListings();
    });
  });

  document.getElementById('btn-apply').addEventListener('click', renderListings);

  // Компактный поиск по внутреннему ID объекта. Поле появляется только по запросу.
  const idSearch = document.getElementById('id-search');
  const idToggle = document.getElementById('id-search-toggle');
  const idInput = document.getElementById('f-object-id');
  const idResults = document.getElementById('id-search-results');
  if (idSearch && idToggle && idInput && idResults) {
    const normalizeId = value => String(value || '').toUpperCase()
      .replace(/[^A-ZА-ЯЁ0-9]/g, '')
      .replace(/[СC]/g, 'C');

    function formatId(value) {
      const raw = normalizeId(value).slice(0, 8);
      if (raw.length < 2) return raw;
      if (raw.length === 2) return `${raw}-`;
      if (raw.length < 4) return `${raw.slice(0, 2)}-${raw.slice(2)}`;
      if (raw.length === 4) return `${raw.slice(0, 2)}-${raw.slice(2, 4)}-`;
      return `${raw.slice(0, 2)}-${raw.slice(2, 4)}-${raw.slice(4)}`;
    }

    function matchingListings() {
      const query = normalizeId(idInput.value);
      if (!query) return [];
      return LISTINGS
        .filter(listing => listing.objectId && normalizeId(listing.objectId).startsWith(query))
        .slice(0, 7);
    }

    function renderIdResults() {
      const matches = matchingListings();
      idResults.innerHTML = matches.length
        ? matches.map(listing => `
          <button type="button" class="id-search-result" role="option" data-listing-id="${listing.id}">
            <b>${listing.objectId}</b><span>${listing.title}</span>
          </button>`).join('')
        : (idInput.value ? '<div class="id-search-empty">Подходящих объектов нет</div>' : '');
    }

    function setSearchOpen(open) {
      idSearch.classList.toggle('open', open);
      idToggle.setAttribute('aria-expanded', String(open));
      if (open) {
        window.setTimeout(() => idInput.focus(), 40);
      } else {
        idInput.value = '';
        idResults.innerHTML = '';
      }
    }

    idToggle.addEventListener('click', event => {
      event.stopPropagation();
      setSearchOpen(!idSearch.classList.contains('open'));
    });
    idInput.addEventListener('input', () => {
      idInput.value = formatId(idInput.value);
      renderIdResults();
    });
    idInput.addEventListener('keydown', event => {
      if (event.key === 'Backspace' && idInput.selectionStart === idInput.selectionEnd) {
        const caret = idInput.selectionStart;
        if (caret > 0 && idInput.value[caret - 1] === '-') {
          event.preventDefault();
          idInput.value = formatId(
            idInput.value.slice(0, Math.max(0, caret - 2)) + idInput.value.slice(caret)
          );
          const nextCaret = Math.max(0, caret - 2);
          idInput.setSelectionRange(nextCaret, nextCaret);
          renderIdResults();
          return;
        }
      }
      if (event.key === 'Escape') {
        setSearchOpen(false);
        idToggle.focus();
      }
      if (event.key === 'Enter') {
        const first = matchingListings()[0];
        if (first) location.href = `object.html?id=${first.id}`;
      }
    });
    idResults.addEventListener('click', event => {
      const result = event.target.closest('[data-listing-id]');
      if (result) location.href = `object.html?id=${result.dataset.listingId}`;
    });
    document.addEventListener('click', event => {
      if (!idSearch.contains(event.target)) setSearchOpen(false);
    });
  }
}

// ---------- поле цены: ввод в тысячах (авто-«000») + ползунок-вилка ----------
// Потолок ползунка = €1 млн; крайнее правое положение = «без ограничения».
// Руками в поле можно вписать и больше — ползунок просто встанет вправо.
const PRICE_MAX_K = 1000;

function initPriceControl() {
  const fMin = document.getElementById('f-price-min');
  const fMax = document.getElementById('f-price-max');
  const sMin = document.getElementById('ps-min');
  const sMax = document.getElementById('ps-max');
  const fill = document.getElementById('ps-fill');
  const cap = document.getElementById('price-caption');
  if (!fMin || !sMin) return;

  // ползунок скрыт; открывается кнопкой-иконкой, закрывается кликом вне
  const slider = document.getElementById('price-slider');
  const toggle = document.getElementById('slider-toggle');
  toggle.addEventListener('click', e => {
    e.stopPropagation();
    slider.classList.toggle('open');
    toggle.classList.toggle('active', slider.classList.contains('open'));
  });
  document.addEventListener('click', e => {
    if (!slider.contains(e.target) && e.target !== toggle && !toggle.contains(e.target)) {
      slider.classList.remove('open');
      toggle.classList.remove('active');
    }
  });

  const thouMin = document.getElementById('thou-min');
  const thouMax = document.getElementById('thou-max');

  // подгоняем ширину поля под введённое число, чтобы «000» шло сразу после цифр
  function autoWidth(inp) {
    const len = (inp.value || inp.placeholder).length;
    inp.style.width = Math.min(7, Math.max(1, len)) + 'ch';
  }

  // общее: ползунок, заливка, подпись и фильтр. noMax = верх не ограничен.
  function updateVisuals(minK, maxK, noMax) {
    const cMin = Math.max(0, Math.min(PRICE_MAX_K, minK));
    const cMax = noMax ? PRICE_MAX_K : Math.max(0, Math.min(PRICE_MAX_K, maxK));
    sMin.value = cMin; sMax.value = cMax;
    fill.style.left = (cMin / PRICE_MAX_K * 100) + '%';
    fill.style.width = (Math.max(0, cMax - cMin) / PRICE_MAX_K * 100) + '%';

    const eur = k => '€' + (k * 1000).toLocaleString('ru-RU');
    cap.textContent = (minK === 0 && noMax) ? '— без ограничения'
      : `${eur(minK)} – ${noMax ? 'без ограничения' : eur(maxK)}`;

    state.priceMin = minK > 0 ? minK : '';
    state.priceMax = noMax ? '' : maxK;
    thouMin.classList.toggle('empty', !fMin.value);
    thouMax.classList.toggle('empty', !fMax.value);
    autoWidth(fMin); autoWidth(fMax);
    renderListings();
  }

  // движение ползунков → переписываем и текстовые поля
  function fromSlider() {
    let minK = +sMin.value, maxK = +sMax.value;
    if (minK > maxK) [minK, maxK] = [maxK, minK];
    const noMax = maxK >= PRICE_MAX_K;
    fMin.value = minK > 0 ? minK : '';
    fMax.value = noMax ? '' : maxK;
    updateVisuals(minK, maxK, noMax);
  }
  sMin.addEventListener('input', fromSlider);
  sMax.addEventListener('input', fromSlider);

  // ручной ввод (цифры = тысячи; можно больше потолка ползунка — просто встанет вправо)
  function fromInput() {
    const minK = parseInt(fMin.value.replace(/\D/g, ''), 10) || 0;
    const noMax = fMax.value.trim() === '';
    const maxK = noMax ? Infinity : (parseInt(fMax.value.replace(/\D/g, ''), 10) || 0);
    updateVisuals(minK, noMax ? PRICE_MAX_K : maxK, noMax);
  }
  fMin.addEventListener('input', fromInput);
  fMax.addEventListener('input', fromInput);

  fromInput(); // старт: без ограничений
}

// ---------- дропдаун контактов в шапке ----------
function initHeaderContact() {
  const wrap = document.getElementById('header-contact');
  const btn = document.getElementById('header-phone-btn');
  if (!wrap || !btn) return;
  btn.addEventListener('click', e => { e.stopPropagation(); wrap.classList.toggle('open'); });
  document.addEventListener('click', e => { if (!wrap.contains(e.target)) wrap.classList.remove('open'); });
}

// ---------- форма обратной связи ----------
function initContactForm() {
  const form = document.getElementById('contact-form');
  if (!form) return;
  form.addEventListener('submit', e => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    // TODO: подключить реальную отправку (Telegram-бот / email). Пока заявка идёт в чат-виджет.
    Chat.openWithLead(data);
    form.reset();
  });
  const chatBtn = document.getElementById('open-chat-btn');
  if (chatBtn) chatBtn.addEventListener('click', () => Chat.open());
}

document.addEventListener('DOMContentLoaded', () => {
  initFilters();
  renderListings();
  renderComplexes();
  renderInvest();
  initHeroSlideshow();
  initHeaderContact();
  initContactForm();
});
