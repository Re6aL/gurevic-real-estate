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

  const thumbs = Array.from({ length: l.photos || 4 }, (_, i) =>
    `<div class="ph ph--thumb ${i === 0 ? 'active' : ''}" style="--h:${(l.hue + i * 14) % 360}" data-i="${i}"><span>фото ${i + 1}</span></div>`
  ).join('');

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
  const mapBlock = `
    <h2>Расположение на карте</h2>
    <div class="obj-map">
      <iframe loading="lazy" referrerpolicy="no-referrer-when-downgrade"
        src="https://www.google.com/maps?q=${lat},${lng}&z=15&output=embed"></iframe>
      <div class="map-note">📍 ${l.location}, Черногория — точка приблизительная (демо-координаты района; заменить точными координатами объекта)</div>
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
      <div id="gallery-main">${ph((l.hue), 'ГЛАВНОЕ ФОТО — плейсхолдер, заменить реальными фотографиями объекта', 'ph--tall')}</div>
      <div class="gallery-thumbs">${thumbs}</div>
    </div>

    <div class="obj-layout">
      <div class="obj-desc">
        <h2>Описание</h2>
        ${l.desc.split('\n\n').map(p => `<p>${p}</p>`).join('')}
        <h2>Особенности</h2>
        <div class="features">${l.features.map(f => `<span class="feature-chip">${f}</span>`).join('')}</div>
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

  // переключение «фото» в галерее
  root.querySelectorAll('.ph--thumb').forEach(t => {
    t.addEventListener('click', () => {
      root.querySelectorAll('.ph--thumb').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      document.getElementById('gallery-main').innerHTML =
        ph((l.hue + (+t.dataset.i) * 14) % 360, `ФОТО ${+t.dataset.i + 1} — плейсхолдер, заменить реальным`, 'ph--tall');
    });
  });
})();
