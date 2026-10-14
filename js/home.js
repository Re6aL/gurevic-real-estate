/* ============================================================
   Главная: hero-слайдер (кроссфейд 1 с, смена ~7 с) + уборка заставки.
   Заставку включает и пропускает инлайн-скрипт в <head>, анимирует CSS (css/home.css).
   Автосмена — только без prefers-reduced-motion; пауза, когда вкладка скрыта,
   hero вне экрана или нажата кнопка паузы. Тексты — SITE.t('home.*').
   ============================================================ */
(function () {
  'use strict';

  var SITE = window.SITE || {};
  var doc = document;
  var root = doc.documentElement;
  var util = SITE.util || {};
  var t = SITE.t || function (k) { return k; };
  var INTERVAL = 7000;
  var FADE = 1000;
  var SPLASH_MS = 2600;

  var splashOn = root.classList.contains('splash-on');
  var splash = doc.querySelector('[data-splash]');
  if (splash) {
    if (splashOn) setTimeout(function () { splash.parentNode && splash.parentNode.removeChild(splash); }, SPLASH_MS + 100);
    else splash.parentNode.removeChild(splash);
  }

  var hero = doc.querySelector('[data-hero]');
  if (!hero) return;
  var slides = [].slice.call(hero.querySelectorAll('[data-slide]'));
  var n = slides.length;
  if (n < 2) return;

  var controls = hero.querySelector('[data-hero-controls]');
  var dots = [].slice.call(hero.querySelectorAll('[data-hero-dot]'));
  var toggle = hero.querySelector('[data-hero-toggle]');
  var reduced = util.prefersReducedMotion ? util.prefersReducedMotion()
    : !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  var idx = 0;
  var want = 0;
  var timer = null;
  var prevTimer = null;
  var userPaused = reduced;
  var inView = true;

  function prime(i) { slides[i].classList.add('is-primed'); }

  // ждём загрузки (lazy) картинки слайда, затем вызываем cb
  function whenReady(i, cb) {
    var img = slides[i].querySelector('img');
    prime(i);
    if (!img || (img.complete && img.naturalWidth)) { cb(); return; }
    var done = false;
    function go() { if (!done) { done = true; cb(); } }
    img.addEventListener('load', go);
    img.addEventListener('error', go);
  }

  function render() {
    slides.forEach(function (s, i) {
      if (i === idx) s.removeAttribute('aria-hidden');
      else s.setAttribute('aria-hidden', 'true');
    });
    dots.forEach(function (d, i) {
      if (i === idx) d.setAttribute('aria-current', 'true');
      else d.removeAttribute('aria-current');
    });
  }

  function show(i) {
    i = (i + n) % n;
    want = i;
    if (i === idx) return;
    whenReady(i, function () {
      if (want !== i || i === idx) return;
      var old = slides[idx];
      slides.forEach(function (s) { s.classList.remove('is-prev'); });
      old.classList.remove('is-active');
      old.classList.add('is-prev');           // старый кадр держится под новым, пока тот проявляется
      slides[i].classList.add('is-active');
      idx = i;
      render();
      clearTimeout(prevTimer);
      prevTimer = setTimeout(function () { old.classList.remove('is-prev'); }, FADE + 50);
      prime((idx + 1) % n);
      schedule();
    });
  }

  function running() { return !userPaused && !doc.hidden && inView; }

  function schedule(delay) {
    clearTimeout(timer);
    timer = null;
    if (running()) timer = setTimeout(function () { show(idx + 1); }, delay || INTERVAL);
  }

  function setPaused(p) {
    userPaused = p;
    if (toggle) {
      toggle.classList.toggle('is-paused', p);
      toggle.setAttribute('aria-label', t(p ? 'home.play' : 'home.pause'));
    }
    schedule();
  }

  if (controls) {
    controls.hidden = false;
    controls.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button') : null;
      if (!b) return;
      if (b.hasAttribute('data-hero-prev')) show(idx - 1);
      else if (b.hasAttribute('data-hero-next')) show(idx + 1);
      else if (b.hasAttribute('data-hero-dot')) show(parseInt(b.getAttribute('data-hero-dot'), 10) || 0);
      else if (b === toggle) setPaused(!userPaused);
    });
  }
  if (toggle && reduced) toggle.hidden = true;   // без автосмены кнопка паузы не нужна

  doc.addEventListener('visibilitychange', function () { schedule(); });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      var v = entries[0].isIntersecting;
      if (v !== inView) { inView = v; schedule(); }
    }).observe(hero);
  }

  // следующий кадр подгружаем после load страницы (не мешает LCP)
  function primeNext() { prime(1); }
  if (doc.readyState === 'complete') primeNext();
  else window.addEventListener('load', primeNext);

  render();
  schedule(splashOn ? INTERVAL + SPLASH_MS : INTERVAL);
})();
