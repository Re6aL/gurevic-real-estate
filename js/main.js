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

function cardHTML(l) {
  const badges = [`<span class="badge ${l.deal === 'rent' ? 'deal-rent' : ''}">${DICT.deal[l.deal]}</span>`];
  if (l.isComplex) badges.push('<span class="badge invest">Комплекс</span>');
  if (l.invest) badges.push(`<span class="badge invest">${l.investKind}</span>`);
  if (l.placeholder) badges.push('<span class="badge demo">Демо-объект</span>');
  return `
  <article class="card">
    <a href="object.html?id=${l.id}" style="position:relative; display:block;">
      <div class="badge-row">${badges.join('')}</div>
      ${ph(l.hue, 'Фото-плейсхолдер — заменить реальным')}
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
  let items = LISTINGS.filter(l => !l.invest && !l.isComplex);
  if (state.deal) items = items.filter(l => l.deal === state.deal);
  if (state.type) items = items.filter(l => l.type === state.type);
  if (state.location) items = items.filter(l => l.location === state.location);
  // цена вводится в тысячах € → умножаем на 1000
  if (state.priceMin) items = items.filter(l => l.price >= +state.priceMin * 1000);
  if (state.priceMax) items = items.filter(l => l.price <= +state.priceMax * 1000);
  if (state.areaMin) items = items.filter(l => (l.area || 0) >= +state.areaMin);
  if (state.areaMax) items = items.filter(l => (l.area || 0) <= +state.areaMax);
  if (state.sort === 'price-asc') items.sort((a, b) => a.price - b.price);
  if (state.sort === 'price-desc') items.sort((a, b) => b.price - a.price);
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

function renderInvest() {
  const grid = document.getElementById('invest-cards');
  if (!grid) return;
  grid.innerHTML = LISTINGS.filter(l => l.invest).map(l => cardHTML(l).replace(
    '<div class="card-price">',
    `<div class="invest-kind">${l.investKind}</div><div class="card-price">`
  )).join('');
}

function renderComplexes() {
  const grid = document.getElementById('complex-cards');
  if (!grid) return;
  grid.innerHTML = LISTINGS.filter(l => l.isComplex).map(l => {
    const n = (l.units || []).length;
    const avail = (l.units || []).filter(u => u.status === 'available').length;
    // добавляем строку «доступно вариантов» перед кнопкой
    return cardHTML(l).replace(
      '<div class="card-actions">',
      `<div class="card-params" style="color:var(--gold-dark);font-weight:700">🏢 вариантов в комплексе: ${n} · свободно: ${avail}</div><div class="card-actions">`
    );
  }).join('');
}

function initFilters() {
  const typeSel = document.getElementById('f-type');
  const locSel = document.getElementById('f-location');
  if (!typeSel) return;

  Object.entries(DICT.type).forEach(([k, v]) => {
    if (k === 'hotel') return; // отели живут в блоке инвестиций
    typeSel.insertAdjacentHTML('beforeend', `<option value="${k}">${v}</option>`);
  });
  LOCATIONS.forEach(loc => {
    locSel.insertAdjacentHTML('beforeend', `<option value="${loc}">${loc}</option>`);
  });

  // вкладки сделки
  document.querySelectorAll('.deal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      if (tab.dataset.deal === 'invest') {
        document.getElementById('invest').scrollIntoView({ behavior: 'smooth' });
        return;
      }
      document.querySelectorAll('.deal-tab').forEach(t => t.classList.toggle('active', t === tab));
      state.deal = tab.dataset.deal;
      renderListings();
    });
  });

  // селекты и поля от/до
  typeSel.addEventListener('change', () => { state.type = typeSel.value; renderListings(); });
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
}

// ---------- поле цены: ввод в тысячах (авто-«000») + ползунок-вилка ----------
const PRICE_MAX_K = 3500; // потолок ползунка = 3,5 млн €
const PRICE_STEP_K = 50;

function initPriceControl() {
  const fMin = document.getElementById('f-price-min');
  const fMax = document.getElementById('f-price-max');
  const sMin = document.getElementById('ps-min');
  const sMax = document.getElementById('ps-max');
  const fill = document.getElementById('ps-fill');
  const cap = document.getElementById('price-caption');
  if (!fMin || !sMin) return;

  const thouMin = document.getElementById('thou-min');
  const thouMax = document.getElementById('thou-max');
  const fmt = k => k.toLocaleString('ru-RU');

  // подгоняем ширину поля под введённое число, чтобы «000» шло сразу после цифр
  function autoWidth(inp) {
    const len = (inp.value || inp.placeholder).length;
    inp.style.width = Math.min(7, Math.max(1, len)) + 'ch';
  }

  // единый пересчёт состояния из значений ползунка (в тысячах)
  function apply(minK, maxK) {
    minK = Math.max(0, Math.min(PRICE_MAX_K, minK));
    maxK = Math.max(0, Math.min(PRICE_MAX_K, maxK));
    if (minK > maxK) [minK, maxK] = [maxK, minK];
    sMin.value = minK; sMax.value = maxK;

    // текстовые поля (в тысячах); пусто = без границы
    fMin.value = minK > 0 ? minK : '';
    fMax.value = maxK < PRICE_MAX_K ? maxK : '';
    thouMin.classList.toggle('empty', !fMin.value);
    thouMax.classList.toggle('empty', !fMax.value);
    autoWidth(fMin); autoWidth(fMax);

    // заливка между ползунками
    fill.style.left = (minK / PRICE_MAX_K * 100) + '%';
    fill.style.width = ((maxK - minK) / PRICE_MAX_K * 100) + '%';

    // подпись (полные евро с разделителем тысяч)
    const noMax = maxK >= PRICE_MAX_K;
    const eur = k => '€' + (k * 1000).toLocaleString('ru-RU');
    cap.textContent = (minK === 0 && noMax) ? '— без ограничения'
      : `${eur(minK)} – ${noMax ? 'без ограничения' : eur(maxK)}`;

    // состояние фильтра — в тысячах (applyFilters домножает на 1000)
    state.priceMin = minK > 0 ? minK : '';
    state.priceMax = noMax ? '' : maxK;
    renderListings();
  }

  // ползунки
  sMin.addEventListener('input', () => apply(+sMin.value, +sMax.value));
  sMax.addEventListener('input', () => apply(+sMin.value, +sMax.value));

  // текстовый ввод (цифры = тысячи)
  const onType = () => {
    const minK = parseInt(fMin.value.replace(/\D/g, ''), 10) || 0;
    const maxK = fMax.value.trim() === '' ? PRICE_MAX_K : (parseInt(fMax.value.replace(/\D/g, ''), 10) || 0);
    autoWidth(fMin); autoWidth(fMax);
    thouMin.classList.toggle('empty', !fMin.value);
    thouMax.classList.toggle('empty', !fMax.value);
    apply(minK, maxK);
  };
  fMin.addEventListener('input', onType);
  fMax.addEventListener('input', onType);

  apply(0, PRICE_MAX_K); // старт: без ограничений
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
  initHeaderContact();
  initContactForm();
});
