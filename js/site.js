/* ============================================================
   Gurevic Real Estate — общий JS каждой страницы (ARCHITECTURE §4, §8).
   SITE.t() · SITE.util · дропдауны меню/языка/контактов · бургер (off-canvas)
   · состояние шапки при прокрутке · запоминание языка + плашка-подсказка.
   Без зависимостей, без инлайн-обработчиков; глобально только window.SITE.
   ============================================================ */
(function () {
  'use strict';

  var SITE = window.SITE = window.SITE || {};
  var doc = document;
  var root = doc.documentElement;
  var LANG = SITE.lang || root.lang || 'ru';
  var NBSP = ' ';

  /* ---------------- i18n ---------------- */

  // ru/uk/pl/fr/he/en — те же правила, что в tools/sitegen/fmt.py (Intl.PluralRules, если есть)
  var pluralRules = (typeof Intl !== 'undefined' && Intl.PluralRules) ? new Intl.PluralRules(LANG) : null;
  var PLURAL_FALLBACK = {
    one: ['one', 'other'], two: ['two', 'other', 'many'], few: ['few', 'other', 'many'],
    many: ['many', 'other', 'few'], other: ['other', 'many', 'few']
  };

  function format(str, vars) {
    if (!vars) return str;
    return String(str).replace(/\{(\w+)\}/g, function (m, k) {
      return Object.prototype.hasOwnProperty.call(vars, k) && vars[k] != null ? String(vars[k]) : m;
    });
  }

  function lookup(key) {
    var parts = String(key).split('.');
    var node = (SITE.i18n || {})[parts.shift()];
    while (node != null && parts.length) node = node[parts.shift()];
    return node;
  }

  /** SITE.t('forms.required', {n: 3}) → SITE.i18n.forms.required с подстановкой {n}.
      Значение-объект {one, few, many, other} + vars.n → форма множественного числа. */
  SITE.t = function (key, vars) {
    var val = lookup(key);
    if (val == null) return key;
    if (typeof val === 'object' && vars && vars.n != null) {
      var cat = pluralRules ? pluralRules.select(Number(vars.n)) : (Number(vars.n) === 1 ? 'one' : 'other');
      var chain = PLURAL_FALLBACK[cat] || ['other'];
      for (var i = 0; i < chain.length; i++) {
        if (val[chain[i]] != null) return format(val[chain[i]], vars);
      }
      return key;
    }
    return typeof val === 'string' ? format(val, vars) : val;
  };

  /* ---------------- utilities ---------------- */

  // Разделители и место знака € — как у генератора (одинаковый вид цен в HTML и в JS)
  var GROUP = { ru: NBSP, uk: NBSP, fr: NBSP, pl: NBSP, de: '.', en: ',', he: ',' };
  var DECIMAL = { ru: ',', uk: ',', fr: ',', pl: ',', de: ',', en: '.', he: '.' };
  var EURO_AFTER = { de: 1, fr: 1, pl: 1, uk: 1 };

  function formatNumber(value, decimals) {
    var n = Number(value);
    if (value === null || value === '' || !isFinite(n)) return value == null ? '' : String(value);
    if (decimals == null) decimals = n % 1 === 0 ? 0 : 1;
    var fixed = Math.abs(n).toFixed(decimals).split('.');
    var whole = fixed[0].replace(/\B(?=(\d{3})+(?!\d))/g, GROUP[LANG] || ',');
    return (n < 0 ? '-' : '') + whole + (fixed[1] ? (DECIMAL[LANG] || '.') + fixed[1] : '');
  }

  /** 213000 → «€213 000» (ru) / «€213,000» (en) / «213.000 €» (de); 0 → «Цена по запросу». */
  function formatPrice(value, opts) {
    opts = opts || {};
    var n = Math.round(Number(value) || 0);
    if (!n) return SITE.t('common.price_on_request');
    var num = formatNumber(n, 0);
    var text = EURO_AFTER[LANG] ? num + NBSP + '€' : '€' + num;
    return opts.perMonth ? text + NBSP + SITE.t('common.per_month') : text;
  }

  var storage = {
    get: function (key, area) {
      try { return window[area || 'localStorage'].getItem(key); } catch (e) { return null; }
    },
    set: function (key, value, area) {
      try { window[area || 'localStorage'].setItem(key, value); return true; } catch (e) { return false; }
    },
    remove: function (key, area) {
      try { window[area || 'localStorage'].removeItem(key); } catch (e) { /* приватный режим */ }
    }
  };

  function debounce(fn, ms) {
    var timer;
    return function () {
      var ctx = this, args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

  var FOCUSABLE = 'a[href], area[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
    'select:not([disabled]), textarea:not([disabled]), iframe, [tabindex]:not([tabindex="-1"]), [contenteditable="true"]';

  function focusables(container) {
    return Array.prototype.filter.call(container.querySelectorAll(FOCUSABLE), function (el) {
      return el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0;
    });
  }

  /** Держит Tab внутри container. Возвращает функцию снятия ловушки. */
  function trapFocus(container) {
    function onKey(e) {
      if (e.key !== 'Tab') return;
      var items = focusables(container);
      if (!items.length) { e.preventDefault(); return; }
      var first = items[0], last = items[items.length - 1];
      if (e.shiftKey && (doc.activeElement === first || !container.contains(doc.activeElement))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && doc.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
    container.addEventListener('keydown', onKey);
    return function () { container.removeEventListener('keydown', onKey); };
  }

  // Блокировка прокрутки страницы со счётчиком (меню, лайтбокс, чат могут пересекаться)
  var scrollLocks = 0;
  function lockScroll() {
    if (scrollLocks++ === 0) {
      var gap = window.innerWidth - root.clientWidth;
      if (gap > 0) root.style.setProperty('--scrollbar-gap', gap + 'px');
      root.classList.add('scroll-locked');
    }
  }
  function unlockScroll() {
    if (scrollLocks > 0 && --scrollLocks === 0) {
      root.classList.remove('scroll-locked');
      root.style.removeProperty('--scrollbar-gap');
    }
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return fallbackCopy(text); });
    }
    return Promise.resolve(fallbackCopy(text));
  }
  function fallbackCopy(text) {
    var ta = doc.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;inset-block-start:-1000px;opacity:0';
    doc.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = doc.execCommand('copy'); } catch (e) { ok = false; }
    doc.body.removeChild(ta);
    return ok;
  }

  function onReady(fn) {
    if (doc.readyState !== 'loading') fn();
    else doc.addEventListener('DOMContentLoaded', fn);
  }

  var reducedMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };

  SITE.util = {
    format: format,
    formatNumber: formatNumber,
    formatPrice: formatPrice,
    plural: function (key, n, vars) {
      var v = vars || {}; v.n = n;
      return SITE.t(key, v);
    },
    storage: storage,
    debounce: debounce,
    focusables: focusables,
    trapFocus: trapFocus,
    lockScroll: lockScroll,
    unlockScroll: unlockScroll,
    copyText: copyText,
    onReady: onReady,
    prefersReducedMotion: function () { return !!reducedMotion.matches; },
    // относительный путь от текущей страницы к файлу в корне сайта (SITE.root = "../../")
    rootPath: function (p) { return (SITE.root || '') + String(p).replace(/^\//, ''); }
  };

  /* ---------------- header: dropdowns, burger, scroll ---------------- */

  var mqMobile = window.matchMedia ? window.matchMedia('(max-width: 1024px)') : { matches: false };
  var mqHover = window.matchMedia ? window.matchMedia('(hover: hover) and (pointer: fine)') : { matches: false };

  function initHeader() {
    var header = doc.getElementById('site-header');
    if (!header) return;
    var panel = doc.getElementById('hdr-panel');
    var burger = header.querySelector('[data-menu-open]');
    var backdrop = doc.querySelector('.nav-backdrop');
    var dropdowns = Array.prototype.slice.call(header.querySelectorAll('[data-dropdown]'));

    function inPanel(el) { return panel && panel.contains(el); }
    function panelMode() { return mqMobile.matches; }

    /* --- дропдауны (подменю, язык, контакты) --- */
    function parts(dd) {
      return {
        toggle: dd.querySelector('[data-dropdown-toggle]'),
        menu: dd.querySelector('[data-dropdown-menu]')
      };
    }
    function isOpen(dd) { return dd.classList.contains('open'); }
    function setOpen(dd, open, focusToggle) {
      var p = parts(dd);
      dd.classList.toggle('open', open);
      if (p.toggle) {
        p.toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (focusToggle) p.toggle.focus();
      }
      if (!open) dd._byHover = false;
    }
    function closeAll(except) {
      dropdowns.forEach(function (dd) {
        if (dd !== except && isOpen(dd)) setOpen(dd, false);
      });
    }
    function menuLinks(dd) {
      var p = parts(dd);
      return p.menu ? Array.prototype.slice.call(p.menu.querySelectorAll('a[href]')) : [];
    }

    dropdowns.forEach(function (dd) {
      var p = parts(dd);
      if (!p.toggle || !p.menu) return;
      var hoverTimer;

      p.toggle.addEventListener('click', function (e) {
        e.stopPropagation();
        // открыто наведением — клик «закрепляет», а не закрывает
        if (isOpen(dd) && dd._byHover) { dd._byHover = false; return; }
        var open = !isOpen(dd);
        // в мобильной панели подменю — аккордеон, остальные не трогаем
        if (!(panelMode() && inPanel(dd))) closeAll(dd);
        setOpen(dd, open);
      });

      p.toggle.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          if (!(panelMode() && inPanel(dd))) closeAll(dd);
          setOpen(dd, true);
          var links = menuLinks(dd);
          var target = e.key === 'ArrowDown' ? links[0] : links[links.length - 1];
          if (target) target.focus();
        }
      });

      p.menu.addEventListener('keydown', function (e) {
        var links = menuLinks(dd);
        var i = links.indexOf(doc.activeElement);
        var next = null;
        if (e.key === 'ArrowDown') next = links[(i + 1) % links.length];
        else if (e.key === 'ArrowUp') next = links[(i - 1 + links.length) % links.length];
        else if (e.key === 'Home') next = links[0];
        else if (e.key === 'End') next = links[links.length - 1];
        if (next) { e.preventDefault(); next.focus(); }
      });

      // фокус ушёл за пределы пункта — закрыть (кроме аккордеона в мобильной панели)
      dd.addEventListener('focusout', function (e) {
        if (panelMode() && inPanel(dd)) return;
        if (e.relatedTarget && !dd.contains(e.relatedTarget)) setOpen(dd, false);
      });

      // наведение — только для подменю навигации и только на устройствах с мышью
      if (dd.classList.contains('nav-item')) {
        dd.addEventListener('mouseenter', function () {
          if (!mqHover.matches || panelMode()) return;
          clearTimeout(hoverTimer);
          if (!isOpen(dd)) {
            closeAll(dd);
            setOpen(dd, true);
            dd._byHover = true;
          }
        });
        dd.addEventListener('mouseleave', function () {
          if (!mqHover.matches || panelMode() || !dd._byHover) return;
          hoverTimer = setTimeout(function () { setOpen(dd, false); }, 180);
        });
      }
    });

    doc.addEventListener('click', function (e) {
      dropdowns.forEach(function (dd) {
        if (isOpen(dd) && !dd.contains(e.target) && !(panelMode() && inPanel(dd))) setOpen(dd, false);
      });
    });

    /* --- off-canvas панель (≤1024px) --- */
    var releaseTrap = null;
    var lastFocus = null;

    function panelIsOpen() { return panel && panel.classList.contains('open'); }

    function openPanel() {
      if (!panel || panelIsOpen()) return;
      lastFocus = doc.activeElement;
      closeAll();
      panel.setAttribute('role', 'dialog');
      panel.setAttribute('aria-modal', 'true');
      panel.setAttribute('aria-labelledby', panel.getAttribute('data-labelledby') || '');
      panel.classList.add('open');
      if (backdrop) { backdrop.hidden = false; backdrop.classList.add('open'); }
      root.classList.add('menu-open');
      burger.setAttribute('aria-expanded', 'true');
      burger.setAttribute('aria-label', SITE.t('common.menu_close'));
      lockScroll();
      releaseTrap = trapFocus(panel);
      var closeBtn = panel.querySelector('.nav-close');
      // фокус после начала анимации (visibility уже visible)
      requestAnimationFrame(function () { (closeBtn || focusables(panel)[0] || panel).focus(); });
    }

    function closePanel(restoreFocus) {
      if (!panel || !panelIsOpen()) return;
      panel.classList.remove('open');
      panel.removeAttribute('role');
      panel.removeAttribute('aria-modal');
      panel.removeAttribute('aria-labelledby');
      if (backdrop) { backdrop.classList.remove('open'); backdrop.hidden = true; }
      root.classList.remove('menu-open');
      burger.setAttribute('aria-expanded', 'false');
      burger.setAttribute('aria-label', SITE.t('common.menu_open'));
      unlockScroll();
      if (releaseTrap) { releaseTrap(); releaseTrap = null; }
      closeAll();
      if (restoreFocus !== false) {
        var target = (lastFocus && doc.contains(lastFocus) && lastFocus.offsetParent !== null) ? lastFocus : burger;
        target.focus();
      }
    }

    if (burger) {
      burger.addEventListener('click', function () {
        if (panelIsOpen()) closePanel(); else openPanel();
      });
    }
    Array.prototype.forEach.call(doc.querySelectorAll('[data-menu-close]'), function (el) {
      el.addEventListener('click', function () { closePanel(); });
    });
    if (panel) {
      // переход по ссылке (в т.ч. на якорь этой же страницы) — закрыть панель
      panel.addEventListener('click', function (e) {
        var a = e.target.closest ? e.target.closest('a[href]') : null;
        if (a && panelIsOpen()) closePanel(false);
      });
    }

    function onMqChange() {
      if (!panelMode()) closePanel(false);
      closeAll();
    }
    if (mqMobile.addEventListener) mqMobile.addEventListener('change', onMqChange);
    else if (mqMobile.addListener) mqMobile.addListener(onMqChange);

    /* --- Esc: сначала открытый дропдаун, затем панель --- */
    doc.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape' && e.key !== 'Esc') return;
      // 1) дропдаун, в котором фокус; 2) открытая панель; 3) любые открытые дропдауны
      var focused = dropdowns.filter(function (dd) { return isOpen(dd) && dd.contains(doc.activeElement); })[0];
      if (focused) { setOpen(focused, false, true); return; }
      if (panelIsOpen()) { closePanel(); return; }
      closeAll();
    });

    /* --- шапка: класс is-scrolled после 40px (прозрачная шапка над hero) --- */
    var ticking = false;
    function updateScrolled() {
      ticking = false;
      header.classList.toggle('is-scrolled', (window.pageYOffset || root.scrollTop) > 40);
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(updateScrolled); }
    }, { passive: true });
    // первое чтение scroll-позиции — в следующем кадре (без принудительного layout при загрузке)
    requestAnimationFrame(updateScrolled);
  }

  /* ---------------- язык: запоминание + плашка-подсказка ---------------- */

  var LANG_KEY = 'gre_lang';

  function supported() { return Object.keys(SITE.alternates || SITE.langNames || {}); }

  function browserLang() {
    var list = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || ''];
    var codes = supported();
    for (var i = 0; i < list.length; i++) {
      var c = String(list[i] || '').toLowerCase().split('-')[0];
      if (c === 'iw') c = 'he';
      if (codes.indexOf(c) !== -1) return c;
    }
    return null;
  }

  function initLanguage() {
    // явный выбор в переключателе (шапка, панель, подвал) запоминаем
    doc.addEventListener('click', function (e) {
      var a = e.target.closest ? e.target.closest('a[data-lang]') : null;
      if (a) storage.set(LANG_KEY, a.getAttribute('data-lang'));
    });

    if (SITE.page === '404') return;
    var stored = storage.get(LANG_KEY);
    var target = stored || browserLang();
    if (!target || target === LANG) return;
    var phrase = (SITE.langSuggest || {})[target];
    var href = (SITE.alternates || {})[target];
    if (!phrase || !href) return;

    // плашка раскладывается по направлению ТЕКУЩЕЙ страницы; тексты — на языке-цели (lang/dir на элементах)
    var targetDir = target === 'he' ? 'rtl' : 'ltr';
    function inTarget(el) { el.setAttribute('lang', target); el.setAttribute('dir', targetDir); return el; }

    var bar = doc.createElement('div');
    bar.className = 'lang-suggest';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', phrase.text);

    var text = inTarget(doc.createElement('span'));
    text.className = 'lang-suggest-text';
    text.textContent = phrase.text;

    var link = inTarget(doc.createElement('a'));
    link.className = 'lang-suggest-switch';
    link.href = href;
    link.hreflang = target;
    link.setAttribute('data-lang', target);
    link.textContent = phrase.switch;

    var close = doc.createElement('button');
    close.type = 'button';
    close.className = 'lang-suggest-close';
    close.setAttribute('aria-label', phrase.dismiss);
    close.setAttribute('lang', target);
    close.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    close.addEventListener('click', function () {
      // «нет, спасибо» = выбран текущий язык; больше не предлагаем
      storage.set(LANG_KEY, LANG);
      bar.classList.remove('show');
      setTimeout(function () { if (bar.parentNode) bar.parentNode.removeChild(bar); }, 250);
    });

    bar.appendChild(text);
    bar.appendChild(link);
    bar.appendChild(close);
    doc.body.appendChild(bar);
    // не поверх заставки главной: небольшая задержка
    setTimeout(function () { bar.classList.add('show'); }, reducedMotion.matches ? 0 : 1200);
  }

  onReady(function () {
    initHeader();
    initLanguage();
  });
})();
