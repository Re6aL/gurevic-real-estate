/* Optional analytics is loaded only after an explicit, revocable choice. */
(() => {
  'use strict';
  const S = window.SITE || {}, config = S.analytics || {};
  const panel = document.querySelector('[data-consent-panel]');
  if (!panel) return;
  const key = 'gre_analytics_consent_v1';
  let allowed = false, loaded = false;
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window.gtag('consent', 'default', {analytics_storage:'denied', ad_storage:'denied', ad_user_data:'denied', ad_personalization:'denied'});
  function script(src) { const el = document.createElement('script'); el.src = src; el.async = true; document.head.append(el); }
  function load() {
    if (loaded || !allowed) return;
    loaded = true;
    window.gtag('consent', 'update', {analytics_storage:'granted'});
    const cleanUrl = location.origin + location.pathname;
    let referrer = '';
    try { referrer = new URL(document.referrer).origin; } catch (_) {}
    if (/^GTM-[A-Z0-9]+$/.test(config.gtm || '')) {
      window.dataLayer.push({'gtm.start':Date.now(), event:'gtm.js'});
      script('https://www.googletagmanager.com/gtm.js?id=' + config.gtm);
    } else if (/^G-[A-Z0-9]+$/.test(config.ga4 || '')) {
      script('https://www.googletagmanager.com/gtag/js?id=' + config.ga4);
      window.gtag('js', new Date());
      window.gtag('config', config.ga4, {page_location:cleanUrl, page_referrer:referrer, allow_google_signals:false, allow_ad_personalization_signals:false});
    }
    if (/^\d+$/.test(String(config.metrica || ''))) {
      window.ym = window.ym || function () { (window.ym.a = window.ym.a || []).push(arguments); };
      window.ym.l = Date.now();
      script('https://mc.yandex.ru/metrika/tag.js');
      window.ym(Number(config.metrica), 'init', {webvisor:false, clickmap:false, trackLinks:false, accurateTrackBounce:true, url:cleanUrl, referrer});
    }
  }
  function choose(value) {
    const wasLoaded = loaded;
    allowed = value;
    try { localStorage.setItem(key, JSON.stringify({allowed, time:Date.now()})); } catch (_) {}
    panel.hidden = true;
    if (allowed) load();
    else {
      window.gtag('consent', 'update', {analytics_storage:'denied',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'});
      if (window.ym && config.metrica) window.ym(Number(config.metrica), 'destruct');
      for (const cookie of document.cookie.split(';')) {
        const name = cookie.split('=')[0].trim();
        if (!/^(_ga|_gid|_gat|_ym_)/.test(name)) continue;
        const parts = location.hostname.split('.');
        for (let i = 0; i < parts.length - 1; i++) {
          document.cookie = `${name}=; Max-Age=0; path=/; domain=.${parts.slice(i).join('.')}`;
        }
        document.cookie = `${name}=; Max-Age=0; path=/`;
      }
      if (wasLoaded) location.reload();
    }
    document.querySelector('[data-consent-open]')?.focus();
  }
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (saved && Date.now() - saved.time < 180 * 86400000) { allowed = saved.allowed === true; panel.hidden = true; }
    else panel.hidden = false;
  } catch (_) { panel.hidden = false; }
  panel.querySelector('[data-consent-accept]').addEventListener('click', () => choose(true));
  panel.querySelector('[data-consent-reject]').addEventListener('click', () => choose(false));
  document.querySelectorAll('[data-consent-open]').forEach(button => button.addEventListener('click', () => {
    panel.hidden = false; panel.querySelector('button').focus();
  }));
  S.track = function (event) {
    if (!allowed || !['lead_sent','contact_click','property_view'].includes(event)) return;
    // Never transmit form values, contact details, query parameters or CRM data.
    window.gtag('event', event, {page_location:location.origin + location.pathname, language:S.lang});
    if (window.ym && config.metrica) window.ym(Number(config.metrica), 'reachGoal', event);
  };
  load();
})();
