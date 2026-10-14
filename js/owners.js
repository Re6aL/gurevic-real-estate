// ============================================================
// Владельцам (/owners/ и подстраницы).
// Кнопки [data-contract-request="sale|business"] («Запросить образец договора») ведут к форме
// заявки владельца (#owner-form) и дописывают в поле «сообщение» готовый запрос
// (тексты — SITE.i18n.owners: contract_request_sale / contract_request_business).
// Без JS кнопка остаётся обычной ссылкой-якорем на форму.
// ============================================================

(function () {
  'use strict';

  var SITE = window.SITE || {};

  function text(key) {
    if (typeof SITE.t === 'function') {
      var v = SITE.t('owners.' + key);
      if (v && v !== 'owners.' + key) return v;
    }
    var ns = SITE.i18n && SITE.i18n.owners;
    return ns && typeof ns[key] === 'string' ? ns[key] : '';
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function fire(el, type) {
    el.dispatchEvent(new Event(type, { bubbles: true }));
  }

  function requestContract(kind, trigger) {
    var section = document.getElementById('owner-form');
    var form = section && section.querySelector('form[data-form="owner"]');
    if (!form) return false;
    var body = form.querySelector('.lf-body');
    // форма уже отправлена (виден результат) — просто прокручиваем к ней
    var message = body && !body.hidden ? form.querySelector('textarea[name="message"]') : null;
    var phrase = text('contract_request_' + kind);

    if (message && phrase && message.value.indexOf(phrase) === -1) {
      var current = message.value.replace(/\s+$/, '');
      message.value = current ? current + '\n' + phrase : phrase;
      fire(message, 'input');
    }
    if (kind === 'business') {
      var checked = form.querySelector('input[name="property_kind"]:checked');
      var business = form.querySelector('input[name="property_kind"][value="business"]');
      if (!checked && business) {
        business.checked = true;
        fire(business, 'change');
      }
    }

    section.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' });
    var target = message || form;
    if (target === form && !form.hasAttribute('tabindex')) form.setAttribute('tabindex', '-1');
    try {
      target.focus({ preventScroll: true });
    } catch (e) {
      target.focus();
    }
    if (trigger && history.replaceState) {
      try { history.replaceState(null, '', '#owner-form'); } catch (e) { /* file:// и т. п. */ }
    }
    return true;
  }

  function init() {
    document.addEventListener('click', function (e) {
      var trigger = e.target.closest && e.target.closest('[data-contract-request]');
      if (!trigger) return;
      if (requestContract(trigger.getAttribute('data-contract-request') || 'sale', trigger)) e.preventDefault();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
