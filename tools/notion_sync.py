#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gurevic Real Estate — синхронизация каталога из Notion CRM.

  база «Objekati» (продажа/инвестиции)  → js/data.js     (const LISTINGS = [...])
  база «Najam / Аренда» (долгосрочная)  → js/rentals.js  (const RENTALS  = [...])

Работает на стандартной библиотеке (urllib) — без pip-зависимостей.
Публикуются ТОЛЬКО колонки из FIELD_MAP / FIELD_MAP_RENT; приватные колонки
CRM (Owner Name, Provizija, List Nep., Documents Folder, Person, Cadastral
Municipality, телефоны, точный адрес) скрипт не читает вообще.
Структура баз и список колонок — docs/NOTION_SETUP.md.

------------------------------------------------------------------
СЕКРЕТЫ (никогда не в репозитории):
  переменные окружения NOTION_TOKEN, NOTION_DB_ID, NOTION_RENT_DB_ID
  или файл %USERPROFILE%\\.config\\gurevic\\notion.env  (KEY=VALUE)

ЗАПУСК:
  python tools/notion_sync.py --dry-run          # показать результат, ничего не писать
  python tools/notion_sync.py                    # записать js/data.js (+ js/rentals.js)
  python tools/notion_sync.py --watch 300        # пересинхронизировать каждые 5 минут
  python tools/notion_sync.py --fixture tools/tests/fixtures/sales_pages.json --dry-run
                                                 # офлайн: страницы Notion из JSON-файла
  python tools/notion_sync.py --sanitize         # только вычистить конфиденциальные
                                                 # объекты в js/data.js (после dropbox_sync)

Если NOTION_RENT_DB_ID не задан: существующий js/rentals.js не трогаем,
а если его нет — создаём с пустым массивом.
------------------------------------------------------------------
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib

NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

# Секреты берём ВНЕ веб-папки (иначе токен был бы скачиваем по URL!).
SECRETS_FILE = os.path.join(os.path.expanduser("~"), ".config", "gurevic", "notion.env")
SECRET_KEYS = ("NOTION_TOKEN", "NOTION_DB_ID", "NOTION_RENT_DB_ID")


def load_secrets():
    """{NOTION_TOKEN, NOTION_DB_ID, NOTION_RENT_DB_ID}: env, затем файл вне веб-папки."""
    found = {k: (os.environ.get(k) or "").strip() or None for k in SECRET_KEYS}
    if not all(found.values()) and os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (s.strip() for s in line.split("=", 1))
                if k in found and not found[k] and v:
                    found[k] = v
    return found


# Корень проекта = родитель папки tools/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(PROJECT_ROOT, "js")

# ------------------------------------------------------------------
# СООТВЕТСТВИЕ ПОЛЕЙ: ключ на сайте -> имя колонки в базе «Objekati».
# Значение может быть кортежем имён — берётся первая существующая колонка.
# Приватные колонки CRM сюда НЕ добавлять.
# ------------------------------------------------------------------
FIELD_MAP = {
    "title":     "Aktualnost",     # Title — название объекта (crmTitle)
    "objectId":  "Object ID",      # BD-26-019S — используется как id
    "type":      "Property Type",  # Apartment/House/Villa/Land/Hotel/Commercial/…/Business/Gradnja
    "price":     "Cijena",         # Number (€)
    "area":      "Interjer (m²)",  # Number (м²)
    "landArea":  "Land (m²)",      # Number (м²)
    "rooms":     "Sp. sobe",       # Number — спальни
    "location":  "Location",       # полный адрес — публикуем ТОЛЬКО район
    "district":  "District",       # Select (латиница, docs/NOTION_SETUP.md) — перекрывает детект
    "section":   "Website Section",  # Select Buy / Invest — перекрывает раздел по умолчанию
    "disclosure": "Disclosure",    # Select Public / Confidential
    "mapLink":   "Map Link",       # Google Maps short-link → координаты
    "features":  "Особенности",    # Multi-select — публичные преимущества объекта
    # Точное название колонки с фото задаётся через NOTION_PHOTOS_FIELD.
    # Значение намеренно не хранится в репозитории.
    "images":    os.environ.get("NOTION_PHOTOS_FIELD", ""),
    "status":    "Status",         # Adding/Available/For Re-evaluation/Reserved/Sold
    "deal":      "Deal Type",      # Sale / Rent
    "bathrooms": "Bathrooms",
    "floor":     "Floor",
    "balconies": "Balconies",
    "view":      "View",
    "cardDescription": "Card Description",
    "propertyDescription": "Website Description",
    "locationDescription": "Location Description",
    "paymentPlan": "Payment Plan",
    "transferTax": "Transfer Tax",
    "furnishing": "Furnishing",
    "condition": "Condition",
    "parking": "Parking",
    "distanceToSea": "Distance to Sea",
    "completionDate": "Completion Date",
    "projectId": "Project ID",
    "projectName": "Project Name",
    "unitCode": "Unit Code",
}

# База аренды «Najam / Аренда» (docs/NOTION_SETUP.md, раздел 1). Имена общих
# колонок совпадают с «Objekati», чтобы базу можно было сделать дублированием.
FIELD_MAP_RENT = {
    "title":     "Aktualnost",
    "objectId":  "Object ID",
    "type":      "Property Type",          # Apartment / House / Villa
    "price":     ("Monthly Rent", "Cijena"),  # Number (€ в месяц)
    "area":      "Interjer (m²)",
    "landArea":  "Land (m²)",
    "rooms":     "Sp. sobe",
    "location":  "Location",
    "district":  "District",
    "mapLink":   "Map Link",
    "features":  "Особенности",
    "images":    os.environ.get("NOTION_RENT_PHOTOS_FIELD", "Photos"),
    "status":    "Status",                 # Adding / Available / Reserved / Rented / Off market
    "bathrooms": "Bathrooms",
    "floor":     "Floor",
    "balconies": "Balconies",
    "view":      "View",
    "furnishing": "Furnishing",
    "condition": "Condition",
    "parking":   "Parking",
    "distanceToSea": "Distance to Sea",
    "cardDescription": "Card Description",
    "propertyDescription": "Website Description",
    "locationDescription": "Location Description",
    "rentalTerms": "Rental Term",          # Multi-select Off-season / Year (/ Short-term)
    "deposit":   "Deposit",                # Number (€)
    "availableFrom": "Available From",     # Date
    "minTermMonths": "Min Term (months)",  # Number
    "utilities": "Utilities",              # Select Included / Not included / Partly included
    "pets":      "Pets",                   # Select Allowed / Not allowed / By agreement
}

# Колонки с текстами для сайта. Русский — базовая колонка, переводы — с суффиксом
# языка: «Card Description EN», «Card Description (EN)» и т.п.
TEXT_COLUMNS = {
    "card": "Card Description",
    "description": "Website Description",
    "location": "Location Description",
}
TEXT_LANGS = ("en", "de", "fr", "pl", "uk", "he")

# Публикуем только эти статусы
PUBLISH_STATUSES = {"available"}


# ------------------------------------------------------------------
# Нормализация строк: нижний регистр, без диакритики (č→c, đ→dj), ё→е
# ------------------------------------------------------------------
def norm(text):
    s = str(text or "").lower().replace("đ", "dj").replace("ё", "е")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------
# Районы (brief §F, общий справочник с src/districts.json).
# (ключ, ru-подпись = data `location`, латиница = опции select «District»,
#  муниципалитет для анонимных заголовков, regex-фрагменты по нормализованному тексту)
# Порядок = приоритет: самые конкретные места первыми, затем «Будва — центр»,
# затем «Черногория» (other). Каждый фрагмент привязан к началу слова.
# ------------------------------------------------------------------
DISTRICTS = [
    ("lastva-grbaljska", "Ластва Грбальска", "Lastva Grbaljska", "Котор",
     (r"l[au]stv[a-z]* grbalj", r"ластв[а-я]* грбал")),
    ("rijeka-crnojevica", "Риека Црноевича", "Rijeka Crnojevića", "Цетине",
     (r"crnojevi", r"crnojrvi", r"црноевич")),
    ("dobra-voda", "Добра Вода", "Dobra Voda", "Бар",
     (r"dobr(?:a|oj|e) vod", r"добр(?:а|ой|ая) вод")),
    ("buljarica", "Булярица", "Buljarica", "Будва",
     (r"buljaric", r"буляриц")),
    ("tudorovici", "Тудоровичи", "Tudorovići", "Будва",
     (r"tudorovic", r"тудорович")),
    ("przno", "Пржно", "Pržno", "Будва",
     (r"przn[oua]", r"пржн")),
    ("sveti-stefan", "Свети-Стефан", "Sveti Stefan", "Будва",
     (r"sv(?:eti|\.)? ?-?stefan", r"свет(?:и|ой)[ -]?стефан")),
    ("rafailovici", "Рафаиловичи", "Rafailovići", "Будва",
     (r"rafailovic", r"рафаилович")),
    ("lapcici", "Лапчичи", "Lapčići", "Будва",
     (r"lapcic", r"лапчич")),
    ("budva-rozino", "Будва — Розино", "Budva – Rozino", "Будва",
     (r"rozino", r"розино")),
    ("budva-ivanica", "Будва — Иваница", "Budva – Ivanica", "Будва",
     (r"ivanic", r"иваниц")),
    ("budva-veligrad", "Будва — Велиград", "Budva – Veligrad", "Будва",
     (r"veligrad", r"велиград")),
    # «šetalište» есть во многих городах (Херцег-Нови!) — считаем только рядом с Будвой
    ("budva-waterfront", "Будва — набережная", "Budva – waterfront", "Будва",
     (r"slovensk[aeoi]j? obal", r"setalist(?=.*budv)", r"набережн(?=.*будв)")),
    ("becici", "Бечичи", "Bečići", "Будва",
     (r"becic", r"boret", r"бечич", r"борет")),
    ("petrovac", "Петровац", "Petrovac", "Будва",
     (r"petrov(?:ac|cu|ca)(?![a-z])", r"петровац")),
    ("tivat", "Тиват", "Tivat", "Тиват",
     (r"tiv(?:at|tu|ta)(?![a-z])", r"тиват")),
    ("herceg-novi", "Херцег-Нови", "Herceg Novi", "Херцег-Нови",
     (r"herceg[ -]?nov", r"херцег")),
    ("kotor", "Котор", "Kotor", "Котор",            # не «Kotorska» (улица в Будве)
     (r"kotor(?:u|a|om)?(?![a-z])", r"котор(?:е|а)?(?![а-я])")),
    ("bar", "Бар", "Bar", "Бар",                    # отдельное слово: не «Barok», не «Barska»
     (r"bar(?:u|a)?(?![a-z])",)),
    ("ulcinj", "Улцинь", "Ulcinj", "Улцинь",
     (r"ulcinj", r"ульцин", r"улцин")),
    ("cetinje", "Цетине", "Cetinje", "Цетине",
     (r"cetinj(?:e|u|a)(?![a-z])", r"obzovic", r"цетин")),
    ("podgorica", "Подгорица", "Podgorica", "Подгорица",
     (r"podgoric(?:a|i|e|u)(?![a-z])", r"подгориц")),
    ("budva-center", "Будва — центр", "Budva – centre", "Будва",
     (r"budv", r"будв")),
    ("other", "Черногория", "Montenegro", "Черногория", ()),
]
DISTRICT_BY_KEY = {d[0]: d for d in DISTRICTS}
_DISTRICT_RX = [
    (d[0], [re.compile(r"(?<![a-zа-я0-9])(?:" + frag + ")") for frag in d[4]])
    for d in DISTRICTS
]


def _match_district(text):
    s = norm(text)
    if not s:
        return None
    for key, patterns in _DISTRICT_RX:
        if any(p.search(s) for p in patterns):
            return key
    return None


def detect_district(*texts):
    """Ключ района по адресу/названию (тексты проверяются по очереди). Fallback — other."""
    for text in texts:
        key = _match_district(text)
        if key:
            return key
    return "other"


def district_from_select(value):
    """Select «District» (латиница, ключ или ru-подпись) → ключ района или None."""
    s = norm(value)
    if not s:
        return None
    for key, ru, latin, _region, _kw in DISTRICTS:
        if s in (key, norm(ru), norm(latin)):
            return key
    return _match_district(value)


def district_label(key):
    return DISTRICT_BY_KEY.get(key, DISTRICT_BY_KEY["other"])[1]


def district_region(key):
    return DISTRICT_BY_KEY.get(key, DISTRICT_BY_KEY["other"])[3]


# ------------------------------------------------------------------
# Классификация (ARCHITECTURE §6)
# ------------------------------------------------------------------
KIND_MAP = {
    "apartment": "apartment", "apartman": "apartment", "stan": "apartment",
    "flat": "apartment", "studio": "apartment", "penthouse": "apartment",
    "house": "house", "kuca": "house", "townhouse": "house",
    "villa": "villa", "vila": "villa",
    "land": "land", "plot": "land", "plac": "land", "zemljiste": "land",
    "hotel": "hotel",
    "commercial": "commercial", "office": "commercial", "retail": "commercial",
    "industrial": "commercial", "warehouse": "commercial", "logistics": "commercial",
    "poslovni prostor": "commercial", "lokal": "commercial", "magacin": "commercial",
    "skladiste": "commercial",
    "business": "business", "restaurant": "business", "biznis": "business",
    "gradnja": "development", "novogradnja": "development", "development": "development",
}
# Старое поле `type` (совместимость со старым фронтом js/main.js, js/object.js)
LEGACY_TYPE = {
    "apartment": "apartment", "house": "house", "villa": "house", "land": "land",
    "hotel": "hotel", "commercial": "commercial", "business": "commercial",
    "development": "land",
}
INVEST_DEFAULT_KINDS = {"hotel", "commercial", "business", "development"}
CONFIDENTIAL_DEFAULT_KINDS = {"hotel", "commercial", "business"}
INVEST_KIND_RU = {
    "hotel": "Отель — готовый бизнес", "development": "Девелопмент",
    "commercial": "Коммерческая недвижимость", "business": "Готовый бизнес",
    "land": "Участок под застройку",
}
TYPE_RU = {
    "apartment": "Квартира", "house": "Дом", "villa": "Вилла", "land": "Участок",
    "commercial": "Коммерческое помещение", "hotel": "Отель",
    "business": "Готовый бизнес", "development": "Проект строительства",
}
DEAL_EN2KEY = {"sale": "sale", "prodaja": "sale", "rent": "rent", "rental": "rent",
               "izdavanje": "rent", "najam": "rent"}


def kind_from_type(value):
    s = norm(value)
    if not s:
        return "apartment"
    if s in KIND_MAP:
        return KIND_MAP[s]
    for word, kind in KIND_MAP.items():  # «Hotel / Apart-hotel», «Office space» …
        if re.search(r"(?<![a-z])" + re.escape(word), s):
            return kind
    print(f"[warn] неизвестный Property Type «{value}» → apartment")
    return "apartment"


def parse_section(value):
    s = norm(value)
    if not s:
        return None
    if s.startswith(("buy", "sale", "kup", "prod", "покуп", "прод")):
        return "buy"
    if s.startswith(("invest", "инвест")):
        return "invest"
    return None


def parse_disclosure(value):
    s = norm(value)
    if not s:
        return None
    if s.startswith(("public", "javn", "публич", "открыт")):
        return "public"
    if s.startswith(("confidential", "private", "povjerlj", "konfid", "конфиденц", "закрыт")):
        return "confidential"
    return None


def default_section(kind):
    return "invest" if kind in INVEST_DEFAULT_KINDS else "buy"


def default_disclosure(kind, section):
    if kind == "development":
        return "public"
    if kind in CONFIDENTIAL_DEFAULT_KINDS:
        return "confidential"
    if kind == "land" and section == "invest":
        return "confidential"
    return "public"


# ---- аренда: условия ----
def parse_rental_terms(values):
    if values is None:
        return []
    if isinstance(values, str):
        values = re.split(r"[,;/\n]+", values)
    out = []
    for raw in values:
        s = norm(raw)
        code = None
        if not s:
            continue
        if any(k in s for k in ("off", "season", "sezon", "сезон", "зим")):
            code = "off_season"
        elif any(k in s for k in ("short", "kratk", "краткоср", "посуточ")):
            code = "short_term"
        elif any(k in s for k in ("year", "annual", "12", "godin", "godis", "год", "долгоср")):
            code = "year"
        if code and code not in out:
            out.append(code)
    order = ("off_season", "year", "short_term")
    return sorted(out, key=order.index)


def parse_utilities(value):
    s = norm(value)
    if not s:
        return None
    if any(k in s for k in ("not", "excl", "nisu", "nije", "не ", "не-", "оплачива")) or s.startswith("не"):
        return "not_included"
    if any(k in s for k in ("part", "djelim", "delim", "частич")):
        return "partial"
    if any(k in s for k in ("incl", "ukljuc", "включ")):
        return "included"
    return None


def parse_pets(value):
    if isinstance(value, bool):
        return "allowed" if value else "not_allowed"
    s = norm(value)
    if not s:
        return None
    if any(k in s for k in ("agree", "request", "negotiab", "dogovor", "договор", "запрос", "обсужд")):
        return "by_agreement"
    if s.startswith(("no", "not", "ne", "не", "нельзя", "запрещ")) or "not allowed" in s:
        return "not_allowed"
    if s.startswith(("yes", "allow", "da", "dozvolj", "можно", "да", "разреш")):
        return "allowed"
    return None


# ---- вычистка контактов из свободного текста ----
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_INTL_RE = re.compile(r"(?<![\w+])(?:\+|00)\d[\d\s().-]{6,}\d")
_PHONE_LOCAL_RE = re.compile(r"(?<!\d)0(?:6\d|20|30|33)[\s/.-]?\d{3}[\s.-]?\d{3,4}(?!\d)")


def scrub_contacts(text):
    """Убирает e-mail и номера телефонов из публикуемого текста."""
    if not isinstance(text, str):
        return text
    s = _EMAIL_RE.sub("", text)
    s = _PHONE_INTL_RE.sub("", s)
    s = _PHONE_LOCAL_RE.sub("", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return s.strip()


# ---- Map Link (maps.app.goo.gl) -> координаты, с кэшем ----
COORD_CACHE_FILE = os.path.join(os.path.dirname(SECRETS_FILE), "maplink_cache.json")
_RE_AT = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
_RE_3D4D = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
_RE_Q = re.compile(r"[?&](?:q|ll|query)=(-?\d+\.\d+)(?:%2C|,)\s*(-?\d+\.\d+)")


def _load_coord_cache():
    try:
        with open(COORD_CACHE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_coord_cache(cache):
    try:
        os.makedirs(os.path.dirname(COORD_CACHE_FILE), exist_ok=True)
        with open(COORD_CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
    except OSError as exc:
        print(f"[warn] кэш координат не сохранён: {exc}")


def _coords_from_text(text):
    for rx in (_RE_AT, _RE_3D4D, _RE_Q):
        m = rx.search(text or "")
        if m:
            return [round(float(m.group(1)), 6), round(float(m.group(2)), 6)]
    return None


def resolve_map_link(url, cache, offline=False):
    """[lat, lng] из ссылки Google Maps (сначала из самого URL, потом редирект). None при неудаче."""
    if not url:
        return None
    coords = _coords_from_text(url)
    if coords:
        return coords
    if url in cache:
        return cache[url]
    if offline:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            final = r.geturl()
            html = r.read(200000).decode("utf-8", "ignore")
        coords = _coords_from_text(final) or _coords_from_text(html)
    except Exception:
        coords = None
    cache[url] = coords
    return coords


# ============ Notion API (переиспользуемая часть) ============
class NotionError(RuntimeError):
    pass


def _req(path, token, method="GET", body=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise NotionError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:400]}") from None
    except urllib.error.URLError as e:
        raise NotionError(f"сеть: {e.reason}") from None


def notion_query_all(token, database_id):
    """Все страницы базы Notion (с учётом пагинации). Универсально."""
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        res = _req(f"/databases/{database_id}/query", token, "POST", body)
        pages.extend(res.get("results", []))
        if not res.get("has_more"):
            break
        cursor = res["next_cursor"]
    return pages


def load_fixture(path):
    """Страницы Notion из локального JSON: список страниц или ответ query ({"results": [...]})."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("results", data.get("pages", []))
    if not isinstance(data, list):
        raise ValueError(f"{path}: ожидался список страниц Notion")
    return data


# ---- извлечение значений из свойств Notion ----
def _plain(rich):
    return "".join(x.get("plain_text") or x.get("text", {}).get("content", "") for x in rich or [])


def prop_value(props, name):
    """Достаёт значение свойства Notion по имени, независимо от типа."""
    p = props.get(name)
    if not p:
        return None
    t = p.get("type")
    v = p.get(t)
    if t in ("title", "rich_text"):
        return _plain(v).strip() or None
    if t == "number":
        return v
    if t in ("select", "status"):
        return v["name"] if v else None
    if t == "multi_select":
        return [o["name"] for o in v or []]
    if t in ("checkbox", "url", "email", "phone_number"):
        return v
    if t == "files":
        out = [f.get("external", {}).get("url") or f.get("file", {}).get("url") for f in v or []]
        return [u for u in out if u]
    if t == "date":
        return v["start"] if v else None
    if t == "unique_id":
        if not v or v.get("number") is None:
            return None
        return f"{v['prefix']}-{v['number']}" if v.get("prefix") else str(v["number"])
    if t == "formula" and v:
        return v.get(v.get("type"))
    return None


class Row:
    """Страница Notion + карта полей: row.get("price") → значение первой найденной колонки."""

    def __init__(self, page, field_map):
        self.page = page
        self.props = page.get("properties", {}) or {}
        self.field_map = field_map

    def get(self, key):
        names = self.field_map.get(key)
        if not names:
            return None
        for name in (names,) if isinstance(names, str) else names:
            if name and name in self.props:
                return prop_value(self.props, name)
        return None

    def texts(self):
        """{"card": {lang: str}, "description": {...}, "location": {...}} — только заполненные."""
        out = {}
        for group, base in TEXT_COLUMNS.items():
            found = {}
            for lang in ("ru",) + TEXT_LANGS:
                names = [f"{base} {lang.upper()}", f"{base} ({lang.upper()})"]
                if lang == "ru":
                    names.insert(0, base)
                for name in names:
                    value = prop_value(self.props, name)
                    if isinstance(value, str) and value.strip():
                        found[lang] = scrub_contacts(value.strip())
                        break
            out[group] = found
        return out


def slugify(text, fallback):
    s = re.sub(r"[^\w\s-]", "", (text or "").lower(), flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s or fallback


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value).replace(" ", ""))
    if not m:
        return None
    f = float(m.group(0).replace(",", "."))
    return int(f) if f.is_integer() else f


def stable_hue(text):
    """Стабильный оттенок плейсхолдера (hash() в Python меняется между запусками)."""
    return zlib.crc32(str(text).encode("utf-8")) % 360


IMAGE_LIMIT = 6
IMAGE_MAX_BYTES = 12 * 1024 * 1024
IMAGE_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def download_images(urls, listing_id, subdir="listings", root=PROJECT_ROOT):
    """Сохраняет фото из Notion как публичные файлы сайта (img/<subdir>/<id>/photo-N.ext).

    Notion выдаёт временные URL, поэтому в js-данных сохраняются только
    относительные пути к скачанным изображениям, а не исходные ссылки.
    """
    if not urls:
        return []
    target_dir = os.path.join(root, "img", subdir, listing_id)
    paths = []
    for index, url in enumerate(urls[:IMAGE_LIMIT], start=1):
        try:
            if urllib.parse.urlparse(url).scheme != "https":
                continue
            req = urllib.request.Request(url, headers={"User-Agent": "GurevicEstateSync/1.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                content_type = response.headers.get_content_type().lower()
                if content_type not in IMAGE_EXTENSIONS:
                    continue
                data = response.read(IMAGE_MAX_BYTES + 1)
            if len(data) > IMAGE_MAX_BYTES:
                continue
            os.makedirs(target_dir, exist_ok=True)
            filename = f"photo-{index}{IMAGE_EXTENSIONS[content_type]}"
            with open(os.path.join(target_dir, filename), "wb") as image_file:
                image_file.write(data)
            paths.append(f"img/{subdir}/{listing_id}/{filename}")
        except Exception as exc:  # отдельное фото не должно срывать публикацию каталога
            print(f"[warn] фото {listing_id}/{index} не скачано: {exc}")
    return paths


def rooms_ru(n):
    n = int(n)
    if n == 1:
        return "1 спальня"
    if 2 <= n <= 4:
        return f"{n} спальни"
    return f"{n} спален"


# ============ маппинг Notion -> объект сайта ============
class SyncContext:
    """Общие настройки одного прогона: кэш координат, офлайн-режим, прошлые данные."""

    def __init__(self, offline=False, coord_cache=None, previous=None, root=PROJECT_ROOT):
        self.offline = offline
        self.coord_cache = coord_cache if coord_cache is not None else {}
        self.previous = previous or {}   # id -> прошлый объект (сохранить фото/координаты)
        self.root = root

    def keep_previous(self, listing, key):
        """Фото из прошлой версии (dropbox_sync), если новых нет и файлы на месте."""
        old = self.previous.get(listing["id"]) or {}
        value = old.get(key)
        if not value:
            return None
        if key == "images":
            value = [p for p in value if isinstance(p, str)
                     and os.path.isfile(os.path.join(self.root, *p.split("/")))]
            return value or None
        return value


def auto_title(kind, area, location):
    """«Квартира 56 м² — Бечичи»: заголовок из структурных полей (без названия CRM)."""
    bits = [TYPE_RU.get(kind, "Объект")]
    if area:
        bits.append(f"{int(area)} м²")
    return " ".join(bits) + f" — {location}"


def _base_listing(row, ctx, kind, section, deal, img_subdir):
    """Общая часть для продажи и аренды (без проверки статуса)."""
    obj_id = (row.get("objectId") or "").strip()
    crm_title = scrub_contacts((row.get("title") or "").strip()) or None

    district_key = district_from_select(row.get("district")) or detect_district(
        row.get("location"), crm_title)
    location = district_label(district_key)
    area, land = _num(row.get("area")), _num(row.get("landArea"))
    bedrooms = _num(row.get("rooms"))
    bedrooms = int(bedrooms) if isinstance(bedrooms, (int, float)) and bedrooms > 0 else None
    price = _num(row.get("price"))
    price = int(price) if price and price > 0 else 0

    # Приватность: в названиях CRM у обычных объектов бывают имена владельцев («Stan od Aleksandra u …»),
    # поэтому в публичный data.js название CRM попадает только у проектов строительства (имя проекта).
    # У остальных — автозаголовок; само название используется лишь внутри (поиск района выше).
    public_crm_title = crm_title if kind == "development" else None
    title = public_crm_title
    if not title:  # автозаголовок: не-проект или риелтор не заполнил название
        title = auto_title(kind, area, location)

    page_key = (row.page.get("id") or "x").replace("-", "")[:8] or "x"
    listing = {
        # без Object ID — из имени проекта или id страницы Notion (не из названия CRM: оно приватно)
        "id": slugify(obj_id or public_crm_title, "obj-" + page_key),
        "objectId": obj_id or None,
        "title": title,
        "crmTitle": public_crm_title,
        "type": LEGACY_TYPE.get(kind, "apartment"),
        "kind": kind,
        "section": section,
        "deal": deal,
        "location": location,        # только район; точный адрес не публикуем
        "districtKey": district_key,
        "price": price,
    }
    if not price:
        listing["priceNote"] = "Цена по запросу"
    if area:
        listing["area"] = area
    if land:
        listing["landArea"] = land
    if bedrooms:
        listing["rooms"] = rooms_ru(bedrooms)
        listing["bedrooms"] = bedrooms

    for field in ("bathrooms", "floor", "balconies", "view", "cardDescription",
                  "propertyDescription", "locationDescription", "paymentPlan", "transferTax",
                  "furnishing", "condition", "parking", "distanceToSea", "completionDate",
                  "projectId", "projectName", "unitCode"):
        value = row.get(field)
        if isinstance(value, str):
            value = scrub_contacts(value)
        if value is not None and value != "" and value != []:
            listing[field] = value

    listing["texts"] = row.texts()

    coords = resolve_map_link(row.get("mapLink"), ctx.coord_cache, offline=ctx.offline)
    coords = coords or ctx.keep_previous(listing, "coords")
    if coords:
        listing["coords"] = coords

    images = []
    if not ctx.offline:
        images = download_images(row.get("images") or [], listing["id"], img_subdir, ctx.root)
    images = images or ctx.keep_previous(listing, "images") or []
    if images:
        listing["images"] = images

    # авто-описания (ru, для старого фронта; генератор строит свои по языкам)
    p_bits = []
    if area:
        p_bits.append(f"площадь {int(area)} м²")
    if land:
        p_bits.append(f"участок {int(land)} м²")
    if bedrooms:
        p_bits.append(rooms_ru(bedrooms))
    params_txt = ", ".join(p_bits) or "параметры уточняются"
    type_ru = TYPE_RU.get(kind, "Объект")
    listing["short"] = listing.get("cardDescription") or f"{type_ru} в районе {location}: {params_txt}."
    listing["desc"] = listing.get("propertyDescription") or (
        f"{type_ru} в районе {location}: {params_txt}. "
        "Описание сформировано из проверенных полей CRM; дополнительные характеристики уточняются у риелтора."
    )
    raw_features = row.get("features") or []
    if isinstance(raw_features, str):
        raw_features = re.split(r"[,;\n]+", raw_features)
    listing["features"] = [scrub_contacts(str(f).strip()) for f in raw_features if str(f).strip()]
    listing["photos"] = len(images) or 4
    listing["hue"] = stable_hue(listing["id"])
    return listing


def anonymize(listing):
    """Конфиденциальный объект: без названия CRM, фото, точки на карте (ARCHITECTURE §6).

    Тексты из колонок Card/Website/Location Description остаются — риелтор пишет их
    специально для сайта.
    """
    kind = listing.get("kind") or "commercial"
    region = district_region(listing.get("districtKey") or "other")
    listing["title"] = f"{TYPE_RU.get(kind, 'Объект')}, {region}"
    listing["crmTitle"] = None
    for key in ("images", "coords", "projectName"):
        listing.pop(key, None)
    listing["photos"] = 0
    listing["disclosure"] = "confidential"
    return listing


def page_to_listing(page, ctx):
    """Страница базы «Objekati» → объект js/data.js (None — не публикуем)."""
    if isinstance(ctx, dict):  # совместимость со старой сигнатурой (page, coord_cache)
        ctx = SyncContext(coord_cache=ctx)
    row = Row(page, FIELD_MAP)
    status = (row.get("status") or "").strip().lower()
    if PUBLISH_STATUSES and status not in PUBLISH_STATUSES:
        return None  # публикуем только Available

    kind = kind_from_type(row.get("type"))
    deal = DEAL_EN2KEY.get(str(row.get("deal") or "sale").strip().lower(), "sale")
    if deal == "rent":
        section = "rent"  # аренда из старой базы: не смешиваем с продажей
    else:
        section = parse_section(row.get("section")) or default_section(kind)
    disclosure = parse_disclosure(row.get("disclosure")) or default_disclosure(kind, section)
    if section == "rent":
        disclosure = "public"

    if disclosure == "confidential":
        # не скачиваем фото и не резолвим карту: всё равно будет вычищено anonymize()
        ctx = SyncContext(offline=True, root=ctx.root)
    listing = _base_listing(row, ctx, kind, section, deal, "listings")
    listing["disclosure"] = disclosure

    if section == "invest":
        listing["invest"] = True
        listing["investKind"] = INVEST_KIND_RU.get(kind, "Инвестиции")
    if kind == "development":
        listing["isComplex"] = True
    if listing.get("projectId") and not listing.get("unitCode"):
        listing["isComplex"] = True
    if section == "rent":
        listing["monthlyPrice"] = listing["price"]
    if disclosure == "confidential":
        anonymize(listing)
    return listing


def page_to_rental(page, ctx):
    """Страница базы «Najam / Аренда» → объект js/rentals.js (None — не публикуем)."""
    row = Row(page, FIELD_MAP_RENT)
    status = (row.get("status") or "").strip().lower()
    if status not in PUBLISH_STATUSES:
        return None
    terms = parse_rental_terms(row.get("rentalTerms"))
    if terms and not set(terms) - {"short_term"}:
        return None  # только посуточная/краткосрочная — раздел «в разработке»

    kind = kind_from_type(row.get("type"))
    if kind not in ("apartment", "house", "villa"):
        kind = "house" if kind in ("land",) else "apartment"
    listing = _base_listing(row, ctx, kind, "rent", "rent", "listings")
    listing["disclosure"] = "public"
    listing["monthlyPrice"] = listing["price"]
    if listing["price"]:
        listing.pop("priceNote", None)
    listing["rentalTerms"] = [t for t in terms if t != "short_term"]
    deposit = _num(row.get("deposit"))
    min_term = _num(row.get("minTermMonths"))
    available = row.get("availableFrom")
    listing["deposit"] = int(deposit) if isinstance(deposit, (int, float)) and deposit >= 0 else None
    listing["availableFrom"] = str(available)[:10] if available else None
    listing["minTermMonths"] = int(min_term) if isinstance(min_term, (int, float)) and min_term > 0 else None
    listing["utilities"] = parse_utilities(row.get("utilities"))
    listing["pets"] = parse_pets(row.get("pets"))
    return listing


def attach_project_units(listings):
    """Собирает строки-юниты под карточкой родительского проекта.

    Родитель: Project ID заполнен, Unit Code пуст. Юнит: оба поля заполнены.
    Если родитель не найден, строка остаётся самостоятельным объектом и не теряется.
    """
    parents = {}
    for item in listings:
        if item.get("unitCode"):
            continue
        for key in (item.get("projectId"), item.get("objectId"), item.get("id")):
            if key:
                parents[str(key).strip().lower()] = item

    attached_ids = set()
    for item in listings:
        project_id = item.get("projectId")
        unit_code = item.get("unitCode")
        if not project_id or not unit_code:
            continue
        parent = parents.get(str(project_id).strip().lower())
        if not parent or parent is item:
            continue
        unit = {"unitCode": unit_code, "name": unit_code, "status": "available"}
        for field in ("floor", "rooms", "bedrooms", "area", "bathrooms", "view", "price"):
            if item.get(field) is not None:
                unit[field] = item[field]
        parent.setdefault("units", []).append(unit)
        parent["isComplex"] = True
        attached_ids.add(id(item))

    for parent in parents.values():
        if parent.get("units"):
            parent["units"].sort(key=lambda u: (str(u.get("floor", "")), str(u.get("unitCode", ""))))
    return [item for item in listings if id(item) not in attached_ids]


def dedupe_ids(listings):
    """Одинаковые id (дубли Object ID в CRM) получают суффикс -2, -3…"""
    seen = {}
    for item in listings:
        base = item["id"]
        if base in seen:
            seen[base] += 1
            item["id"] = f"{base}-{seen[base]}"
        else:
            seen[base] = 1
    return listings


# ============ запись js-файлов ============
def render_js(listings, var="LISTINGS"):
    if var == "RENTALS":
        what = "ОБЪЕКТЫ ДОЛГОСРОЧНОЙ АРЕНДЫ (RENTALS)"
        src = "из Notion (база «Najam / Аренда»)"
    else:
        what = "БАЗА ОБЪЕКТОВ (LISTINGS)"
        src = "из Notion (база «Objekati»)"
    header = (
        "// ============================================================\n"
        f"// Gurevic Real Estate — {what}.\n"
        f"// АВТОСГЕНЕРИРОВАНО {src} скриптом tools/notion_sync.py — не править вручную.\n"
        "// Справочники и координаты — в js/config.js.\n"
        "// ============================================================\n\n"
        f"const {var} =\n"
    )
    return header + json.dumps(listings, ensure_ascii=False, indent=2) + ";\n"


def render_data_js(listings):  # старое имя — совместимость
    return render_js(listings, "LISTINGS")


def read_js_array(path):
    """Массив из js-файла (между первой «[» и последней «]»). [] если файла нет."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return []
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _previous_by_id(path):
    return {x.get("id"): x for x in read_js_array(path) if isinstance(x, dict) and x.get("id")}


def build_sales(pages, ctx):
    listings = [x for x in (page_to_listing(p, ctx) for p in pages) if x]
    return dedupe_ids(attach_project_units(listings))


def build_rentals(pages, ctx):
    return dedupe_ids([x for x in (page_to_rental(p, ctx) for p in pages) if x])


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _warn(msg):
    # ::warning:: видно в сводке GitHub Actions; локально — просто строка
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") == "true" else "[warn] "
    print(prefix + msg)


def sync_once(token=None, db=None, rent_db=None, dry_run=False, out_dir=JS_DIR,
              fixture=None, rent_fixture=None, root=PROJECT_ROOT):
    """Один прогон. Возвращает (listings|None, rentals|None)."""
    ts = time.strftime("%H:%M:%S")
    offline = bool(fixture or rent_fixture)
    cache = {} if offline else _load_coord_cache()
    data_path = os.path.join(out_dir, "data.js")
    rent_path = os.path.join(out_dir, "rentals.js")
    listings = rentals = None

    # ---- продажа / инвестиции ----
    if fixture or db:
        pages = load_fixture(fixture) if fixture else notion_query_all(token, db)
        ctx = SyncContext(offline=offline, coord_cache=cache,
                          previous=_previous_by_id(data_path), root=root)
        listings = build_sales(pages, ctx)
        print(f"[{ts}] Objekati: страниц {len(pages)}, к публикации {len(listings)}")

    # ---- аренда ----
    if rent_fixture or rent_db:
        try:
            pages = load_fixture(rent_fixture) if rent_fixture else notion_query_all(token, rent_db)
            ctx = SyncContext(offline=offline, coord_cache=cache,
                              previous=_previous_by_id(rent_path), root=root)
            rentals = build_rentals(pages, ctx)
            print(f"[{ts}] Аренда: страниц {len(pages)}, к публикации {len(rentals)}")
        except NotionError as exc:
            # база аренды могла быть ещё не подключена к интеграции — продажу не роняем
            _warn(f"база аренды недоступна ({exc}); js/rentals.js не изменён")

    if not offline:
        _save_coord_cache(cache)

    if dry_run:
        for name, items, var in (("data.js", listings, "LISTINGS"), ("rentals.js", rentals, "RENTALS")):
            if items is None:
                continue
            out = render_js(items, var)
            print(f"--- {name} ---")
            print(out[:2000] + ("\n… (обрезано)" if len(out) > 2000 else ""))
        print("\n[dry-run] файлы НЕ записаны.")
        return listings, rentals

    if listings is not None:
        _write(data_path, render_js(listings, "LISTINGS"))
        print(f"[{ts}] ok: {len(listings)} объектов → {data_path}")
    if rentals is not None:
        _write(rent_path, render_js(rentals, "RENTALS"))
        print(f"[{ts}] ok: {len(rentals)} объектов аренды → {rent_path}")
    elif not os.path.exists(rent_path):
        _write(rent_path, render_js([], "RENTALS"))
        print(f"[{ts}] база аренды не задана → создан пустой {rent_path}")
    return listings, rentals


def strip_private_title(item):
    """Не-проект с названием CRM (в нём бывают имена владельцев) → автозаголовок, crmTitle = null.

    Только для записей нового формата (есть ключ kind). True — если запись изменилась.
    """
    kind = item.get("kind")
    if not kind or kind == "development" or not item.get("crmTitle"):
        return False
    item["crmTitle"] = None
    item["title"] = auto_title(kind, item.get("area"), item.get("location") or district_label("other"))
    return True


def sanitize_file(path=None, root=PROJECT_ROOT, dry_run=False):
    """Повторно анонимизирует конфиденциальные объекты в js/data.js и убирает названия CRM
    у не-проектов (strip_private_title).

    Нужен после tools/dropbox_sync.py, который дописывает фото всем объектам с папкой
    в Dropbox. Удаляет и сами фото таких объектов из img/listings/<id>/.
    """
    path = path or os.path.join(JS_DIR, "data.js")
    listings = read_js_array(path)
    changed, removed_dirs = 0, []
    for item in listings:
        if not isinstance(item, dict):
            continue
        if item.get("disclosure") != "confidential":
            if strip_private_title(item):
                changed += 1
            continue
        before = json.dumps(item, ensure_ascii=False, sort_keys=True)
        anonymize(item)
        if json.dumps(item, ensure_ascii=False, sort_keys=True) != before:
            changed += 1
        item_id = str(item.get("id") or "")
        folder = os.path.join(root, "img", "listings", item_id)
        if re.fullmatch(r"[\w-]+", item_id) and os.path.isdir(folder):
            removed_dirs.append(folder)
    if dry_run:
        print(f"[sanitize] изменилось бы объектов: {changed}, папок фото к удалению: {len(removed_dirs)}")
        return changed
    if changed:
        _write(path, render_js(listings, "LISTINGS"))
    for folder in removed_dirs:
        shutil.rmtree(folder, ignore_errors=True)
    print(f"[sanitize] объектов исправлено: {changed}, папок фото удалено: {len(removed_dirs)}")
    return changed


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # Windows-консоль (cp1252) не валит кириллицу
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Синхронизация каталога из Notion в js/data.js и js/rentals.js")
    secrets = load_secrets()
    ap.add_argument("--token", default=secrets["NOTION_TOKEN"])
    ap.add_argument("--db", default=secrets["NOTION_DB_ID"], help="ID базы «Objekati»")
    ap.add_argument("--rent-db", default=secrets["NOTION_RENT_DB_ID"], help="ID базы аренды")
    ap.add_argument("--fixture", metavar="PATH", help="страницы «Objekati» из JSON-файла (офлайн, для тестов)")
    ap.add_argument("--rent-fixture", metavar="PATH", help="страницы базы аренды из JSON-файла")
    ap.add_argument("--out-dir", default=JS_DIR, help="куда писать data.js / rentals.js (по умолчанию js/)")
    ap.add_argument("--dry-run", action="store_true", help="показать результат, не записывать файлы")
    ap.add_argument("--sanitize", action="store_true",
                    help="только анонимизировать конфиденциальные объекты в data.js (после dropbox_sync)")
    ap.add_argument("--watch", type=int, metavar="SEC",
                    help="ПОСТОЯННОЕ обновление: пересинхронизировать каждые SEC секунд (напр. 300)")
    args = ap.parse_args(argv)

    if args.sanitize:
        sanitize_file(os.path.join(args.out_dir, "data.js"), dry_run=args.dry_run)
        return

    if args.fixture or args.rent_fixture:
        sync_once(dry_run=args.dry_run, out_dir=args.out_dir,
                  fixture=args.fixture, rent_fixture=args.rent_fixture)
        return

    if not args.token or not (args.db or args.rent_db):
        sys.exit(f"Нужны NOTION_TOKEN и NOTION_DB_ID / NOTION_RENT_DB_ID "
                 f"(env, --token/--db/--rent-db или файл {SECRETS_FILE}).")

    def run():
        sync_once(args.token, args.db, args.rent_db, dry_run=args.dry_run, out_dir=args.out_dir)

    if args.watch:
        print(f"[watch] обновление каждые {args.watch} с. Ctrl+C — стоп.")
        while True:
            try:
                run()
            except Exception as e:  # noqa: BLE001 — не роняем демон из-за разовой ошибки сети
                print(f"[warn] {e}")
            time.sleep(args.watch)
    else:
        try:
            run()
        except NotionError as exc:
            sys.exit(f"[notion] {exc}")


if __name__ == "__main__":
    main()
