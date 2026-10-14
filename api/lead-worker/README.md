# lead-worker — приём заявок с сайта в Notion

Маленький Cloudflare Worker. Формы сайта (инвестор, владелец, аренда, контакт, чат)
отправляют JSON сюда, а Worker записывает заявку строкой в базу Notion
**«Website Leads»** и (по желанию) присылает короткое уведомление в Telegram.

Почему отдельный сервис: сайт — статический (GitHub Pages) и публичный, токен Notion
в него положить нельзя. Токен живёт только в секретах Cloudflare.

```
браузер ── POST (text/plain JSON) ──► Worker ── Notion API ──► «Website Leads»
                                         └──── Telegram (необязательно)
```

## Что делает Worker

- принимает только `POST` (и `OPTIONS` для CORS) с сайтов из `ALLOWED_ORIGINS`;
- тело — JSON (`Content-Type: text/plain` или `application/json`), не больше 32 КБ;
- антиспам: поле-ловушка `hp` должно быть пустым (иначе ответ «ok», но ничего не пишется),
  форма должна быть заполнена не быстрее чем за 2,5 с (`elapsed_ms`);
- обязательно согласие `consent: true`; проверяет тип формы, длину полей, формат e-mail и даты,
  наличие хотя бы одного контакта (e-mail / телефон / Telegram);
- пишет **только** существующие колонки подходящего типа. Схему базы Worker пытается прочитать
  (`GET /v1/databases/{id}`, кэш 10 минут); у рекомендуемой интеграции с одним правом
  *Insert content* чтения нет (Notion отвечает 403) — тогда используется встроенная схема
  из `docs/NOTION_SETUP.md`, поэтому **имена колонок должны совпадать точно**. Коды превращаются в понятные подписи (`2m_10m` → `€2–10M`,
  `hotel` → `Hotel`, `investor_company` → `Investor (company)`); новые варианты select Notion
  создаёт сам. Всё, для чего колонки нет, попадает в **Message** строками `ключ: значение` —
  заявка не теряется, даже если колонку переименовали;
- если Notion отклонил запись (например, удалили вариант статуса), повторяет «минимальной»
  записью: заголовок + все поля текстом в Message;
- уведомление в Telegram — без e-mail, телефонов, кадастровых и регистрационных номеров
  (только тип заявки, имя, ключевые параметры и ссылка на строку в Notion);
- ответ: `{"ok": true}` или `{"ok": false, "error": "<код>"}` с кодом HTTP 400/403/405/413/415/502/503.
  При ошибке сайт показывает запасные кнопки WhatsApp / Telegram / E-mail.

Коды ошибок: `origin_not_allowed`, `method_not_allowed`, `unsupported_media_type`, `too_large`,
`invalid_json`, `invalid_form`, `consent_required`, `too_fast`, `invalid_email`, `invalid_date`,
`field_too_long:<поле>`, `contact_required`, `company_required`, `not_configured`, `upstream_error`.

Формат запроса — `docs/ARCHITECTURE.md` §7, колонки базы — `docs/NOTION_SETUP.md` (раздел 2).

## Развёртывание (один раз, ~10 минут)

Нужны: аккаунт Cloudflare (бесплатного тарифа достаточно) и Node.js 18+.

1. Подготовить Notion — `docs/NOTION_SETUP.md`, разделы 2 и 4: база «Website Leads» и
   **отдельная** интеграция `website-leads` только с правом *Insert content*, подключённая
   только к этой базе.
2. Войти в Cloudflare и задеплоить:
   ```bash
   cd api/lead-worker
   npx wrangler login
   npx wrangler deploy
   ```
   Wrangler покажет адрес вида `https://gurevic-lead-worker.<аккаунт>.workers.dev`.
3. Задать секреты (значения вводятся в ответ на запрос и никуда не сохраняются локально):
   ```bash
   npx wrangler secret put NOTION_TOKEN          # токен интеграции website-leads
   npx wrangler secret put NOTION_LEADS_DB_ID    # 32 символа из ссылки на базу
   # необязательно — уведомления в Telegram:
   npx wrangler secret put TELEGRAM_BOT_TOKEN    # от @BotFather
   npx wrangler secret put TELEGRAM_CHAT_ID      # id чата/группы, куда бот будет писать
   ```
   Для Telegram: создать бота у @BotFather, написать ему любое сообщение (или добавить бота
   в группу), затем узнать `chat_id`, например через `https://api.telegram.org/bot<токен>/getUpdates`
   в своём браузере. Токен бота никому не пересылать.
4. Прописать адрес Worker в `src/site.json` → `leadEndpoint` и пересобрать сайт
   (`python tools/build_site.py`). Пока поле пустое, формы работают через запасные кнопки.
5. Если сайт переедет на свой домен — добавить его в `ALLOWED_ORIGINS` в `wrangler.toml`
   и снова `npx wrangler deploy`.

Рекомендуется также правило ограничения частоты в Cloudflare (Security → WAF → Rate limiting
rules: например, не больше 10 POST в минуту с одного IP на адрес Worker).

## Проверка

Тесты (без сети, fetch подменяется):

```bash
cd api/lead-worker && node --test
# или из корня репозитория:
node --test "api/lead-worker/test/*.test.mjs"
```

Живая проверка после деплоя (создаст тестовую строку в «Website Leads» — потом удалите её
или поставьте статус Spam):

```bash
curl -i -X POST "https://gurevic-lead-worker.<аккаунт>.workers.dev/" \
  -H "Origin: https://re6al.github.io" \
  -H "Content-Type: text/plain" \
  --data '{"form":"contact","lang":"ru","page":"https://re6al.github.io/gurevic-real-estate/contact/","elapsed_ms":5000,"hp":"","consent":true,"consent_version":"2026-10","utm":{},"fields":{"name":"Тест","email":"test@example.com","message":"Проверка Worker"}}'
```

Ожидаемый ответ: `HTTP/1.1 200` и `{"ok":true}`. Проверка CORS:

```bash
curl -i -X OPTIONS "https://gurevic-lead-worker.<аккаунт>.workers.dev/" -H "Origin: https://evil.example"
# → 403 {"ok":false,"error":"origin_not_allowed"}
```

Логи в реальном времени: `npx wrangler tail` (пишутся только коды ошибок, без данных посетителей).

## Безопасность

- Секретов в репозитории нет; `wrangler.toml` содержит только список разрешённых сайтов.
- Токен `website-leads` может **только добавлять** страницы в одну базу — он не читает CRM
  и не видит базы объектов. Если токен утёк — отозвать его в Notion и задать новый
  (`npx wrangler secret put NOTION_TOKEN`).
- Хранимые логи Cloudflare выключены (`[observability] enabled = false`).
