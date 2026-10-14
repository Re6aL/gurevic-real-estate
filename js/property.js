/* ============================================================
   Страница объекта — прогрессивное улучшение серверной разметки:
   галерея (миниатюры, стрелки, клавиатура, свайп, счётчик), лайтбокс на <dialog>,
   копирование ID, карта-фасад (iframe Google Maps только по клику).
   Без JS: первое фото, миниатюры — ссылки на файлы, ссылка «Открыть в Google Maps».
   ============================================================ */
(function () {
  'use strict';

  var SITE = window.SITE || {};
  var U = SITE.util || {};
  var doc = document;
  var t = function (key, vars) { return SITE.t ? SITE.t(key, vars) : key; };
  var reduced = function () { return U.prefersReducedMotion ? U.prefersReducedMotion() : false; };

  function onReady(fn) {
    if (doc.readyState !== 'loading') fn();
    else doc.addEventListener('DOMContentLoaded', fn);
  }

  /* ---------------- галерея + лайтбокс ---------------- */
  function initGallery() {
    var gallery = doc.querySelector('[data-gallery]');
    if (!gallery) return;
    var main = gallery.querySelector('[data-gallery-main]');
    var slides = Array.prototype.slice.call(main.querySelectorAll('.gallery-slide'));
    var thumbs = Array.prototype.slice.call(gallery.querySelectorAll('[data-thumb]'));
    var counter = main.querySelector('[data-gallery-counter]');
    var zoom = main.querySelector('[data-gallery-open]');
    var navs = Array.prototype.slice.call(main.querySelectorAll('[data-gallery-dir]'));
    var total = slides.length;
    var current = 0;
    var rtl = SITE.dir === 'rtl';

    navs.forEach(function (b) { b.hidden = false; });
    if (zoom) zoom.hidden = false;

    function show(index, opts) {
      opts = opts || {};
      var next = (index + total) % total;
      if (next === current && !opts.force) return;
      slides.forEach(function (s, i) {
        var on = i === next;
        s.hidden = !on;
        s.classList.toggle('is-active', on);
        s.classList.remove('is-entering');
        if (on && !reduced() && !opts.instant) {
          void s.offsetWidth; // перезапуск анимации
          s.classList.add('is-entering');
        }
      });
      // соседние кадры — заранее, чтобы листание было без задержки
      [next + 1, next - 1].forEach(function (j) {
        var img = slides[(j + total) % total].querySelector('img');
        if (img && img.loading === 'lazy') img.loading = 'eager';
      });
      thumbs.forEach(function (th, i) {
        th.classList.toggle('active', i === next);
        if (i === next) th.setAttribute('aria-current', 'true');
        else th.removeAttribute('aria-current');
      });
      var thumb = thumbs[next];
      if (thumb && thumb.scrollIntoView && opts.scrollThumb !== false) {
        var list = thumb.closest('.gallery-thumbs');
        if (list) {
          var li = thumb.parentNode;
          if (list.scrollHeight > list.clientHeight + 2) list.scrollTop = li.offsetTop - list.clientHeight / 2 + li.offsetHeight / 2;
          if (list.scrollWidth > list.clientWidth + 2) {
            var left = li.offsetLeft - list.clientWidth / 2 + li.offsetWidth / 2;
            list.scrollLeft = rtl ? left - (list.scrollWidth - list.clientWidth) : left;
          }
        }
      }
      if (counter) counter.textContent = t('property.counter', { n: next + 1, total: total });
      current = next;
      if (lightbox && lightbox.open) fillLightbox();
    }

    thumbs.forEach(function (th) {
      th.addEventListener('click', function (e) {
        e.preventDefault();
        show(Number(th.dataset.thumb));
      });
    });
    navs.forEach(function (b) {
      b.addEventListener('click', function () { show(current + Number(b.dataset.galleryDir)); });
    });

    // клавиатура: стрелки внутри галереи (в RTL «вперёд» — влево)
    gallery.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      if (e.target.closest && e.target.closest('input, textarea, select')) return;
      e.preventDefault();
      var forward = (e.key === 'ArrowRight') !== rtl;
      show(current + (forward ? 1 : -1));
    });

    // свайп
    function swipe(el, handler) {
      var x0 = null, y0 = null;
      el.addEventListener('touchstart', function (e) { x0 = e.changedTouches[0].clientX; y0 = e.changedTouches[0].clientY; }, { passive: true });
      el.addEventListener('touchend', function (e) {
        if (x0 === null) return;
        var dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
        x0 = null;
        if (Math.abs(dx) < 45 || Math.abs(dx) < Math.abs(dy)) return;
        var forward = (dx < 0) !== rtl;
        handler(forward ? 1 : -1);
      }, { passive: true });
    }
    swipe(main, function (d) { show(current + d); });

    /* лайтбокс */
    var lightbox = doc.querySelector('[data-lightbox]');
    if (!lightbox || typeof lightbox.showModal !== 'function') {
      if (zoom) zoom.hidden = true;
      return;
    }
    var stage = lightbox.querySelector('[data-lightbox-stage]');
    var lbCounter = lightbox.querySelector('[data-lightbox-counter]');

    function fillLightbox() {
      var pic = slides[current].querySelector('picture, img');
      stage.textContent = '';
      if (pic) {
        var clone = pic.cloneNode(true);
        Array.prototype.forEach.call(clone.querySelectorAll ? clone.querySelectorAll('source, img') : [], function (n) { n.setAttribute('sizes', '100vw'); });
        if (clone.tagName === 'IMG') clone.setAttribute('sizes', '100vw');
        var img = clone.tagName === 'IMG' ? clone : clone.querySelector('img');
        if (img) { img.loading = 'eager'; img.removeAttribute('fetchpriority'); }
        stage.appendChild(clone);
      }
      if (lbCounter) lbCounter.textContent = total > 1 ? t('property.photo', { n: current + 1, total: total }) : '';
    }
    function open() {
      fillLightbox();
      lightbox.showModal();
      if (U.lockScroll) U.lockScroll();
    }
    lightbox.addEventListener('close', function () {
      if (U.unlockScroll) U.unlockScroll();
      if (zoom) zoom.focus();
    });
    if (zoom) zoom.addEventListener('click', open);
    lightbox.querySelector('[data-lightbox-close]').addEventListener('click', function () { lightbox.close(); });
    Array.prototype.forEach.call(lightbox.querySelectorAll('[data-lightbox-dir]'), function (b) {
      b.addEventListener('click', function () { show(current + Number(b.dataset.lightboxDir), { scrollThumb: false }); });
    });
    lightbox.addEventListener('click', function (e) {
      if (e.target === lightbox || e.target === stage) lightbox.close();
    });
    lightbox.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault();
      var forward = (e.key === 'ArrowRight') !== rtl;
      show(current + (forward ? 1 : -1), { scrollThumb: false });
    });
    swipe(lightbox, function (d) { show(current + d, { scrollThumb: false }); });
  }

  /* ---------------- копирование ID ---------------- */
  function initCopy() {
    var btn = doc.querySelector('[data-copy-id]');
    if (!btn || !U.copyText) return;
    var label = btn.querySelector('[data-copy-label]');
    var status = doc.querySelector('[data-copy-status]');
    var original = label.textContent;
    var timer = 0;
    btn.hidden = false;
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-copy-id');
      U.copyText(id).then(function (ok) {
        clearTimeout(timer);
        if (ok) {
          btn.classList.add('is-copied');
          label.textContent = t('property.copied');
          if (status) status.textContent = t('property.copied_status', { id: id });
        } else if (status) {
          status.textContent = t('property.copy_failed');
          label.textContent = t('property.copy_failed');
        }
        timer = setTimeout(function () {
          btn.classList.remove('is-copied');
          label.textContent = original;
          if (status) status.textContent = '';
        }, 2000);
      });
    });
  }

  /* ---------------- карта-фасад ---------------- */
  function initMap() {
    var facade = doc.querySelector('[data-map-facade]');
    if (!facade) return;
    var btn = facade.querySelector('[data-map-load]');
    if (!btn) return;
    btn.hidden = false;
    btn.addEventListener('click', function () {
      var frame = doc.createElement('iframe');
      frame.src = facade.getAttribute('data-src');
      frame.title = facade.getAttribute('data-title') || '';
      frame.loading = 'lazy';
      frame.referrerPolicy = 'no-referrer-when-downgrade';
      frame.setAttribute('allowfullscreen', '');
      facade.appendChild(frame);
      facade.classList.add('is-loaded');
      frame.setAttribute('tabindex', '0');
      frame.focus();
    });
  }

  onReady(function () {
    initGallery();
    initCopy();
    initMap();
  });
})();
