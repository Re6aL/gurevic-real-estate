// ============================================================
// Gurevic Real Estate — инвестиции (/invest/ и invest/<категория>/).
//
// Переход к форме инвестора (#enquiry) без перезагрузки и с правильным фокусом:
//   [data-invest-cta]            → плавная прокрутка к форме, фокус на её заголовок;
//   [data-invest-type="hotel"]   → предвыбор «Тип инвестиций» в форме + фокус на этом поле;
//   [data-invest-variant="company"] → вкладка «Представитель компании» + фокус на вкладку.
// Хэш #enquiry-<тип> (#enquiry-hotel, #enquiry-land, #enquiry-logistics, #enquiry-company …)
// делает то же при загрузке и при смене хэша — для ссылок с других страниц.
// Без JS ссылки ведут на #enquiry обычным якорем. При prefers-reduced-motion — без анимации.
// Тексты — SITE.t('invest.*') (i18n invest.js); глобальных переменных не создаёт.
// ============================================================
(function () {
  'use strict';

  var SITE = window.SITE || {};
  var section = document.getElementById('enquiry');
  if (!section) return;
  var form = section.querySelector('form[data-lead-form]');
  var heading = document.getElementById('enquiry-title');
  var status = section.querySelector('[data-invest-status]');

  // коды — brief §E (общие для формы, воркера и Notion)
  var TYPES = ['hotel', 'development_land', 'restaurant_commercial', 'warehouse_logistics', 'development_partnership', 'other'];
  var ALIASES = {
    hotels: 'hotel', land: 'development_land', commercial: 'restaurant_commercial', restaurant: 'restaurant_commercial',
    logistics: 'warehouse_logistics', warehouse: 'warehouse_logistics', development: 'development_partnership'
  };
  var flashTimer = null;
  var announceTimer = null;

  function t(key, vars) {
    return typeof SITE.t === 'function' ? SITE.t(key, vars) : '';
  }

  function reducedMotion() {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; }
  }

  function visible(el) {
    return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  }

  function announce(text) {
    if (!status || !text) return;
    status.textContent = '';
    clearTimeout(announceTimer);
    announceTimer = setTimeout(function () { status.textContent = text; }, 60);
  }

  /** Выбирает тип инвестиций в форме; возвращает <select> или null. */
  function setType(code) {
    var select = form && form.querySelector('select[name=investment_type]');
    if (!select || TYPES.indexOf(code) === -1 || !select.querySelector('option[value="' + code + '"]')) return null;
    if (select.value !== code) {
      select.value = code;
      // forms.js слушает change: пересчёт условий и сохранение черновика
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }
    select.classList.add('inv-flash');
    clearTimeout(flashTimer);
    flashTimer = setTimeout(function () { select.classList.remove('inv-flash'); }, 1600);
    var option = select.options[select.selectedIndex];
    announce(t('invest.preselected', { type: option ? option.text : code }));
    return select;
  }

  /** Переключает вкладку формы инвестора (private | company); возвращает вкладку или null. */
  function setVariant(variant) {
    var tab = form && form.querySelector('[role=tab][data-variant="' + variant + '"]');
    if (!tab) return null;
    if (tab.getAttribute('aria-selected') !== 'true') tab.click();
    return tab;
  }

  function go(focusEl, instant) {
    var target = focusEl && focusEl !== heading ? focusEl : section;
    var behavior = instant || reducedMotion() ? 'auto' : 'smooth';
    try {
      target.scrollIntoView({ behavior: behavior, block: target === section ? 'start' : 'center' });
    } catch (e) {
      target.scrollIntoView();
    }
    var el = focusEl || heading;
    if (el) {
      try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
    }
  }

  function handle(type, variant, instant) {
    var focusEl = heading;
    if (variant) {
      var tab = setVariant(variant);
      if (tab && visible(tab)) focusEl = tab;
    }
    if (type) {
      var select = setType(ALIASES[type] || type);
      if (select && visible(select)) focusEl = select;
    }
    go(focusEl, instant);
  }

  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var link = e.target.closest && e.target.closest('[data-invest-cta], [data-invest-type], [data-invest-variant]');
    if (!link) return;
    var href = link.getAttribute('href');
    if (href && href !== '#enquiry') return; // ссылка на другую страницу — обычный переход
    e.preventDefault();
    handle(link.getAttribute('data-invest-type'), link.getAttribute('data-invest-variant'), false);
    if (window.history && history.replaceState && location.hash !== '#enquiry') {
      try { history.replaceState(null, '', '#enquiry'); } catch (err) { /* file:// и т. п. */ }
    }
  });

  function fromHash(instant) {
    var m = /^#enquiry-([a-z_]+)$/.exec(window.location.hash || '');
    if (!m) return;
    var key = m[1];
    if (key === 'company' || key === 'private') handle(null, key, instant);
    else handle(key, null, instant);
  }

  window.addEventListener('hashchange', function () { fromHash(false); });
  fromHash(true);
})();
