// ============================================================
// Gurevic Real Estate — чат-помощник (скриптованная анкета).
//
// Плавающая кнопка → диалог: цель → тип объекта → бюджет → район → контакт → имя →
// подтверждение с согласием → отправка тем же конвейером, что и формы
// (GRForms.submit, form = "chat", fields.transcript). Если эндпоинта нет или он
// недоступен — кнопки WhatsApp / Telegram / e-mail с готовым текстом.
// Все строки — SITE.i18n.chat (i18n/<lang>/chat.json → js); без них виджет не показывается.
// DOM панели строится при первом открытии; js/forms.js и css/forms.css догружаются сами,
// если страница их не подключила.
// Публичное API: window.Chat = { open(), close(), toggle() }; любой [data-chat-open] открывает чат.
// ============================================================

(function () {
  'use strict';

  const SITE = window.SITE;
  const S = SITE && SITE.i18n && SITE.i18n.chat;
  if (!S || !S.title || typeof document === 'undefined') return;

  const CONTACTS = SITE.contacts || {};
  const ROOT = SITE.root || '';
  const ASSETS = SITE.assets || {}; // { 'css/forms.css': '<relative url>?v=hash', … } — от генератора

  // ---------- сценарий (коды; подписи — chat.js.o.*) ----------
  const TYPES = {
    buy: ['apartment', 'house', 'land', 'undecided'],
    rent: ['apartment', 'house', 'undecided'],
    invest: ['hotel', 'land', 'commercial', 'development', 'undecided'],
    sell: ['apartment', 'house', 'land', 'construction_project', 'business'],
  };
  const BUDGETS = {
    buy: ['b_lt150', 'b_150_300', 'b_300_700', 'b_gt700'],
    rent: ['r_lt800', 'r_800_1500', 'r_gt1500'],
    invest: ['lt_500k', '500k_2m', '2m_10m', '10m_50m', 'gt_50m'],
  };
  const DISTRICTS = ['budva', 'becici', 'sveti_stefan', 'petrovac', 'boka', 'any'];
  const STEPS = ['goal', 'type', 'budget', 'district', 'contact', 'name', 'confirm'];
  // коды чата → поля заявки (brief §E)
  const INTEREST = { buy: 'buy', rent: 'rent', invest: 'invest', sell: 'sell', browse: 'other' };
  const INVEST_TYPE = { hotel: 'hotel', land: 'development_land', commercial: 'restaurant_commercial', development: 'development_partnership' };
  const OWNER_KIND = { apartment: 'apartment', house: 'house', land: 'land', construction_project: 'construction_project', business: 'business' };

  const ICONS = {
    chat: 'M4 5h16v11H10l-6 4zM8 10h.01M12 10h.01M16 10h.01',
    close: 'M6 6l12 12M18 6L6 18',
    restart: 'M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4',
    send: 'M3 11.5 21 3l-8.5 18-2-7.5z',
  };

  // ---------- утилиты ----------
  function t(path, params) {
    let node = S;
    for (const p of path.split('.')) node = node && typeof node === 'object' ? node[p] : undefined;
    if (typeof node !== 'string') return '';
    return params ? node.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : node;
  }

  function svg(name, cls) {
    const ns = 'http://www.w3.org/2000/svg';
    const s = document.createElementNS(ns, 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('width', '22');
    s.setAttribute('height', '22');
    s.setAttribute('aria-hidden', 'true');
    s.setAttribute('focusable', 'false');
    s.setAttribute('fill', 'none');
    s.setAttribute('stroke', 'currentColor');
    s.setAttribute('stroke-width', '1.9');
    s.setAttribute('stroke-linecap', 'round');
    s.setAttribute('stroke-linejoin', 'round');
    if (cls) s.setAttribute('class', cls);
    const p = document.createElementNS(ns, 'path');
    p.setAttribute('d', ICONS[name]);
    s.appendChild(p);
    return s;
  }

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    Object.keys(attrs || {}).forEach((k) => {
      const v = attrs[k];
      if (v == null || v === false) return;
      if (k === 'text') n.textContent = v;
      else if (k === 'className') n.className = v;
      else n.setAttribute(k, v === true ? '' : v);
    });
    (children || []).forEach((c) => { if (c) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }

  const reducedMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function privacyUrl() {
    if (SITE.privacyUrl) return SITE.privacyUrl;
    return ROOT + (SITE.lang && SITE.lang !== 'ru' ? SITE.lang + '/' : '') + 'privacy/';
  }

  /** Телефон / @telegram / e-mail из свободного текста; null — ничего не нашли. */
  function parseContact(text) {
    let s = String(text || '');
    const out = {};
    const email = s.match(/[^\s@,;:<>()]+@[^\s@,;:<>()]+\.[^\s@,;:<>()]{2,}/);
    if (email) { out.email = email[0]; s = s.replace(email[0], ' '); }
    const tg = s.match(/(?:t(?:elegram)?\.me\/|@)([A-Za-z][A-Za-z0-9_]{3,31})/i);
    if (tg) { out.telegram = '@' + tg[1]; s = s.replace(tg[0], ' '); }
    const phone = s.match(/\+?\d[\d\s().-]{5,}\d/);
    if (phone) {
      const digits = phone[0].replace(/\D/g, '');
      if (digits.length >= 7 && digits.length <= 15) out.phone = phone[0].trim();
    }
    return Object.keys(out).length ? out : null;
  }

  // ---------- загрузка зависимостей ----------
  let formsPromise = null;
  function ensureForms() {
    if (window.GRForms) return Promise.resolve(window.GRForms);
    if (!formsPromise) {
      formsPromise = new Promise((resolve) => {
        const s = document.createElement('script');
        s.src = ASSETS['js/forms.js'] || ROOT + 'js/forms.js';
        s.onload = () => resolve(window.GRForms || null);
        s.onerror = () => resolve(null);
        document.head.appendChild(s);
      });
    }
    return formsPromise;
  }

  function ensureCss(done) {
    const has = Array.prototype.some.call(document.querySelectorAll('link[rel=stylesheet]'), (l) => /(^|\/)css\/forms\.css(\?|$)/.test(l.getAttribute('href') || ''));
    if (has) { done(); return; }
    const link = el('link', { rel: 'stylesheet', href: ASSETS['css/forms.css'] || ROOT + 'css/forms.css' });
    link.addEventListener('load', done);
    link.addEventListener('error', done);
    document.head.appendChild(link);
  }

  // ---------- состояние ----------
  const ui = {};
  let state = null;

  function reset() {
    state = { step: -1, answers: {}, notes: [], transcript: [], t0: Date.now(), done: false, sending: false, expecting: null, timer: null };
  }

  // ---------- DOM ----------
  function buildFab() {
    const fab = el('button', {
      className: 'gchat-fab', type: 'button', 'aria-expanded': 'false', 'aria-controls': 'gr-chat',
      'aria-label': t('fab_open'), title: t('fab_open'),
    }, [svg('chat', 'gchat-fab__open'), svg('close', 'gchat-fab__close')]);
    fab.addEventListener('click', toggle);
    document.body.appendChild(fab);
    ui.fab = fab;
  }

  function buildPanel() {
    if (ui.panel) return;
    const restartBtn = el('button', { className: 'gchat-icon-btn', type: 'button', 'aria-label': t('restart'), title: t('restart') }, [svg('restart')]);
    const closeBtn = el('button', { className: 'gchat-icon-btn', type: 'button', 'aria-label': t('close'), title: t('close') }, [svg('close')]);
    const msgs = el('div', { className: 'gchat-msgs', role: 'log', 'aria-live': 'polite', 'aria-relevant': 'additions' });
    const replies = el('div', { className: 'gchat-replies' });
    const log = el('div', { className: 'gchat-log' }, [msgs, replies]);
    const input = el('input', {
      className: 'gchat-input', id: 'gr-chat-input', type: 'text', autocomplete: 'off', maxlength: '1000',
      dir: 'auto', placeholder: t('input_placeholder'),
    });
    const form = el('form', { className: 'gchat-input-row', novalidate: true }, [
      el('label', { className: 'lf-sr', for: 'gr-chat-input', text: t('input_label') }),
      input,
      el('button', { className: 'gchat-send', type: 'submit', 'aria-label': t('send'), title: t('send') }, [svg('send')]),
    ]);
    const panel = el('div', { className: 'gchat-panel', id: 'gr-chat', role: 'dialog', 'aria-modal': 'false', 'aria-labelledby': 'gr-chat-title', hidden: true }, [
      el('div', { className: 'gchat-head' }, [
        el('span', { className: 'gchat-ava', 'aria-hidden': 'true', text: t('avatar') || 'GR' }),
        el('div', { className: 'gchat-head__text' }, [
          el('p', { className: 'gchat-title', id: 'gr-chat-title', text: t('title') }),
          el('p', { className: 'gchat-sub', text: t('subtitle') }),
        ]),
        restartBtn,
        closeBtn,
      ]),
      log,
      form,
    ]);
    document.body.insertBefore(panel, ui.fab);
    Object.assign(ui, { panel, log, msgs, replies, input });
    closeBtn.addEventListener('click', () => close(true));
    restartBtn.addEventListener('click', restart);
    form.addEventListener('submit', (e) => { e.preventDefault(); sendFree(); });
    panel.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); close(true); }
    });
  }

  function scrollDown() {
    ui.log.scrollTop = ui.log.scrollHeight;
  }

  function addMsg(text, who) {
    const node = el('div', { className: 'gchat-msg gchat-msg--' + who, dir: who === 'user' ? 'auto' : null, text });
    ui.msgs.appendChild(node);
    state.transcript.push(`${who === 'user' ? t('you') : t('bot')}: ${text}`);
    scrollDown();
    return node;
  }

  /** Реплика помощника с короткой «печатью»; after() — когда сообщение появилось. */
  function botSay(text, after) {
    clearTimeout(state.timer);
    const typing = el('div', { className: 'gchat-typing', 'aria-hidden': 'true' }, [el('i'), el('i'), el('i')]);
    ui.msgs.appendChild(typing);
    scrollDown();
    const delay = reducedMotion() ? 120 : 420 + Math.random() * 280;
    const session = state;
    state.timer = setTimeout(() => {
      typing.remove();
      if (session !== state) return; // «начать заново» во время печати
      addMsg(text, 'bot');
      if (after) after();
    }, delay);
  }

  function clearReplies() {
    ui.replies.textContent = '';
  }

  function focusInPanel(node) {
    if (!ui.panel.hidden && node && (ui.panel.contains(document.activeElement) || document.activeElement === document.body || document.activeElement === ui.fab)) node.focus();
  }

  /** Кнопки быстрых ответов: [{code, text, primary}] */
  function showReplies(items, onPick) {
    clearReplies();
    const buttons = items.map((it) => {
      const b = el('button', { className: 'gchat-reply' + (it.primary ? ' gchat-reply--primary' : ''), type: 'button', text: it.text });
      b.addEventListener('click', () => onPick(it));
      ui.replies.appendChild(b);
      return b;
    });
    scrollDown();
    focusInPanel(buttons[0]);
  }

  // ---------- сценарий ----------
  function goal() {
    const g = state.answers.goal && state.answers.goal.code;
    return g === 'browse' ? 'buy' : g;
  }

  /** Вопрос и варианты шага; null — шаг пропускается. */
  function stepDef(key) {
    const g = goal();
    const opt = (group, codes) => codes.map((c) => ({ code: c, text: t(`o.${group}.${c}`) }));
    switch (key) {
      case 'goal':
        return { q: t('q.goal'), options: opt('goal', ['buy', 'rent', 'invest', 'sell', 'browse']) };
      case 'type':
        return { q: t(g === 'sell' ? 'q.type_sell' : 'q.type'), options: opt('type', TYPES[g] || TYPES.buy) };
      case 'budget':
        if (g === 'sell') return { q: t('q.price_sell'), options: [{ code: 'skip', text: t('o.skip') }], free: true };
        return { q: t('q.budget_' + (BUDGETS[g] ? g : 'buy')), options: opt('budget', BUDGETS[g] || BUDGETS.buy), free: true };
      case 'district':
        return { q: t(g === 'sell' ? 'q.district_sell' : 'q.district'), options: opt('district', g === 'sell' ? DISTRICTS.slice(0, -1) : DISTRICTS), free: true };
      case 'contact':
        return { q: t('q.contact'), options: [], free: true };
      case 'name':
        return { q: t('q.name'), options: [{ code: 'skip', text: t('o.skip') }], free: true };
      default:
        return null;
    }
  }

  function next() {
    state.step += 1;
    const key = STEPS[state.step];
    if (!key) return;
    if (key === 'confirm') { askConfirm(); return; }
    const def = stepDef(key);
    if (!def) { next(); return; }
    state.expecting = key;
    botSay(def.q, () => {
      if (def.options.length) showReplies(def.options, (it) => answer(key, it.code, it.text));
      else { clearReplies(); focusInPanel(ui.input); }
    });
  }

  function answer(key, code, text) {
    if (state.expecting !== key) return;
    clearReplies();
    addMsg(text, 'user');
    if (key === 'contact') {
      const parsed = parseContact(text);
      if (!parsed) {
        botSay(t('q.contact_invalid'), () => focusInPanel(ui.input));
        return;
      }
      state.answers.contact = { code: null, text, fields: parsed };
    } else {
      state.answers[key] = { code: code === 'skip' ? null : code, text: code === 'skip' ? '' : text };
    }
    state.expecting = null;
    next();
  }

  function sendFree() {
    const text = ui.input.value.trim();
    if (!text || state.sending) return;
    ui.input.value = '';
    if (state.expecting) { answer(state.expecting, null, text); return; }
    addMsg(text, 'user');
    if (state.done) {
      botSay(t('after'), () => showChannels(leadText()));
      return;
    }
    state.notes.push(text);
    botSay(t('q.free_note'));
  }

  function summaryRows() {
    const a = state.answers;
    const g = goal();
    const rows = [];
    const add = (label, v) => { if (v) rows.push([label, v]); };
    add(t('summary.goal'), a.goal && a.goal.text);
    add(t('summary.type'), a.type && a.type.text);
    add(t(g === 'sell' ? 'summary.price' : 'summary.budget'), a.budget && a.budget.text);
    add(t('summary.district'), a.district && a.district.text);
    add(t('summary.contact'), a.contact && a.contact.text);
    add(t('summary.name'), a.name && a.name.text);
    if (state.notes.length) add(t('summary.notes'), state.notes.join('\n'));
    return rows;
  }

  function rowsText(rows) {
    return rows.map(([k, v]) => `${k}: ${v}`).join('\n');
  }

  function leadText() {
    const page = SITE.url || location.href.split('#')[0];
    return `${t('lead_title')}\n\n${rowsText(summaryRows())}\n\n${page}`;
  }

  function askConfirm() {
    state.expecting = null;
    botSay(`${t('q.confirm')}\n${rowsText(summaryRows())}`, () => {
      const consent = el('p', { className: 'gchat-consent' }, [
        t('consent_text') + ' ',
        el('a', { href: privacyUrl(), target: '_blank', rel: 'noopener', text: t('consent_link') }),
      ]);
      ui.msgs.appendChild(consent);
      showReplies([
        { code: 'send', text: t('submit'), primary: true },
        { code: 'edit', text: t('edit') },
      ], (it) => (it.code === 'send' ? sendLead() : restart()));
    });
  }

  function buildFields() {
    const a = state.answers;
    const g = a.goal && a.goal.code;
    const fields = {
      interest: INTEREST[g] || 'other',
      message: rowsText(summaryRows()),
      transcript: state.transcript.join('\n'),
    };
    if (a.name && a.name.text) fields.name = a.name.text.slice(0, 200);
    if (a.contact) Object.assign(fields, a.contact.fields);
    const type = a.type && a.type.code;
    if (g === 'invest') {
      if (INVEST_TYPE[type]) fields.investment_type = INVEST_TYPE[type];
      if (a.budget && a.budget.code && BUDGETS.invest.indexOf(a.budget.code) !== -1) fields.budget = a.budget.code;
    }
    if (g === 'sell' && OWNER_KIND[type]) fields.property_kind = OWNER_KIND[type];
    return fields;
  }

  function sendLead() {
    if (state.sending || state.done) return;
    state.sending = true;
    clearReplies();
    addMsg(t('submit'), 'user');
    const fields = buildFields();
    const status = addMsg(t('sending'), 'bot');
    ensureForms().then((F) => {
      if (!F) return { ok: false, reason: 'no_forms' };
      return F.submit({
        form: 'chat',
        elapsed_ms: Date.now() - state.t0,
        hp: '',
        consent: true,
        fields,
      });
    }).then((res) => {
      status.remove();
      state.transcript.pop();
      state.sending = false;
      state.done = true;
      botSay(t(res && res.ok ? 'sent' : 'fallback'), () => showChannels(leadText()));
    });
  }

  /** Кнопки WhatsApp / Telegram / e-mail / копировать с готовым текстом запроса. */
  function showChannels(text) {
    clearReplies();
    const labels = {
      channel_whatsapp: t('whatsapp'), channel_telegram: t('telegram'), channel_email: t('email'), channel_copy: t('copy'),
      copied: t('copied'), telegram_note: t('copied'), copy_failed: t('copy_failed'),
    };
    const note = el('p', { className: 'gchat-consent', role: 'status' });
    const render = (F) => {
      let wrap;
      if (F && F.fallbackButtons) {
        wrap = F.fallbackButtons(text, t('email_subject'), (msg) => { note.textContent = msg; }, labels);
      } else {
        // forms.js не загрузился — простые ссылки
        wrap = el('div', { className: 'lf-channels' });
        const wa = String(CONTACTS.whatsapp || '').replace(/\/+$/, '');
        if (wa) wrap.appendChild(el('a', { className: 'lf-channel', href: `${wa}?text=${encodeURIComponent(text)}`, target: '_blank', rel: 'noopener', text: labels.channel_whatsapp }));
        if (CONTACTS.telegram) wrap.appendChild(el('a', { className: 'lf-channel', href: CONTACTS.telegram, target: '_blank', rel: 'noopener', text: labels.channel_telegram }));
        if (CONTACTS.email) wrap.appendChild(el('a', { className: 'lf-channel', href: `mailto:${CONTACTS.email}?subject=${encodeURIComponent(t('email_subject'))}&body=${encodeURIComponent(text.slice(0, 1800))}`, text: labels.channel_email }));
      }
      ui.replies.appendChild(wrap);
      ui.replies.appendChild(note);
      scrollDown();
      focusInPanel(wrap.querySelector('a, button'));
    };
    ensureForms().then(render);
  }

  // ---------- открытие / закрытие ----------
  function open() {
    if (!ui.fab) return;
    buildPanel();
    if (!ui.panel.hidden) return;
    ui.panel.hidden = false;
    ui.fab.setAttribute('aria-expanded', 'true');
    ui.fab.setAttribute('aria-label', t('fab_close'));
    ui.fab.title = t('fab_close');
    document.body.classList.add('gchat-is-open');
    if (!state) reset();
    if (state.step < 0) next();
    else {
      const first = ui.replies.querySelector('button, a');
      (first || ui.input).focus();
    }
    if (!window.GRForms) ensureForms(); // заранее, чтобы отправка не ждала загрузки
  }

  function close(returnFocus) {
    if (!ui.panel || ui.panel.hidden) return;
    ui.panel.hidden = true;
    ui.fab.setAttribute('aria-expanded', 'false');
    ui.fab.setAttribute('aria-label', t('fab_open'));
    ui.fab.title = t('fab_open');
    document.body.classList.remove('gchat-is-open');
    if (returnFocus) ui.fab.focus();
  }

  function toggle() {
    if (ui.panel && !ui.panel.hidden) close(true);
    else open();
  }

  function restart() {
    if (state && state.sending) return;
    clearTimeout(state && state.timer);
    reset();
    ui.msgs.textContent = '';
    clearReplies();
    next();
  }

  function init() {
    ensureCss(buildFab);
    document.addEventListener('click', (e) => {
      const trigger = e.target.closest && e.target.closest('[data-chat-open]');
      if (!trigger) return;
      e.preventDefault();
      open();
    });
  }

  window.Chat = { open, close: () => close(false), toggle };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
