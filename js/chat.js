// ============================================================
// Gurevic Real Estate — чат-виджет с ИИ-ассистентом (черновик)
//
// Сейчас это скриптованный сценарий на фронте: ассистент задаёт
// уточняющие вопросы (цель, тип, бюджет, район), собирает контакт
// и «передаёт риелтору» (лид сохраняется в localStorage + console).
//
// TODO (продакшн):
//  1. Бэкенд-прокси к Claude API (ключ нельзя класть во фронт) —
//     небольшой endpoint /api/chat, который держит system-промпт
//     с данными об объектах и историю диалога.
//  2. Отправка собранного лида риелтору: Telegram-бот (sendMessage
//     в чат риелтора) или email. Хук — функция deliverLead() ниже.
// ============================================================

const Chat = (() => {
  let el = {};
  let step = 0;
  let autoStart = true;  // при открытии запускать сценарий-анкету
  const lead = {};       // собранные ответы клиента
  const transcript = []; // полная переписка (кто что написал) — уходит вместе с заявкой
  let freeInputHandler = null;

  const SCRIPT = [
    {
      key: 'goal',
      text: 'Здравствуйте! Я ассистент агентства Gurevic Real Estate 🤖\nПомогу подобрать недвижимость в Будве и окрестностях. Что вас интересует?',
      options: ['Купить', 'Арендовать', 'Инвестиции', 'Просто смотрю'],
    },
    {
      key: 'type',
      text: 'Отлично! Какой тип объекта рассматриваете?',
      options: ['Квартира', 'Дом / вилла', 'Участок', 'Коммерческая', 'Пока не решил(а)'],
    },
    {
      key: 'budget',
      text: 'Какой у вас ориентировочный бюджет? Можно выбрать вариант или написать свой.',
      options: ['до €150 000', '€150–300 тыс.', '€300–700 тыс.', 'от €700 тыс.'],
      allowFree: true,
    },
    {
      key: 'location',
      text: 'Есть ли предпочтения по району? Будва, Бечичи, Рафаиловичи, Пржно, Свети-Стефан…',
      options: ['Будва', 'Бечичи / Рафаиловичи', 'Свети-Стефан / Пржно', 'Не важно'],
      allowFree: true,
    },
    {
      key: 'contact',
      text: 'Записал! Чтобы риелтор связался с вами и прислал подборку, оставьте, пожалуйста, телефон или @telegram:',
      free: true,
    },
  ];

  // ---------- UI ----------
  function build() {
    document.body.insertAdjacentHTML('beforeend', `
      <button class="chat-fab" id="chat-fab" title="Чат с ассистентом">💬<span class="fab-dot"></span></button>
      <div class="chat-panel" id="chat-panel">
        <div class="chat-head">
          <div class="agent-ava">GR</div>
          <div><b>Ассистент Gurevic Estate</b><span>● онлайн — отвечает сразу</span></div>
          <button class="chat-close" id="chat-close">✕</button>
        </div>
        <div class="chat-log" id="chat-log"></div>
        <form class="chat-input-row" id="chat-form">
          <input id="chat-input" type="text" placeholder="Написать сообщение…" autocomplete="off">
          <button id="chat-send" type="submit">➤</button>
        </form>
      </div>`);
    el = {
      fab: document.getElementById('chat-fab'),
      panel: document.getElementById('chat-panel'),
      log: document.getElementById('chat-log'),
      input: document.getElementById('chat-input'),
    };
    el.fab.addEventListener('click', toggle);
    document.getElementById('chat-close').addEventListener('click', toggle);
    // форма ловит и клик по кнопке, и Enter в поле ввода
    document.getElementById('chat-form').addEventListener('submit', e => {
      e.preventDefault();
      sendFree();
    });
    // дублируем Enter явно (preventDefault защищает от двойной отправки через submit)
    el.input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); sendFree(); }
    });
  }

  function toggle() {
    const opening = !el.panel.classList.contains('open');
    el.panel.classList.toggle('open');
    el.fab.querySelector('.fab-dot')?.remove();
    if (opening && autoStart && !el.log.children.length) askNext();
    if (opening) el.input.focus();
  }

  function addMsg(text, who) {
    el.log.insertAdjacentHTML('beforeend', `<div class="msg ${who}">${text}</div>`);
    el.log.scrollTop = el.log.scrollHeight;
    transcript.push({ who, text, t: new Date().toISOString() });
  }

  function botSay(text, after) {
    el.log.insertAdjacentHTML('beforeend',
      `<div class="msg bot typing-msg"><span class="typing"><i></i><i></i><i></i></span></div>`);
    el.log.scrollTop = el.log.scrollHeight;
    setTimeout(() => {
      el.log.querySelector('.typing-msg').remove();
      addMsg(text, 'bot');
      if (after) after();
    }, 550 + Math.random() * 350);
  }

  function removeQuickReplies() {
    el.log.querySelectorAll('.quick-replies').forEach(q => q.remove());
  }

  function showOptions(opts, onPick) {
    const html = opts.map(o => `<button type="button" class="quick-reply">${o}</button>`).join('');
    el.log.insertAdjacentHTML('beforeend', `<div class="quick-replies">${html}</div>`);
    el.log.scrollTop = el.log.scrollHeight;
    el.log.querySelectorAll('.quick-replies:last-child .quick-reply').forEach(btn => {
      btn.addEventListener('click', () => {
        removeQuickReplies();
        addMsg(btn.textContent, 'user');
        onPick(btn.textContent);
      });
    });
  }

  // ---------- сценарий ----------
  function askNext() {
    if (step >= SCRIPT.length) return finish();
    const q = SCRIPT[step];
    botSay(q.text, () => {
      if (q.options) showOptions(q.options, answer);
      if (q.allowFree || q.free) freeInputHandler = answer;
    });
  }

  function answer(value) {
    freeInputHandler = null;
    lead[SCRIPT[step].key] = value;
    step++;
    askNext();
  }

  function sendFree() {
    const text = el.input.value.trim();
    if (!text) return;
    el.input.value = '';
    if (freeInputHandler) {
      removeQuickReplies();
      addMsg(text, 'user');
      freeInputHandler(text);
    } else {
      addMsg(text, 'user');
      // свободный вопрос вне сценария — в проде сюда пойдёт запрос к Claude API
      botSay('Хороший вопрос! Я передам его риелтору вместе с вашей заявкой. А пока продолжим подбор 🙂');
    }
  }

  function finish() {
    deliverLead(lead);
    const rows = [
      ['Имя', lead.name], ['Цель', lead.goal], ['Тип', lead.type],
      ['Бюджет', lead.budget], ['Район', lead.location],
      ['Сообщение', lead.message], ['Контакт', lead.contact],
    ].filter(([, v]) => v).map(([k, v]) => `• ${k}: ${v}`).join('\n');
    botSay(
      `Спасибо! Ваша заявка передана риелтору:\n${rows}\n\n` +
      `Риелтор свяжется с вами в ближайшее время. Также можно написать напрямую:`,
      () => showOptions(['📱 WhatsApp', '✈️ Telegram', '📞 Позвонить'], opt => {
        const links = {
          '📱 WhatsApp': 'https://wa.me/38269572257',
          '✈️ Telegram': 'https://t.me/hurewicz',
          '📞 Позвонить': 'tel:+38269572257',
        };
        window.open(links[opt], '_blank');
        botSay('Открываю… Если что-то не сработало — номера есть в разделе «Контакты» внизу страницы.');
      })
    );
  }

  // Доставка лида риелтору. ВАЖНО: сейчас данные пишутся только в localStorage
  // ЭТОГО браузера — то есть агентство их НЕ видит. Чтобы риелтор видел заявки и
  // переписку, нужен бэкенд: этот же объект (data + transcript) отправить POST-ом
  // на сервер / в Telegram-бота. См. пометку TODO вверху файла и leads.html.
  function deliverLead(data) {
    const record = {
      ...data,
      transcript: transcript.slice(),        // полная переписка бота с клиентом
      ts: new Date().toISOString(),
      page: location.pathname + location.search,
    };
    const leads = JSON.parse(localStorage.getItem('gurevic_leads') || '[]');
    leads.push(record);
    localStorage.setItem('gurevic_leads', JSON.stringify(leads));
    console.log('[lead] заявка + переписка сохранены (демо, только этот браузер):', record);

    // TODO (продакшн): отправить record на бэкенд/бота, например:
    // fetch('/api/lead', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(record) });
  }

  // ---------- публичное API ----------
  function open() {
    if (!el.panel.classList.contains('open')) toggle();
  }

  // Открыть чат с данными из формы обратной связи
  function openWithLead(formData) {
    if (formData.name) lead.name = formData.name;
    if (formData.contact) lead.contact = formData.contact;
    if (formData.message) lead.message = formData.message;

    if (formData.contact) {
      // форма уже дала контакт — не гоняем анкету, сразу подтверждаем заявку
      autoStart = false;
      open();
      if (formData.message) addMsg(formData.message, 'user');
      step = SCRIPT.length;
      finish();
    } else {
      open(); // без контакта — обычный сценарий с вопросами
    }
  }

  document.addEventListener('DOMContentLoaded', build);
  return { open, openWithLead };
})();
