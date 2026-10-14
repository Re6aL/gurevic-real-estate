# Notion для сайта Gurevic Real Estate — что создать и как подключить

Инструкция для риелтора (владельца Notion). Сайт берёт данные из трёх баз:

| База | Что в ней | Как связана с сайтом | Интеграция |
|---|---|---|---|
| **Objekati** (уже есть) | объекты на продажу и для инвестиций | раз в час → страницы `buy/` и `invest/` | `website` (только чтение) |
| **Najam / Аренда** (новая, раздел 1) | объекты долгосрочной аренды | раз в час → страницы `rent/` | `website` (только чтение) |
| **Website Leads** (новая, раздел 2) | заявки с форм сайта | сайт сам добавляет строки | `website-leads` (только добавление) |

На сайт попадают **только** колонки, перечисленные ниже как «публикуется». Владелец, комиссия,
лист непокретности, кадастровая община, документы, телефоны и точный адрес на сайт не попадают
никогда — скрипт их просто не читает. Имена колонок надо писать **точно как в таблицах**
(регистр, пробелы, «m²»), иначе колонка не будет найдена.

Объекты обновляются на сайте автоматически раз в час (GitHub Actions). Публикуются только строки
со статусом **Available**.

---

## 1. Новая база «Najam / Аренда» — долгосрочная аренда

Как создать: в Notion → новая страница → **Table — Full page** → назвать `Najam / Аренда`.
Имена общих колонок совпадают с «Objekati», поэтому можно сделать копию «Objekati»
(••• → Duplicate), удалить строки и лишние колонки, добавить колонки аренды.

### 1.1 Колонки

| Колонка (точное имя) | Тип Notion | Варианты / формат | На сайте | Пример |
|---|---|---|---|---|
| `Aktualnost` | Title | название объекта; можно оставить пустым — сайт соберёт заголовок сам | публикуется | `Stan Rozino, 2 spavaće` |
| `Object ID` | Text | уникальный код; **не должен совпадать** с кодами в «Objekati» (например, буква `N` в конце) | публикуется (в адресе страницы) | `BD-26-001N` |
| `Status` | Status | `Adding`, `Available`, `Reserved`, `Rented`, `Off market` | только фильтр: публикуется лишь `Available` | `Available` |
| `Property Type` | Select | `Apartment`, `House`, `Villa` | публикуется | `Apartment` |
| `Monthly Rent` | Number (формат Euro) | € в месяц; пусто/0 → «цена по запросу» | публикуется | `900` |
| `Rental Term` | Multi-select | `Off-season` (до начала сезона), `Year` (на год), `Short-term` (посуточно) | публикуется. Объекты только с `Short-term` на сайт не попадают — раздел краткосрочной аренды «в разработке» | `Off-season`, `Year` |
| `Deposit` | Number (Euro) | депозит, € | публикуется | `900` |
| `Available From` | Date | с какой даты свободен | публикуется | `01.11.2026` |
| `Min Term (months)` | Number | минимальный срок, месяцев | публикуется | `6` |
| `Utilities` | Select | `Included`, `Not included`, `Partly included` | публикуется | `Not included` |
| `Pets` | Select | `Allowed`, `Not allowed`, `By agreement` | публикуется | `By agreement` |
| `Interjer (m²)` | Number | площадь, м² | публикуется | `62` |
| `Land (m²)` | Number | участок, м² (для домов) | публикуется | `400` |
| `Sp. sobe` | Number | число спален | публикуется | `2` |
| `Bathrooms` | Number | санузлы | публикуется | `1` |
| `Floor` | Text | этаж | публикуется | `3/5` |
| `Balconies` | Number | балконы/террасы | публикуется | `1` |
| `View` | Select | `Sea`, `Mountains`, `City`, `Garden`… | публикуется | `Sea` |
| `Furnishing` | Select | `Furnished`, `Partly furnished`, `Unfurnished` | публикуется | `Furnished` |
| `Parking` | Select | `Garage`, `Parking space`, `Street`, `No` | публикуется | `Parking space` |
| `Distance to Sea` | Text | расстояние | публикуется | `300 м` |
| `Особенности` | Multi-select | преимущества | публикуется | `Вид на море`, `Кондиционер` |
| `Location` | Text | адрес | **НЕ публикуется** — по нему определяется только район | `Rozino, ul. …, Budva` |
| `District` | Select | район латиницей (список в разделе 3.4); если заполнен — важнее адреса | публикуется (район) | `Budva – Rozino` |
| `Map Link` | URL | ссылка Google Maps | публикуется точка на карте; не хотите точку — оставьте пустым | `https://maps.app.goo.gl/…` |
| `Photos` | Files & media | до 6 фото (JPG/PNG/WebP), первое — обложка | публикуется (фото копируются на сайт) | |
| `Card Description` | Text | короткий текст карточки (рус.) | публикуется | `Светлая квартира в 5 минутах от пляжа.` |
| `Website Description` | Text | описание на странице объекта (рус.) | публикуется | |
| `Location Description` | Text | о районе (рус.) | публикуется | |
| `Card Description EN` … | Text | переводы — см. раздел 3.5 | публикуется | |
| `Owner Name` | Text | собственник | **приватно** | |
| `Owner Phone` | Phone | телефон собственника | **приватно** | |
| `Provizija` | Number | комиссия | **приватно** | |
| `Notes` | Text | заметки | **приватно** | |

Любые другие колонки (ваши заметки, связи, ответственный) сайт игнорирует.
Телефоны и e-mail, случайно попавшие в тексты описаний, при публикации вырезаются.

### 1.2 Как это выглядит на сайте

- Страница `rent/` показывает только объекты со статусом `Available` и сроком `Off-season` и/или `Year`.
- Квартиры → `rent/apartments/`, дома и виллы → `rent/houses/`.
- Пока база не подключена, раздел аренды показывает форму «оставьте заявку» — это нормально.

---

## 2. Новая база «Website Leads» — заявки с сайта

Сюда сайт складывает все заявки: инвесторы (частные и компании), владельцы, запросы на аренду
и покупку, контактная форма, чат. Создать: новая страница → **Table — Full page** → назвать
`Website Leads`. Колонки **с точными именами и типами**:

| Колонка | Тип Notion | Варианты (создать заранее, точно так) | Что приходит |
|---|---|---|---|
| `Name` | Title | — | имя; если нет — компания; иначе «Website lead» |
| `Form` | Select | `Investor (private)`, `Investor (company)`, `Owner`, `Contact`, `Rent request`, `Buy request`, `Property request`, `Chat` | какая форма |
| `Status` | Status | To-do: `New`; In progress: `In progress`, `Qualified`, `NDA sent`; Complete: `Closed`, `Spam` | новые заявки — `New` |
| `Language` | Select | `Русский`, `English`, `Deutsch`, `Français`, `Polski`, `Українська`, `עברית` | язык страницы сайта |
| `Preferred Language` | Select | `Русский`, `English`, `Crnogorski/Srpski`, `Українська`, `Other` | язык общения (при `Other` текст — в Message) |
| `Contact Method` | Select | `E-mail`, `Phone`, `WhatsApp`, `Telegram`, `Video call` | как связаться |
| `Email` | Email | — | |
| `Phone` | Phone | — | |
| `Telegram` | Text | — | ник или телефон |
| `Company` | Text | — | компания (инвестор-компания / юрлицо-владелец) |
| `Position` | Text | — | должность |
| `Website` | URL | — | сайт компании |
| `Jurisdiction` | Text | — | страна регистрации компании |
| `Investment Type` | Select | `Hotel`, `Development land`, `Restaurant / commercial`, `Warehouse / logistics`, `Development partnership`, `Other` | |
| `Budget` | Select | `< €500K`, `€500K–2M`, `€2–10M`, `€10–50M`, `> €50M`, `Not disclosed` | |
| `NDA Requested` | Checkbox | — | просит / готов подписать NDA |
| `Property Kind` | Select | `Apartment`, `House`, `Land`, `Construction project`, `Business` | форма владельца |
| `Owner Type` | Select | `Individual`, `Company` | физлицо / юрлицо |
| `List Nepokretnosti` | Text | — | номер листа непокретности |
| `KO` | Text | — | кадастарска општина |
| `PD` | Text | — | посебни дио (для квартиры) |
| `Company Reg No` | Text | — | регистрационный номер юрлица |
| `Asking Price` | Number (Euro) | — | желаемая цена владельца |
| `Interest` | Select | `Buy`, `Rent`, `Invest`, `Sell`, `Rent out`, `Property management`, `Other` | интерес (контакт/чат) |
| `Rental Term` | Select | `Off-season`, `Full year`, `Short-term` | запрос аренды |
| `Move-in` | Date | — | желаемая дата заезда |
| `Monthly Budget` | Number (Euro) | — | бюджет аренды в месяц |
| `Bedrooms` | Number | — | нужно спален |
| `Occupants` | Text | — | кто будет жить |
| `Pets` | Text | — | животные |
| `Object ID` | Text | — | код объекта, если заявка со страницы объекта |
| `Listing URL` | URL | — | ссылка на объект |
| `Message` | Text | — | комментарий + все поля, для которых нет колонки (`ключ: значение`) |
| `Transcript` | Text | — | переписка из чата |
| `Page` | URL | — | страница сайта, где отправлена форма |
| `UTM` | Text | — | метки рекламы `source=…; medium=…; campaign=…` |
| `Consent` | Checkbox | — | согласие на обработку данных (всегда отмечено) |
| `Consent Version` | Text | — | версия текста согласия, напр. `2026-10` |
| `Received` | Created time | — | заполняет Notion сам |

Важно:
- Варианты select лучше создать заранее ровно так, как в таблице. Если варианта нет, Notion
  может создать его сам или отклонить запись — тогда заявка всё равно сохранится: заголовок
  + все поля текстом в `Message`.
- Колонку можно не создавать — тогда её значение уйдёт строкой в `Message`. Переименовывать
  колонки нельзя (сайт пишет по именам).
- Паспортные данные и финансовые документы формы **не запрашивают**.

### 2.1 Рекомендуемые представления (views)

| View | Тип | Фильтр | Сортировка | Показать колонки |
|---|---|---|---|---|
| **New** | Board по `Status` | `Status` ≠ `Spam` | `Received` ↓ | Name, Form, Contact Method, Received |
| **Investors** | Table | `Form` is `Investor (private)` или `Investor (company)` | `Received` ↓ | Name, Company, Position, Investment Type, Budget, NDA Requested, Preferred Language, Contact Method, Email, Phone, Status |
| **Owners** | Table | `Form` is `Owner` | `Received` ↓ | Name, Owner Type, Property Kind, Asking Price, List Nepokretnosti, KO, PD, Company Reg No, Phone, Preferred Language, Status |
| **Buyers & Tenants** | Table | `Form` is `Buy request`, `Rent request`, `Property request`, `Contact` или `Chat` | `Received` ↓ | Name, Form, Interest, Object ID, Rental Term, Move-in, Monthly Budget, Bedrooms, Contact Method, Status |

### 2.2 Хранение заявок

- Срок хранения — как на странице `privacy/` («Сколько мы храним данные»): по общему правилу
  заявки и переписку храним **до 24 месяцев после последнего контакта** с человеком, затем
  удаляем или обезличиваем. Если заключён договор, связанные с ним данные хранятся столько,
  сколько требуют договор и закон.
- Заявки со статусом `Spam` удалять сразу; остальные пересматривать раз в квартал и удалять
  (обезличивать) те, где с последнего контакта прошло 24 месяца и нет договора. Если срок
  меняется — сначала текст `privacy/` (i18n/*/privacy.json), потом этот раздел.
- Данные владельцев (лист непокретности, KO, PD) после передачи объекта в работу хранить в
  закрытом разделе CRM, а не в «Website Leads».
- Доступ к базе — только сотрудникам агентства; не делать страницу публичной (Share to web).

---

## 3. Новые колонки в существующей базе «Objekati»

Всё ниже необязательно: без этих колонок сайт работает по правилам «по умолчанию».

### 3.1 `Property Type` — добавить варианты

Уже есть: `Apartment`, `House`, `Land`, `Commercial`, `Industrial`, `Office`, `Retail`, `Hotel`, `Gradnja`.
Добавить: **`Villa`**, **`Business`** (готовый бизнес, ресторан), **`Warehouse`** (склад, логистика).

| Property Type | Тип на сайте | Раздел по умолчанию | Раскрытие по умолчанию |
|---|---|---|---|
| Apartment | квартира | `buy/apartments/` | Public |
| House | дом | `buy/houses/` | Public |
| Villa | вилла | `buy/villas/` | Public |
| Land | участок | `buy/land/` (под частную застройку) | Public (если раздел Invest — Confidential) |
| Hotel | отель | `invest/hotels/` | Confidential |
| Commercial / Office / Retail / Industrial / Warehouse | коммерческая | `invest/commercial/` | Confidential |
| Business | готовый бизнес | `invest/commercial/` | Confidential |
| Gradnja | проект строительства | `invest/development-projects/` | Public |

### 3.2 `Website Section` — Select: `Buy`, `Invest`

Перекрывает раздел по умолчанию. Пример: участок под отель → `Land` + `Website Section = Invest`
→ `invest/land/`. Пусто = по таблице выше.

### 3.3 `Disclosure` — Select: `Public`, `Confidential`

- **Public** — обычная карточка: название, фото, точка на карте.
- **Confidential** — анонимно: заголовок вида «Отель, Будва», без названия из CRM, без фото
  (вместо них иллюстрация), без точки на карте (только район), цена помечена как ориентировочная.
  Фото таких объектов не выкладываются на сайт, даже если лежат в Dropbox.
- Пусто = по таблице выше.

### 3.4 `District` — Select (латиница)

Если заполнен — район берётся отсюда, а не из адреса. Варианты (точно так):

`Budva – centre`, `Budva – Rozino`, `Budva – waterfront`, `Budva – Ivanica`, `Budva – Veligrad`,
`Bečići`, `Rafailovići`, `Pržno`, `Sveti Stefan`, `Lapčići`, `Tudorovići`, `Lastva Grbaljska`,
`Petrovac`, `Buljarica`, `Tivat`, `Kotor`, `Herceg Novi`, `Bar`, `Dobra Voda`, `Ulcinj`,
`Rijeka Crnojevića`, `Cetinje`, `Podgorica`, `Montenegro`.

Без колонки район определяется по `Location`; если ничего не узнано — «Черногория» (раньше было
«Будва — центр»).

### 3.5 Тексты для сайта и переводы

| Колонка | Тип | Где на сайте |
|---|---|---|
| `Card Description` | Text | короткий текст карточки (рус.) |
| `Website Description` | Text | описание на странице объекта (рус.) |
| `Location Description` | Text | блок «Расположение» (рус.) |
| `Card Description EN`, `… DE`, `… FR`, `… PL`, `… UK`, `… HE` | Text | то же на других языках |
| `Website Description EN` … `HE` | Text | |
| `Location Description EN` … `HE` | Text | |

Суффикс — код языка через пробел (`Card Description EN`), допустимо и `Card Description (EN)`.
Можно добавить только нужные языки. Где текста нет, сайт сам составит нейтральное описание
из параметров (тип, площадь, спальни, район) — без выдуманных фактов.

### 3.6 Прочие колонки, которые сайт уже понимает

`Bathrooms`, `Floor`, `Balconies`, `View`, `Furnishing`, `Condition`, `Parking`,
`Distance to Sea`, `Completion Date`, `Payment Plan`, `Transfer Tax`, `Project ID`,
`Project Name`, `Unit Code`, `Map Link`, `Особенности`, `Deal Type`.
Проекты: строка проекта — `Project ID` заполнен, `Unit Code` пуст; квартиры проекта — те же
`Project ID` + свой `Unit Code` — показываются таблицей внутри проекта.

---

## 4. Доступ: интеграции, ID баз, секреты

### 4.1 Интеграция `website` (уже есть) — только чтение объектов

1. https://www.notion.so/my-integrations → `website` → **Capabilities**: включено только
   **Read content**; Update content, Insert content — выключены; User information — *No user information*.
2. Подключить к базам **Objekati** и **Najam / Аренда**: открыть базу → ••• → **Connections**
   → найти `website`. К «Website Leads» эту интеграцию **не** подключать.

### 4.2 Новая интеграция `website-leads` — только добавление заявок

1. https://www.notion.so/my-integrations → **New integration** → имя `website-leads`, тип Internal.
2. **Capabilities**: включить **только Insert content**; Read content и Update content —
   выключить; User information — *No user information*. Такой токен может только добавлять
   строки и не может прочитать ни одной заявки или объекта.
3. Подключить **только** к базе **Website Leads** (••• → Connections → `website-leads`).

### 4.3 Что отправить разработчику

Только **ID баз** (это не секрет): открыть базу как страницу → **Share → Copy link**;
ID — 32 символа между последним `/` и `?v=`:
`https://www.notion.so/workspace/`**`0123456789abcdef0123456789abcdef`**`?v=…`

- ID базы **Najam / Аренда**
- ID базы **Website Leads**

**Токены (`ntn_…` / `secret_…`) никогда не пересылать в чат, почту или мессенджер.**
Владелец вставляет их сам в настройки (ниже) или во время созвона, вводя в поле секрета.

### 4.4 Где хранятся секреты

GitHub → репозиторий → Settings → Secrets and variables → Actions:

| Имя | Что это | Статус |
|---|---|---|
| `NOTION_TOKEN` | токен интеграции `website` (read-only) | уже есть |
| `NOTION_DB_ID` | ID базы «Objekati» | уже есть |
| `NOTION_RENT_DB_ID` | ID базы «Najam / Аренда» | **добавить** |
| `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN` | фото из Dropbox | уже есть |
| переменная `DROPBOX_MEDIA_ROOT` (Variables) | папка с фото | уже есть |

Cloudflare (Worker приёма заявок, `api/lead-worker/README.md`), задаются командой
`npx wrangler secret put <ИМЯ>`:

| Имя | Что это |
|---|---|
| `NOTION_TOKEN` | токен интеграции `website-leads` (insert-only) — **не** токен `website` |
| `NOTION_LEADS_DB_ID` | ID базы «Website Leads» |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | необязательно: уведомления о новых заявках в Telegram |

### 4.5 Порядок включения

1. Создать «Najam / Аренда» (раздел 1), подключить `website`, добавить секрет `NOTION_RENT_DB_ID`.
2. Создать «Website Leads» (раздел 2) и интеграцию `website-leads`, подключить только к ней.
3. Разработчик деплоит Worker и прописывает его адрес в `src/site.json` (`leadEndpoint`).
   До этого формы сайта работают через кнопки WhatsApp / Telegram / E-mail.
4. По желанию — колонки раздела 3 в «Objekati».
5. GitHub → Actions → **Sync public listings from Notion** → **Run workflow** — проверить,
   что сайт обновился.

Если токен мог попасть к посторонним — сразу отозвать его в Notion
(my-integrations → интеграция → Secrets → Refresh) и обновить секрет.
