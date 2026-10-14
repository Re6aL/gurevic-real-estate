// ============================================================
// Gurevic Real Estate — формы заявок (ARCHITECTURE §7).
//
// Прогрессивное улучшение форм из src/templates/macros/forms.html:
// условные поля, вкладки инвестора, валидация с сообщениями из SITE.i18n.forms,
// ловушка для ботов, замер времени, UTM, отправка JSON (text/plain, без CORS-preflight)
// на SITE.leadEndpoint, состояние «отправлено» и запасной канал
// (WhatsApp / Telegram / e-mail с готовым текстом), если эндпоинта нет или он недоступен.
// Набранное не теряется: черновик живёт в sessionStorage до успешной отправки.
//
// Публичное API: window.GRForms = { submit(payload), fallbackLinks(text, subject), fallbackButtons(text, subject, onNote, labels),
//                                  enhance(root), utm(), t(key, params) }
// Чистые функции экспортируются в Node (module.exports) для tools/tests.
// ============================================================

(function () {
  'use strict';

  // ---------- чистые функции (без DOM) ----------
  const UTM_KEYS = ['source', 'medium', 'campaign', 'term', 'content'];
  const MAILTO_MAX = 1800; // длинные mailto: обрезаются почтовыми клиентами

  /** '{n} полей' + {n: 3} → '3 полей'; неизвестные плейсхолдеры остаются как есть. */
  function format(str, params) {
    if (typeof str !== 'string' || !params) return str;
    return str.replace(/\{(\w+)\}/g, (m, k) => (Object.prototype.hasOwnProperty.call(params, k) ? String(params[k]) : m));
  }

  /** utm_* из строки запроса → {source, medium, …} (только непустые, ≤ 200 символов). */
  function parseUtm(search) {
    const out = {};
    let q;
    try { q = new URLSearchParams(search || ''); } catch (e) { return out; }
    UTM_KEYS.forEach((k) => {
      const v = (q.get('utm_' + k) || '').trim().slice(0, 200);
      if (v) out[k] = v;
    });
    return out;
  }

  function isEmail(v) {
    return /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/.test(v);
  }

  /** Международный формат: допускаем +, цифры, пробелы, скобки, дефисы, точки; 7–15 цифр. */
  function isPhone(v) {
    if (!/^\+?[\d\s().-]+$/.test(v)) return false;
    const digits = v.replace(/\D/g, '');
    return digits.length >= 7 && digits.length <= 15;
  }

  /** @username, username или ссылка t.me/username → '@username'; null, если не похоже. */
  function normalizeTelegram(v) {
    let s = String(v || '').trim();
    s = s.replace(/^(https?:\/\/)?(www\.)?(t\.me|telegram\.me)\//i, '').replace(/^@/, '').replace(/\/+$/, '');
    return /^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(s) ? '@' + s : null;
  }

  function isUrlLike(v) {
    return /^(https?:\/\/)?[\w-]+(\.[\w-]+)+(:\d+)?(\/\S*)?$/i.test(v);
  }

  /** '250 000', '250,000', '250000' → true */
  function isNumberLike(v) {
    return /^\d[\d\s.,']*$/.test(v) && /\d/.test(v);
  }

  /** Условие 'name=a|b' против значений {name: [..]}. Пустое условие — истина. */
  function checkCond(spec, values) {
    if (!spec) return true;
    const i = spec.indexOf('=');
    if (i < 0) return true;
    const name = spec.slice(0, i);
    const allowed = spec.slice(i + 1).split('|');
    const have = values[name] || [];
    return have.some((v) => allowed.indexOf(v) !== -1);
  }

  /** Текст заявки для мессенджера/почты. rows: [[подпись, значение], …] */
  function buildText(header, rows, footer) {
    const lines = [header, ''];
    rows.forEach(([label, value]) => {
      if (value === '' || value == null) return;
      const v = String(value);
      lines.push(v.indexOf('\n') !== -1 ? `${label}:\n${v}` : `${label}: ${v}`);
    });
    if (footer) lines.push('', footer);
    return lines.join('\n');
  }

  /** Ссылки запасного канала. contacts — SITE.contacts. */
  function fallbackLinks(text, subject, contacts) {
    const c = contacts || {};
    const wa = String(c.whatsapp || '').replace(/\/+$/, '');
    let body = String(text || '');
    if (body.length > MAILTO_MAX) body = body.slice(0, MAILTO_MAX) + '…';
    return {
      whatsapp: wa ? `${wa}?text=${encodeURIComponent(text || '')}` : '',
      telegram: c.telegram || '',
      email: c.email ? `mailto:${c.email}?subject=${encodeURIComponent(subject || '')}&body=${encodeURIComponent(body)}` : '',
    };
  }

  /** Полный payload по контракту §7 из частичного (form, fields, …) и окружения env. */
  function buildPayload(part, env) {
    const e = env || {};
    return {
      form: part.form,
      lang: part.lang || e.lang || '',
      page: part.page || e.page || '',
      ts: part.ts || (e.now ? new Date(e.now) : new Date()).toISOString(),
      elapsed_ms: Math.max(0, Math.round(Number(part.elapsed_ms) || 0)),
      hp: typeof part.hp === 'string' ? part.hp : '',
      consent: part.consent === true,
      consent_version: part.consent_version || e.consentVersion || '',
      utm: part.utm || e.utm || {},
      fields: part.fields || {},
    };
  }

  const pure = { format, parseUtm, isEmail, isPhone, normalizeTelegram, isUrlLike, isNumberLike, checkCond, buildText, fallbackLinks, buildPayload };

  if (typeof document === 'undefined') {
    if (typeof module !== 'undefined' && module.exports) module.exports = pure;
    return;
  }

  // ---------- окружение ----------
  const SITE = window.SITE || {};
  const CONTACTS = SITE.contacts || {};
  const SKIP_FIELDS = ['consent', 'homepage'];
  const TIMEOUT_MS = 15000;

  /** forms.* (i18n/<lang>/forms.json → js) из SITE.i18n (через SITE.t, если его уже определил site.js). */
  function t(key, params) {
    const full = key.indexOf('.') === -1 ? 'forms.' + key : key;
    if (typeof SITE.t === 'function') {
      const v = SITE.t(full, params);
      if (v && v !== full) return v;
    }
    const parts = full.split('.');
    let node = SITE.i18n || {};
    for (const p of parts) {
      node = node && typeof node === 'object' ? node[p] : undefined;
    }
    return typeof node === 'string' ? format(node, params) : full;
  }

  function store(kind) {
    try { return window[kind]; } catch (e) { return null; }
  }

  function sessionGet(key) {
    try { const s = store('sessionStorage'); return s ? s.getItem(key) : null; } catch (e) { return null; }
  }

  function sessionSet(key, value) {
    try {
      const s = store('sessionStorage');
      if (!s) return;
      if (value == null) s.removeItem(key); else s.setItem(key, value);
    } catch (e) { /* приватный режим / квота — без черновиков */ }
  }

  // UTM первого входа в сессии
  const UTM_KEY = 'gre_utm';
  let utmCache = null;
  function utm() {
    if (utmCache) return utmCache;
    const fresh = parseUtm(location.search);
    let saved = null;
    try { saved = JSON.parse(sessionGet(UTM_KEY) || 'null'); } catch (e) { saved = null; }
    if (Object.keys(fresh).length && !(saved && Object.keys(saved).length)) {
      sessionSet(UTM_KEY, JSON.stringify(fresh));
      saved = fresh;
    }
    utmCache = saved && typeof saved === 'object' ? saved : fresh;
    return utmCache;
  }

  function pageUrl() {
    return SITE.url || location.href.split('#')[0];
  }

  /** POST на SITE.leadEndpoint. → Promise<{ok, reason}>; reason: no_endpoint | http_<код> | network | timeout */
  function submit(part) {
    const payload = buildPayload(part, {
      lang: SITE.lang, page: pageUrl(), consentVersion: SITE.consentVersion, utm: utm(),
    });
    const endpoint = SITE.leadEndpoint;
    if (!endpoint) return Promise.resolve({ ok: false, reason: 'no_endpoint', payload });
    const ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = ctrl ? setTimeout(() => ctrl.abort(), TIMEOUT_MS) : null;
    return fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: JSON.stringify(payload),
      credentials: 'omit',
      signal: ctrl ? ctrl.signal : undefined,
    }).then((res) => res.json().catch(() => ({})).then((data) => {
      if (res.ok && data.ok !== false) return { ok: true, payload };
      return { ok: false, reason: 'http_' + res.status + (data.error ? ':' + data.error : ''), payload };
    })).catch((err) => ({ ok: false, reason: err && err.name === 'AbortError' ? 'timeout' : 'network', payload }))
      .finally(() => { if (timer) clearTimeout(timer); });
  }

  /** Ссылки запасного канала + copy() → Promise<bool> (копирует текст в буфер). */
  function links(text, subject) {
    const l = fallbackLinks(text, subject, CONTACTS);
    l.copy = () => copyText(text);
    return l;
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(() => true, () => legacyCopy(text));
    }
    return Promise.resolve(legacyCopy(text));
  }

  function legacyCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }

  // ---------- DOM-помощники ----------
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.keys(attrs || {}).forEach((k) => {
      const v = attrs[k];
      if (v == null || v === false) return;
      if (k === 'text') node.textContent = v;
      else if (k === 'className') node.className = v;
      else node.setAttribute(k, v === true ? '' : v);
    });
    (children || []).forEach((c) => { if (c) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return node;
  }

  const SVG = {
    whatsapp: 'M17.5 14.4c-.3-.1-1.7-.8-1.9-.9-.3-.1-.5-.1-.7.1-.2.3-.7.9-.9 1.1-.2.2-.3.2-.6.1-.3-.1-1.2-.4-2.3-1.4-.9-.8-1.4-1.7-1.6-2-.2-.3 0-.5.1-.6l.4-.5.3-.5c.1-.2 0-.4 0-.5l-.9-2.2c-.2-.6-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4-.3.3-1 1-1 2.5s1.1 2.9 1.2 3.1c.1.2 2.1 3.2 5.1 4.5.7.3 1.3.5 1.7.6.7.2 1.4.2 1.9.1.6-.1 1.7-.7 2-1.4.2-.7.2-1.3.2-1.4-.1-.1-.3-.2-.6-.3zM12 2a10 10 0 0 0-8.5 15.3L2 22l4.8-1.5A10 10 0 1 0 12 2z',
    telegram: 'M21.9 4.3 18.7 19.6c-.2 1-.9 1.3-1.8.8l-4.9-3.6-2.4 2.3c-.3.3-.5.5-1 .5l.4-5 9.1-8.2c.4-.4-.1-.6-.6-.2L6.6 13.2l-4.8-1.5c-1-.3-1-1 .2-1.5l18.7-7.2c.9-.3 1.6.2 1.3 1.3z',
    email: 'M3 5h18v14H3zM3 7l9 6 9-6',
    copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
    check: 'M5 12.5l4.5 4.5L19 7.5',
  };
  const SVG_FILLED = ['whatsapp', 'telegram'];

  function icon(name) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '20');
    svg.setAttribute('height', '20');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('class', 'icon');
    if (SVG_FILLED.indexOf(name) !== -1) {
      svg.setAttribute('fill', 'currentColor');
    } else {
      svg.setAttribute('fill', 'none');
      svg.setAttribute('stroke', 'currentColor');
      svg.setAttribute('stroke-width', '1.8');
      svg.setAttribute('stroke-linecap', 'round');
      svg.setAttribute('stroke-linejoin', 'round');
    }
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', SVG[name]);
    svg.appendChild(path);
    return svg;
  }

  /** Панель кнопок запасного канала (используется и формами, и чатом).
      labels — необязательные подписи {channel_whatsapp, channel_telegram, channel_email, channel_copy, copied, telegram_note, copy_failed}. */
  function fallbackButtons(text, subject, onNote, labels) {
    const l = links(text, subject);
    const L = (k) => (labels && labels[k]) || t('forms.' + k);
    const wrap = el('div', { className: 'lf-channels' });
    if (l.whatsapp) {
      wrap.appendChild(el('a', { className: 'lf-channel lf-channel--whatsapp', href: l.whatsapp, target: '_blank', rel: 'noopener' },
        [icon('whatsapp'), el('span', { text: L('channel_whatsapp') })]));
    }
    if (l.telegram) {
      const a = el('a', { className: 'lf-channel lf-channel--telegram', href: l.telegram, target: '_blank', rel: 'noopener' },
        [icon('telegram'), el('span', { text: L('channel_telegram') })]);
      // клик — жест пользователя: копируем текст, ссылка открывается штатно
      a.addEventListener('click', () => {
        l.copy().then((ok) => { if (onNote) onNote(ok ? L('telegram_note') : L('copy_failed')); });
      });
      wrap.appendChild(a);
    }
    if (l.email) {
      wrap.appendChild(el('a', { className: 'lf-channel lf-channel--email', href: l.email }, [icon('email'), el('span', { text: L('channel_email') })]));
    }
    const copyBtn = el('button', { className: 'lf-channel lf-channel--copy', type: 'button' }, [icon('copy'), el('span', { text: L('channel_copy') })]);
    copyBtn.addEventListener('click', () => {
      l.copy().then((ok) => { if (onNote) onNote(ok ? L('copied') : L('copy_failed')); });
    });
    wrap.appendChild(copyBtn);
    return wrap;
  }

  // ---------- состояние формы ----------
  function controls(form) {
    return Array.prototype.filter.call(form.elements, (c) => c.name && c.type !== 'submit' && c.type !== 'button');
  }

  function values(form) {
    const out = {};
    controls(form).forEach((c) => {
      if ((c.type === 'radio' || c.type === 'checkbox') && !c.checked) return;
      (out[c.name] = out[c.name] || []).push(c.value);
    });
    return out;
  }

  function formName(form) {
    return form.getAttribute('data-form') || 'contact';
  }

  function fieldBox(c) {
    return c.closest('.lf-group, .lf-field');
  }

  /** Видимая подпись поля (с учётом альтернативных меток по условию). */
  function labelOf(c) {
    if (c.getAttribute('data-label')) return c.getAttribute('data-label');
    const box = c.type === 'radio' ? c.closest('.lf-group') : fieldBox(c);
    if (!box) return c.name;
    const texts = box.querySelectorAll('.lf-label-text');
    for (const node of texts) {
      if (!node.hidden && node.closest('.lf-field, .lf-group') === box) return node.textContent.trim();
    }
    return c.name;
  }

  /** Условные блоки: hidden + disabled для полей внутри скрытых блоков; обязательность по условию. */
  function applyConditions(form) {
    const vals = values(form);
    form.querySelectorAll('[data-show-when]').forEach((node) => {
      node.hidden = !checkCond(node.getAttribute('data-show-when'), vals);
    });
    controls(form).forEach((c) => {
      if (c.type === 'hidden') return;
      const off = !!c.closest('[data-show-when][hidden]');
      if (c.disabled !== off) {
        c.disabled = off;
        if (off) clearError(form, c);
      }
    });
    form.querySelectorAll('[data-required-when]').forEach((box) => {
      const on = checkCond(box.getAttribute('data-required-when'), vals);
      box.classList.toggle('is-required', on);
      box.querySelectorAll('input, select, textarea').forEach((c) => {
        c.required = on;
        if (!on) clearError(form, c);
      });
    });
  }

  // ---------- валидация ----------
  function errorNode(box) {
    return box ? Array.prototype.find.call(box.querySelectorAll('.lf-error'), (n) => n.closest('.lf-group, .lf-field') === box) : null;
  }

  function setDescribed(c, errId, on) {
    const ids = (c.getAttribute('aria-describedby') || '').split(/\s+/).filter((x) => x && x !== errId);
    if (on) ids.push(errId);
    if (ids.length) c.setAttribute('aria-describedby', ids.join(' '));
    else c.removeAttribute('aria-describedby');
  }

  function markError(box, targets, msg) {
    const node = errorNode(box);
    if (!node) return;
    node.textContent = msg;
    node.hidden = false;
    box.classList.add('has-error');
    targets.forEach((c) => {
      c.setAttribute('aria-invalid', 'true');
      setDescribed(c, node.id, true);
    });
  }

  function clearBox(box) {
    if (!box) return;
    const node = errorNode(box);
    if (node) { node.textContent = ''; node.hidden = true; }
    box.classList.remove('has-error');
    box.querySelectorAll('[aria-invalid]').forEach((c) => {
      c.removeAttribute('aria-invalid');
      if (node) setDescribed(c, node.id, false);
    });
  }

  function clearError(form, c) {
    clearBox(c.type === 'radio' ? c.closest('.lf-group') : fieldBox(c));
  }

  function todayIso() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  /** Сообщение об ошибке для одиночного контрола или '' */
  function checkControl(c) {
    const v = (c.value || '').trim();
    if (c.type === 'checkbox') {
      if (c.required && !c.checked) return c.name === 'consent' ? t('forms.consent') : t('forms.required');
      return '';
    }
    if (!v) {
      if (!c.required) return '';
      return c.tagName === 'SELECT' ? t('forms.required_choice') : t('forms.required');
    }
    const rule = c.getAttribute('data-validate');
    if (c.type === 'email' && !isEmail(v)) return t('forms.email');
    if (c.type === 'tel' && !isPhone(v)) return t('forms.phone');
    if (rule === 'telegram' && !normalizeTelegram(v)) return t('forms.telegram');
    if (rule === 'url' && !isUrlLike(v)) return t('forms.url');
    if (rule === 'number' && !isNumberLike(v)) return t('forms.number');
    if (c.type === 'number') {
      const n = Number(v);
      if (!Number.isFinite(n)) return t('forms.number');
      if (c.min !== '' && n < Number(c.min)) return t('forms.number_min', { min: c.min });
    }
    if (c.type === 'date') {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return t('forms.date');
      if (c.hasAttribute('data-min-today') && v < todayIso()) return t('forms.date_past');
    }
    return '';
  }

  /** Проверка одного поля/группы; возвращает {box, focus, msg} или null. */
  function validateBox(form, box) {
    if (!box || box.closest('[data-show-when][hidden]')) return null;
    if (box.matches('fieldset[data-require-one]')) {
      const inner = Array.prototype.filter.call(box.querySelectorAll('input'), (c) => !c.disabled);
      // сперва — формат каждого заполненного поля (ошибка показывается у самого поля)
      let first = null;
      inner.forEach((c) => {
        const msg = checkControl(c);
        const fb = fieldBox(c);
        if (msg) { markError(fb, [c], msg); if (!first) first = { box: fb, focus: c, msg }; } else clearBox(fb);
      });
      clearBox(box);
      if (first) return first;
      if (!inner.some((c) => c.value.trim())) {
        markError(box, inner, t('forms.contact_one'));
        return { box, focus: inner[0], msg: t('forms.contact_one') };
      }
      return null;
    }
    if (box.matches('fieldset.lf-group')) {
      const radios = Array.prototype.filter.call(box.querySelectorAll('input[type=radio]'), (c) => !c.disabled);
      const required = radios.some((c) => c.required);
      if (required && !radios.some((c) => c.checked)) {
        markError(box, radios, t('forms.required_choice'));
        return { box, focus: radios[0], msg: t('forms.required_choice') };
      }
      clearBox(box);
      return null;
    }
    const c = box.querySelector('input:not([type=hidden]), select, textarea');
    if (!c || c.disabled) return null;
    const msg = checkControl(c);
    if (msg) { markError(box, [c], msg); return { box, focus: c, msg }; }
    clearBox(box);
    return null;
  }

  function topBoxes(form) {
    // поля внутри группы «хотя бы один контакт» проверяет сама группа
    return Array.prototype.filter.call(form.querySelectorAll('.lf-body .lf-field, .lf-body .lf-group'),
      (box) => !box.parentElement.closest('fieldset[data-require-one]'));
  }

  function validateForm(form) {
    const errors = [];
    topBoxes(form).forEach((box) => {
      const err = validateBox(form, box);
      if (err) errors.push(err);
    });
    return errors;
  }

  function showSummary(form, errors) {
    const sum = form.querySelector('.lf-summary');
    if (!sum) return;
    sum.textContent = '';
    if (!errors.length) { sum.hidden = true; return; }
    sum.appendChild(el('p', { className: 'lf-summary__title', text: t('forms.summary', { n: errors.length }) }));
    const list = el('ul', { className: 'lf-summary__list' });
    errors.forEach((err) => {
      // у чекбокса (согласие) подпись длинная — достаточно самого сообщения
      const text = err.focus.type === 'checkbox' ? err.msg : `${labelOf(err.focus)}: ${err.msg}`;
      const a = el('a', { href: '#' + err.focus.id, text });
      a.addEventListener('click', (e) => {
        e.preventDefault();
        err.focus.focus();
      });
      list.appendChild(el('li', {}, [a]));
    });
    sum.appendChild(list);
    sum.hidden = false;
    sum.focus();
  }

  // ---------- сбор данных ----------
  function collect(form) {
    const fields = {};
    const rows = [];
    let consent = false;
    let hp = '';
    const seen = {};
    controls(form).forEach((c) => {
      if (c.name === 'homepage') { hp = c.value; return; }
      if (c.name === 'consent') { consent = c.checked; return; }
      if (c.disabled || c.name.charAt(0) === '_' || SKIP_FIELDS.indexOf(c.name) !== -1) return;
      if (c.type === 'radio' && !c.checked) return;
      if (seen[c.name]) return;
      let value;
      let display;
      if (c.type === 'checkbox') {
        value = c.checked;
        display = c.checked ? t('forms.yes') : t('forms.no');
        if (!c.checked) { fields[c.name] = false; return; }
      } else {
        value = (c.value || '').trim();
        if (!value) return;
        if (c.getAttribute('data-validate') === 'telegram') value = normalizeTelegram(value) || value;
        display = value;
        if (c.type === 'hidden') {
          // служебное скрытое поле (interest=rent) — только в payload, не в текст заявки;
          // с подписью — читаемое значение из data-display вместо кода (sell → «Продать»)
          if (!c.getAttribute('data-label')) { seen[c.name] = true; fields[c.name] = value; return; }
          display = c.getAttribute('data-display') || value;
        }
        if (c.tagName === 'SELECT') display = c.options[c.selectedIndex].text;
        if (c.type === 'radio') {
          const txt = c.closest('.lf-choice') && c.closest('.lf-choice').querySelector('.lf-choice__text');
          if (txt) display = txt.textContent.trim();
        }
      }
      seen[c.name] = true;
      fields[c.name] = value;
      rows.push([labelOf(c), display]);
    });
    return { fields, rows, consent, hp };
  }

  // ---------- черновики ----------
  function draftKey(form) {
    return 'gre_form:' + location.pathname + '#' + form.id;
  }

  function saveDraft(form) {
    const data = {};
    controls(form).forEach((c) => {
      if (c.type === 'hidden' && c.name !== '_variant') return;
      if (SKIP_FIELDS.indexOf(c.name) !== -1) return;
      if (c.type === 'radio') { if (c.checked) data[c.name] = c.value; return; }
      if (c.type === 'checkbox') { data[c.name] = c.checked; return; }
      if (c.value) data[c.name + (c.id ? '#' + c.id : '')] = c.value;
    });
    sessionSet(draftKey(form), JSON.stringify(data));
  }

  function restoreDraft(form) {
    let data = null;
    try { data = JSON.parse(sessionGet(draftKey(form)) || 'null'); } catch (e) { data = null; }
    if (!data || typeof data !== 'object') return false;
    controls(form).forEach((c) => {
      if (c.type === 'hidden' && c.name !== '_variant') return;
      if (SKIP_FIELDS.indexOf(c.name) !== -1) return;
      if (c.type === 'radio') {
        if (Object.prototype.hasOwnProperty.call(data, c.name)) c.checked = c.value === data[c.name];
      } else if (c.type === 'checkbox') {
        if (Object.prototype.hasOwnProperty.call(data, c.name)) c.checked = !!data[c.name];
      } else {
        const key = c.name + (c.id ? '#' + c.id : '');
        if (Object.prototype.hasOwnProperty.call(data, key)) c.value = data[key];
      }
    });
    return true;
  }

  // ---------- вкладки инвестора ----------
  function setVariant(form, variant, focus) {
    const tabs = form.querySelectorAll('[role=tab][data-variant]');
    if (!tabs.length) return;
    const hiddenInput = form.querySelector('input[name=_variant]');
    if (hiddenInput) hiddenInput.value = variant;
    tabs.forEach((tab) => {
      const on = tab.getAttribute('data-variant') === variant;
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.tabIndex = on ? 0 : -1;
      if (on) {
        const panel = document.getElementById(tab.getAttribute('aria-controls'));
        if (panel) panel.setAttribute('aria-labelledby', tab.id);
        if (focus) tab.focus();
      }
    });
    form.setAttribute('data-form', variant === 'company' ? 'investor_company' : 'investor');
    applyConditions(form);
  }

  function initTabs(form) {
    const tabs = Array.prototype.slice.call(form.querySelectorAll('[role=tab][data-variant]'));
    if (!tabs.length) return;
    const hiddenInput = form.querySelector('input[name=_variant]');
    if (hiddenInput) setVariant(form, hiddenInput.value || 'private', false);
    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => { setVariant(form, tab.getAttribute('data-variant'), false); saveDraft(form); });
      tab.addEventListener('keydown', (e) => {
        const rtl = getComputedStyle(tab).direction === 'rtl';
        let next = null;
        if (e.key === 'ArrowRight') next = rtl ? i - 1 : i + 1;
        else if (e.key === 'ArrowLeft') next = rtl ? i + 1 : i - 1;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = tabs.length - 1;
        if (next === null) return;
        e.preventDefault();
        const target = tabs[(next + tabs.length) % tabs.length];
        setVariant(form, target.getAttribute('data-variant'), true);
        saveDraft(form);
      });
    });
  }

  // ---------- результат ----------
  function setStatus(form, text) {
    const status = form.querySelector('.lf-status');
    if (status) status.textContent = text;
  }

  function resultPanel(form) {
    const box = form.querySelector('.lf-result');
    box.textContent = '';
    box.hidden = false;
    return box;
  }

  function showSuccess(form) {
    const box = resultPanel(form);
    box.className = 'lf-result lf-result--success';
    const body = form.querySelector('.lf-body');
    const title = el('p', { className: 'lf-result__title', tabindex: '-1' }, [icon('check'), el('span', { text: t('forms.success_title') })]);
    const again = el('button', { className: 'lf-link-btn', type: 'button', text: t('forms.success_again') });
    again.addEventListener('click', () => {
      form.reset();
      sessionSet(draftKey(form), null);
      box.hidden = true;
      box.textContent = '';
      body.hidden = false;
      setVariant(form, (form.querySelector('input[name=_variant]') || {}).value || 'private', false);
      applyDefaults(form);
      applyConditions(form);
      form.__t0 = Date.now();
      const first = form.querySelector('.lf-body input:not([type=hidden]):not([disabled]), .lf-body select, .lf-body textarea');
      if (first) first.focus();
    });
    box.appendChild(title);
    box.appendChild(el('p', { className: 'lf-result__text', text: t('forms.success_text') }));
    box.appendChild(again);
    body.hidden = true;
    sessionSet(draftKey(form), null);
    setStatus(form, t('forms.success_title'));
    title.focus();
  }

  function showFallback(form, rows, reason) {
    const box = resultPanel(form);
    box.className = 'lf-result lf-result--fallback';
    const name = t('forms.form_names.' + formName(form));
    const text = buildText(t('forms.text_header', { form: name }), rows, `${t('forms.text_page')}: ${pageUrl()}`);
    const title = el('p', { className: 'lf-result__title', tabindex: '-1', text: t('forms.fallback_title') });
    const note = el('p', { className: 'lf-result__note', role: 'status' });
    box.appendChild(title);
    box.appendChild(el('p', { className: 'lf-result__text', text: t(reason === 'no_endpoint' ? 'forms.fallback_offline' : 'forms.fallback_error') }));
    box.appendChild(fallbackButtons(text, t('forms.email_subject', { form: name }), (msg) => { note.textContent = msg; }));
    box.appendChild(note);
    const details = el('details', { className: 'lf-result__details' }, [
      el('summary', { text: t('forms.summary_heading') }),
      el('pre', { className: 'lf-result__text-block', dir: 'auto', text }),
    ]);
    box.appendChild(details);
    setStatus(form, t('forms.fallback_title'));
    title.focus();
  }

  // ---------- отправка ----------
  function setBusy(form, busy) {
    form.__busy = busy;
    form.setAttribute('aria-busy', busy ? 'true' : 'false');
    form.querySelectorAll('[data-lf-submit]').forEach((b) => {
      b.disabled = busy;
      b.classList.toggle('is-busy', busy);
      const label = b.querySelector('.lf-submit__label');
      if (label) {
        if (busy) { b.__label = label.textContent; label.textContent = t('forms.sending'); } else if (b.__label) label.textContent = b.__label;
      }
    });
  }

  function onSubmit(e) {
    e.preventDefault();
    const form = e.currentTarget;
    if (form.__busy) return; // защита от двойной отправки
    applyConditions(form);
    const errors = validateForm(form);
    showSummary(form, errors);
    if (errors.length) return;
    const data = collect(form);
    const result = form.querySelector('.lf-result');
    if (result) { result.hidden = true; result.textContent = ''; }
    setBusy(form, true);
    setStatus(form, t('forms.sending'));
    saveDraft(form);
    submit({
      form: formName(form),
      elapsed_ms: Date.now() - (form.__t0 || Date.now()),
      hp: data.hp,
      consent: data.consent,
      fields: data.fields,
    }).then((res) => {
      setBusy(form, false);
      if (res.ok) showSuccess(form);
      else showFallback(form, data.rows, res.reason);
    });
  }

  /** Значения по умолчанию, зависящие от языка страницы (язык общения). */
  function applyDefaults(form) {
    form.querySelectorAll('select[name=preferred_language]').forEach((s) => {
      if (s.value || !s.required) return;
      const code = SITE.lang === 'ru' || SITE.lang === 'en' || SITE.lang === 'uk' ? SITE.lang : 'en';
      if (s.querySelector(`option[value="${code}"]`)) s.value = code;
    });
  }

  function enhanceForm(form) {
    if (form.__lf) return;
    form.__lf = true;
    form.__t0 = Date.now();
    restoreDraft(form);
    applyDefaults(form);
    const today = todayIso();
    form.querySelectorAll('input[type=date][data-min-today]').forEach((d) => { d.min = today; });
    initTabs(form);
    applyConditions(form);
    form.classList.add('is-enhanced');
    form.querySelectorAll('[data-lf-submit]').forEach((b) => { b.disabled = false; });

    let saveTimer = null;
    const onChange = (ev) => {
      const c = ev.target;
      if (!c || !c.name || c.name === 'homepage') return;
      if (c.type === 'radio' || c.tagName === 'SELECT' || c.type === 'checkbox') applyConditions(form);
      // поле с ошибкой перепроверяем на лету, чтобы ошибка исчезала сразу после исправления
      const box = c.type === 'radio' ? c.closest('.lf-group') : fieldBox(c);
      const group = c.closest('fieldset[data-require-one]');
      if (group && (group.classList.contains('has-error') || (box && box.classList.contains('has-error')))) validateBox(form, group);
      else if (box && box.classList.contains('has-error')) validateBox(form, box);
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => saveDraft(form), 300);
    };
    form.addEventListener('input', onChange);
    form.addEventListener('change', onChange);
    // проверка формата при уходе с заполненного поля
    form.addEventListener('focusout', (ev) => {
      const c = ev.target;
      if (!c || !c.name || !c.value || c.type === 'radio' || c.type === 'checkbox' || c.type === 'hidden') return;
      const group = c.closest('fieldset[data-require-one]');
      if (group) {
        const msg = checkControl(c);
        if (msg) markError(fieldBox(c), [c], msg); else clearBox(fieldBox(c));
        return;
      }
      validateBox(form, fieldBox(c));
    });
    form.addEventListener('submit', onSubmit);
  }

  function enhance(root) {
    (root || document).querySelectorAll('form[data-lead-form]').forEach(enhanceForm);
  }

  window.GRForms = {
    submit,
    fallbackLinks: links,
    fallbackButtons,
    enhance,
    utm,
    t,
    pure,
  };

  utm(); // фиксируем UTM уже на входе, даже если форму откроют на другой странице
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => enhance());
  else enhance();
})();
