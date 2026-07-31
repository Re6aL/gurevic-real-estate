// ============================================================
// Gurevic Real Estate — страница объекта (object.html?id=...)
// Галерея-плейсхолдер, описание, параметры, варианты квартир
// для комплексов (в духе adriaticdreamestate /unique/29)
// ============================================================

(function () {
  const root = document.getElementById('obj-root');
  const id = new URLSearchParams(location.search).get('id');
  const l = LISTINGS.find(x => x.id === id);

  if (!l) {
    root.innerHTML = `<div class="empty-state" style="padding:80px 20px">
      Объект не найден. <a href="index.html" style="color:var(--sea)">Вернуться в каталог</a></div>`;
    return;
  }

  document.title = `${l.title} — Gurevic Real Estate`;

  const images = Array.isArray(l.images) ? l.images : [];
  const fallbackImage = listingPlaceholderImage(l);
  const features = Array.isArray(l.features) ? l.features.filter(Boolean) : [];
  const thumbs = images.length
    ? images.map((src, i) => `<button class="gallery-image-thumb ${i === 0 ? 'active' : ''}" type="button" data-i="${i}" aria-label="Показать фото ${i + 1} из ${images.length}"><img src="${src}" alt="Фото ${i + 1} объекта" loading="lazy"></button>`).join('')
    : `<div class="gallery-image-thumb active listing-illustration"><img src="${fallbackImage}" alt="Иллюстрация объекта"></div>`;
  const galleryControls = images.length > 1 ? `
    <button class="gallery-nav gallery-nav--prev" type="button" data-gallery-dir="-1" aria-label="Предыдущее фото">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4-8 8 8 8"/></svg>
    </button>
    <button class="gallery-nav gallery-nav--next" type="button" data-gallery-dir="1" aria-label="Следующее фото">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 4 8 8-8 8"/></svg>
    </button>
    <span class="gallery-counter" aria-live="polite">1 / ${images.length}</span>` : '';
  const galleryPlayControl = images.length > 1 ? `
    <button class="gallery-play" type="button" aria-label="Возобновить слайд-шоу" title="Возобновить слайд-шоу" hidden>
      <span class="gallery-play-icon" aria-hidden="true"></span>
      <span>Слайд-шоу</span>
    </button>` : '';
  const lightbox = images.length ? `
    <div class="photo-lightbox" id="photo-lightbox" role="dialog" aria-modal="true"
         aria-label="Просмотр фотографий" aria-hidden="true">
      <button class="photo-lightbox-close" type="button" aria-label="Закрыть просмотр"></button>
      ${images.length > 1 ? `
        <button class="photo-lightbox-nav photo-lightbox-prev" type="button" data-lightbox-dir="-1" aria-label="Предыдущее фото">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4-8 8 8 8"/></svg>
        </button>
        <button class="photo-lightbox-nav photo-lightbox-next" type="button" data-lightbox-dir="1" aria-label="Следующее фото">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 4 8 8-8 8"/></svg>
        </button>` : ''}
      <img class="photo-lightbox-image" src="${images[0]}" alt="Фото 1 объекта">
      <span class="photo-lightbox-counter" aria-live="polite">1 / ${images.length}</span>
    </div>` : '';

  const params = [
    ['Сделка', DICT.deal[l.deal]],
    ['Тип', DICT.type[l.type]],
    ['Район', l.location],
    l.area && ['Площадь', l.areaNote || l.area + ' м²'],
    l.landArea && ['Участок', l.landArea + ' м²'],
    l.rooms && ['Комнат', l.rooms],
    ['Цена', fmtPrice(l)],
  ].filter(Boolean);

  const bedrooms = r => { const m = String(r).match(/^\d+/); return m ? m[0] : r; };
  const unitsBlock = l.units ? `
    <h2>Доступные варианты в комплексе</h2>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:4px">
      ${l.units.filter(u => u.status === 'available').length} свободно из ${l.units.length}. Выберите планировку — этаж, спальни, площадь:</p>
    <div class="unit-cards">
      ${l.units.map(u => `
        <div class="unit-card">
          <div class="u-top">
            <span class="u-code">${u.name}</span>
            <span class="u-tag">${DICT.type[l.type] || 'Квартира'}</span>
          </div>
          <div class="u-grid">
            <div><span>Этаж:</span> <b>${u.floor}</b></div>
            <div><span>Спальни:</span> <b>${bedrooms(u.rooms)}</b></div>
            <div><span>Площадь:</span> <b>${u.area} м²</b></div>
            <div><span class="status-pill status-${u.status}">${u.status === 'available' ? 'Свободно' : 'Резерв'}</span></div>
          </div>
          <div class="u-foot">
            <span class="u-price">€${u.price.toLocaleString('ru-RU').replace(/,/g, ' ')}</span>
            <button class="btn" onclick="Chat.open()">Оставить запрос</button>
          </div>
        </div>`).join('')}
    </div>` : '';

  const [lat, lng] = objCoords(l);
  const mapNote = l.coords
    ? `📍 ${l.location}, Черногория — геолокация объекта из базы`
    : `📍 ${l.location}, Черногория — район указан приблизительно; точный адрес уточняйте у риелтора`;
  const mapBlock = `
    <h2>Расположение на карте</h2>
    <div class="obj-map">
      <iframe loading="lazy" referrerpolicy="no-referrer-when-downgrade"
        src="https://www.google.com/maps?q=${lat},${lng}&z=15&output=embed"></iframe>
      <div class="map-note">${mapNote}</div>
    </div>`;

  const similar = LISTINGS
    .filter(x => x.id !== l.id && !x.invest && (x.type === l.type || x.deal === l.deal))
    .slice(0, 3);

  root.innerHTML = `
    <div class="breadcrumbs"><a href="index.html">Главная</a> / <a href="index.html#catalog">Каталог</a> / ${l.title}</div>

    ${l.placeholder ? `<div class="demo-note">⚠ Демо-объект: описание и цифры вымышленные —
      сюда нужно будет поместить настоящее предложение.</div>` : ''}

    <div class="obj-head">
      <div>
        <h1>${l.title}</h1>
        <div class="card-loc" style="margin-top:4px">${l.location}, Черногория</div>
      </div>
      <div class="obj-price"><b>${fmtPrice(l)}</b>${(l.price > 0 && l.area) ? `<span>${Math.round(l.price / l.area).toLocaleString('ru-RU')} €/м²</span>` : ''}</div>
    </div>

    <div class="gallery">
      <div id="gallery-main" class="gallery-main" tabindex="${images.length ? '0' : '-1'}">
        ${images.length ? `<img class="gallery-main-image is-current" src="${images[0]}" alt="Фото 1 объекта">` : `<img class="gallery-main-image is-current listing-illustration" src="${fallbackImage}" alt="Иллюстрация объекта">`}
        ${galleryControls}
      </div>
      <div class="gallery-thumbs">${thumbs}</div>
      ${galleryPlayControl}
    </div>
    ${lightbox}

    <div class="obj-layout">
      <div class="obj-desc">
        <h2>Описание</h2>
        ${l.desc.split('\n\n').map(p => `<p>${p}</p>`).join('')}
        ${features.length ? `<h2>Особенности</h2>
        <div class="features">${features.map(f => `<span class="feature-chip">${f}</span>`).join('')}</div>` : ''}
        ${unitsBlock}
        ${mapBlock}
      </div>

      <aside class="obj-side">
        <div class="side-card">
          <h3>Параметры</h3>
          <table class="params-table">
            ${params.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}
          </table>
        </div>
        <div class="side-card">
          <div class="agent-row">
            <div class="agent-ava">GR</div>
            <div><b>Gurevic Real Estate</b><span>риелтор · Будва</span></div>
          </div>
          <button class="btn" onclick="Chat.open()">💬 Спросить в чате</button>
          <a class="btn btn-outline" href="tel:+38269572257">📞 Позвонить</a>
          <a class="btn btn-navy" href="https://wa.me/38269572257?text=${encodeURIComponent('Здравствуйте! Интересует объект: ' + l.title)}" target="_blank" rel="noopener">WhatsApp</a>
        </div>
      </aside>
    </div>

    ${similar.length ? `
    <section class="section">
      <div class="section-head"><h2>Похожие объекты</h2></div>
      <div class="cards">${similar.map(cardHTML).join('')}</div>
    </section>` : ''}
  `;

  // Галерея: автоматическое слайд-шоу до первого ручного действия пользователя.
  if (images.length) {
    const galleryMain = document.getElementById('gallery-main');
    const gallery = galleryMain.closest('.gallery');
    const galleryThumbs = root.querySelector('.gallery-thumbs');
    const counter = galleryMain.querySelector('.gallery-counter');
    const playButton = gallery.querySelector('.gallery-play');
    const lightbox = document.getElementById('photo-lightbox');
    const lightboxImage = lightbox.querySelector('.photo-lightbox-image');
    const lightboxCounter = lightbox.querySelector('.photo-lightbox-counter');
    const lightboxClose = lightbox.querySelector('.photo-lightbox-close');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let currentIndex = 0;
    let lightboxIndex = 0;
    let timer = 0;
    let transitionLocked = false;
    let touchStartX = null;
    let lightboxTouchStartX = null;
    let focusBeforeLightbox = null;

    function stopSlideshow() {
      window.clearInterval(timer);
      timer = 0;
      galleryMain.classList.add('is-manual');
      if (playButton) {
        playButton.hidden = false;
        positionPlayButton(currentIndex);
      }
    }

    function startSlideshow() {
      window.clearInterval(timer);
      galleryMain.classList.remove('is-manual');
      if (playButton) playButton.hidden = true;
      timer = window.setInterval(() => showPhoto(currentIndex + 1, 1, false), 5500);
    }

    function syncThumbHeight() {
      if (window.innerWidth <= 960) {
        galleryThumbs.style.height = '';
        positionPlayButton(currentIndex);
        return;
      }
      galleryThumbs.style.height = `${galleryMain.getBoundingClientRect().height}px`;
      positionPlayButton(currentIndex);
    }

    function positionPlayButton(index) {
      if (!playButton || playButton.hidden) return;
      const thumb = root.querySelectorAll('.gallery-image-thumb')[index];
      if (!thumb) return;
      window.requestAnimationFrame(() => {
        const galleryRect = gallery.getBoundingClientRect();
        const thumbRect = thumb.getBoundingClientRect();
        playButton.style.left = `${thumbRect.left - galleryRect.left + thumbRect.width / 2}px`;
        playButton.style.top = `${thumbRect.top - galleryRect.top + thumbRect.height / 2}px`;
      });
    }

    function setActiveThumb(index) {
      root.querySelectorAll('.gallery-image-thumb').forEach((thumb, i) => {
        thumb.classList.toggle('active', i === index);
        if (i === index) {
          if (window.innerWidth <= 960) {
            const left = thumb.offsetLeft;
            const right = left + thumb.offsetWidth;
            if (left < galleryThumbs.scrollLeft) galleryThumbs.scrollLeft = left;
            else if (right > galleryThumbs.scrollLeft + galleryThumbs.clientWidth) {
              galleryThumbs.scrollLeft = right - galleryThumbs.clientWidth;
            }
          } else {
            const top = thumb.offsetTop;
            const bottom = top + thumb.offsetHeight;
            if (top < galleryThumbs.scrollTop) galleryThumbs.scrollTop = top;
            else if (bottom > galleryThumbs.scrollTop + galleryThumbs.clientHeight) {
              galleryThumbs.scrollTop = bottom - galleryThumbs.clientHeight;
            }
          }
        }
      });
      if (counter) counter.textContent = `${index + 1} / ${images.length}`;
      positionPlayButton(index);
    }

    function showPhoto(index, direction = 1, manual = false) {
      if (manual) stopSlideshow();
      const nextIndex = (index + images.length) % images.length;
      if (nextIndex === currentIndex || transitionLocked) {
        setActiveThumb(nextIndex);
        return;
      }

      const current = galleryMain.querySelector('.gallery-main-image.is-current');
      const next = document.createElement('img');
      next.className = `gallery-main-image is-next ${direction < 0 ? 'from-left' : 'from-right'}`;
      next.src = images[nextIndex];
      next.alt = `Фото ${nextIndex + 1} объекта`;

      const animate = () => {
        transitionLocked = true;
        galleryMain.insertBefore(next, galleryMain.firstChild);
        if (reduceMotion.matches) {
          current.remove();
          next.className = 'gallery-main-image is-current';
          transitionLocked = false;
        } else {
          requestAnimationFrame(() => {
            next.classList.add('is-active');
            current.classList.add(direction < 0 ? 'leave-right' : 'leave-left');
          });
          window.setTimeout(() => {
            current.remove();
            next.className = 'gallery-main-image is-current';
            transitionLocked = false;
          }, 620);
        }
        currentIndex = nextIndex;
        setActiveThumb(currentIndex);
      };

      if (next.complete) animate();
      else next.addEventListener('load', animate, { once: true });
    }

    function updateLightbox(index) {
      lightboxIndex = (index + images.length) % images.length;
      lightboxImage.src = images[lightboxIndex];
      lightboxImage.alt = `Фото ${lightboxIndex + 1} объекта`;
      lightboxCounter.textContent = `${lightboxIndex + 1} / ${images.length}`;
      showPhoto(lightboxIndex, lightboxIndex >= currentIndex ? 1 : -1, true);
    }

    function openLightbox() {
      stopSlideshow();
      focusBeforeLightbox = document.activeElement;
      updateLightbox(currentIndex);
      lightbox.classList.add('open');
      lightbox.setAttribute('aria-hidden', 'false');
      document.body.classList.add('lightbox-open');
      lightboxClose.focus();
    }

    function closeLightbox() {
      lightbox.classList.remove('open');
      lightbox.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('lightbox-open');
      focusBeforeLightbox?.focus();
    }

    root.querySelectorAll('.gallery-image-thumb').forEach(thumb => {
      thumb.addEventListener('click', () => showPhoto(+thumb.dataset.i, +thumb.dataset.i >= currentIndex ? 1 : -1, true));
    });
    galleryMain.querySelectorAll('.gallery-nav').forEach(button => {
      button.addEventListener('click', () => {
        const direction = +button.dataset.galleryDir;
        showPhoto(currentIndex + direction, direction, true);
      });
    });
    gallery.addEventListener('click', event => {
      if (event.target.closest('.gallery-play')) {
        startSlideshow();
        galleryMain.focus({ preventScroll: true });
        return;
      }
      if (event.target.closest('.gallery-main-image')) openLightbox();
    });
    galleryThumbs.addEventListener('scroll', () => positionPlayButton(currentIndex), { passive: true });
    galleryMain.addEventListener('keydown', event => {
      if ((event.key === 'Enter' || event.key === ' ') && event.target === galleryMain) {
        event.preventDefault();
        openLightbox();
        return;
      }
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const direction = event.key === 'ArrowLeft' ? -1 : 1;
      showPhoto(currentIndex + direction, direction, true);
    });
    galleryMain.addEventListener('touchstart', event => {
      touchStartX = event.changedTouches[0].clientX;
    }, { passive: true });
    galleryMain.addEventListener('touchend', event => {
      if (touchStartX === null) return;
      const delta = event.changedTouches[0].clientX - touchStartX;
      touchStartX = null;
      if (Math.abs(delta) < 45) return;
      const direction = delta < 0 ? 1 : -1;
      showPhoto(currentIndex + direction, direction, true);
    }, { passive: true });

    lightboxClose.addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', event => {
      if (event.target === lightbox) closeLightbox();
    });
    lightbox.querySelectorAll('[data-lightbox-dir]').forEach(button => {
      button.addEventListener('click', () => updateLightbox(lightboxIndex + +button.dataset.lightboxDir));
    });
    lightbox.addEventListener('touchstart', event => {
      lightboxTouchStartX = event.changedTouches[0].clientX;
    }, { passive: true });
    lightbox.addEventListener('touchend', event => {
      if (lightboxTouchStartX === null || images.length < 2) return;
      const delta = event.changedTouches[0].clientX - lightboxTouchStartX;
      lightboxTouchStartX = null;
      if (Math.abs(delta) >= 45) updateLightbox(lightboxIndex + (delta < 0 ? 1 : -1));
    }, { passive: true });
    document.addEventListener('keydown', event => {
      if (!lightbox.classList.contains('open')) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        closeLightbox();
      }
      if (event.key === 'ArrowLeft' && images.length > 1) {
        event.preventDefault();
        updateLightbox(lightboxIndex - 1);
      }
      if (event.key === 'ArrowRight' && images.length > 1) {
        event.preventDefault();
        updateLightbox(lightboxIndex + 1);
      }
      if (event.key === 'Tab') {
        const controls = [...lightbox.querySelectorAll('button')];
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });

    if (images.length > 1 && !reduceMotion.matches) {
      startSlideshow();
    }
    const resizeObserver = window.ResizeObserver ? new ResizeObserver(syncThumbHeight) : null;
    resizeObserver?.observe(galleryMain);
    window.addEventListener('resize', syncThumbHeight);
    galleryMain.querySelector('.gallery-main-image').addEventListener('load', syncThumbHeight, { once: true });
    syncThumbHeight();
  }
})();
