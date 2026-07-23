#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gurevic Real Estate — синхронизация каталога из Notion CRM в js/data.js.

Тянет объекты из базы Notion и переписывает массив LISTINGS в js/data.js.
Справочники (js/config.js) не трогает. Работает на стандартной библиотеке
(urllib) — без pip-зависимостей.

Notion-часть (notion_query_all + prop_*) написана универсально —
её можно переиспользовать в других проектах.

------------------------------------------------------------------
ПОДГОТОВКА (делает риелтор/владелец базы, один раз):
  1. https://www.notion.so/my-integrations → New integration → скопировать
     "Internal Integration Secret" (токен вида secret_xxx или ntn_xxx).
  2. Открыть нужную базу в Notion → ••• → Connections → добавить эту интеграцию.
     (Доступ на почту для API НЕ работает — нужен именно шаг Connections.)
  3. Скопировать Database ID из URL базы:
     notion.so/<workspace>/<DATABASE_ID>?v=...  — 32 hex-символа.

ЗАПУСК:
  set NOTION_TOKEN=secret_xxx        (Windows: setx или переменная окружения)
  set NOTION_DB_ID=xxxxxxxx...
  python tools/notion_sync.py --dry-run      # показать, что получится
  python tools/notion_sync.py                # записать в js/data.js

Или явно:
  python tools/notion_sync.py --token secret_xxx --db <DATABASE_ID>
------------------------------------------------------------------

ГЛАВНОЕ, ЧТО НАСТРАИВАЕТСЯ ПОД КОНКРЕТНУЮ БАЗУ — словарь FIELD_MAP ниже:
слева ключ объекта на сайте, справа — ТОЧНОЕ имя колонки в Notion.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"

# Секреты берём ВНЕ веб-папки (иначе токен был бы скачиваем по URL!).
# Файл формата KEY=VALUE: NOTION_TOKEN=... / NOTION_DB_ID=...
SECRETS_FILE = os.path.join(
    os.path.expanduser("~"), ".config", "gurevic", "notion.env"
)


def load_secrets():
    """Токен/ID: сначала переменные окружения, затем файл вне веб-папки."""
    tok = os.environ.get("NOTION_TOKEN")
    db = os.environ.get("NOTION_DB_ID")
    if (not tok or not db) and os.path.exists(SECRETS_FILE):
        for line in open(SECRETS_FILE, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "NOTION_TOKEN" and not tok:
                tok = v.strip()
            if k.strip() == "NOTION_DB_ID" and not db:
                db = v.strip()
    return tok, db

# Куда писать (относительно корня проекта = родитель папки tools/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(PROJECT_ROOT, "js", "data.js")

# ------------------------------------------------------------------
# СООТВЕТСТВИЕ ПОЛЕЙ: поле на сайте  ->  имя колонки в Notion.
# Поменяйте правую часть под реальные названия колонок вашей базы.
# Тип колонки в Notion распознаётся автоматически (title/number/select/…).
# ------------------------------------------------------------------
FIELD_MAP = {
    "title":     "Название",       # заголовок объекта (тип Title)
    "type":      "Тип",            # Квартира/Дом/Участок/Коммерческая/Отель (Select)
    "deal":      "Сделка",         # Продажа/Аренда (Select)
    "location":  "Район",          # Select или Text
    "price":     "Цена",           # Number (€)
    "area":      "Площадь",        # Number (м²)
    "landArea":  "Участок",        # Number (м²), для домов/участков
    "rooms":     "Спальни",        # Text/Select ("2 спальни", "студия")
    "short":     "Краткое",        # короткое описание (Text)
    "desc":      "Описание",       # полное описание (Text)
    "features":  "Особенности",    # Multi-select -> список чипов
    "status":    "Статус",         # напр. Активно/Продано (Select) — фильтр ниже
    "lat":       "Широта",         # Number (необязательно) — точка на карте
    "lng":       "Долгота",        # Number (необязательно)
    "invest":    "Инвестиции",     # Checkbox -> объект попадает в блок «Под инвестиции»
    "isComplex": "Комплекс",       # Checkbox -> блок «Жилые комплексы»
}

# Русские названия типов/сделок в Notion -> ключи сайта
TYPE_RU2KEY = {
    "квартира": "apartment", "апартаменты": "apartment",
    "дом": "house", "вилла": "house", "дом / вилла": "house",
    "участок": "land", "земля": "land",
    "коммерческая": "commercial", "коммерция": "commercial",
    "отель": "hotel",
}
DEAL_RU2KEY = {"продажа": "sale", "sale": "sale", "аренда": "rent", "rent": "rent"}

# Публиковать только объекты с таким статусом (пусто = публиковать все)
PUBLISH_STATUSES = {"активно", "актуально", "в продаже", "published", ""}


# ============ Notion API (переиспользуемая часть) ============
def _req(path, token, method="GET", body=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"[notion] HTTP {e.code}: {e.read().decode()[:400]}")


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


# ---- извлечение значений из свойств Notion ----
def prop_value(props, name):
    """Достаёт значение свойства Notion по имени, независимо от типа."""
    p = props.get(name)
    if not p:
        return None
    t = p.get("type")
    if t == "title":
        return "".join(x["plain_text"] for x in p["title"]).strip() or None
    if t == "rich_text":
        return "".join(x["plain_text"] for x in p["rich_text"]).strip() or None
    if t == "number":
        return p["number"]
    if t == "select":
        return p["select"]["name"] if p["select"] else None
    if t == "multi_select":
        return [o["name"] for o in p["multi_select"]]
    if t == "status":
        return p["status"]["name"] if p["status"] else None
    if t == "checkbox":
        return p["checkbox"]
    if t == "url":
        return p["url"]
    if t == "files":
        out = []
        for f in p["files"]:
            out.append(f.get("external", {}).get("url") or f.get("file", {}).get("url"))
        return [u for u in out if u]
    if t == "date":
        return p["date"]["start"] if p["date"] else None
    return None


def slugify(text, fallback):
    s = re.sub(r"[^\w\s-]", "", (text or "").lower(), flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    # транслит нескольких частых символов, чтобы id был ASCII-дружелюбным
    return s or fallback


# ============ маппинг Notion -> объект сайта ============
def page_to_listing(page):
    props = page.get("properties", {})
    g = lambda key: prop_value(props, FIELD_MAP[key]) if FIELD_MAP.get(key) else None

    status = (g("status") or "").strip().lower()
    if PUBLISH_STATUSES and status not in PUBLISH_STATUSES:
        return None  # объект не для публикации

    title = g("title") or "Без названия"
    type_ru = (g("type") or "").strip().lower()
    deal_ru = (g("deal") or "").strip().lower()

    listing = {
        "id": slugify(title, page["id"][:8]),
        "title": title,
        "type": TYPE_RU2KEY.get(type_ru, "apartment"),
        "deal": DEAL_RU2KEY.get(deal_ru, "sale"),
        "location": g("location") or "Будва — центр",
    }
    price = g("price")
    if price is not None:
        listing["price"] = int(price)
    for k in ("area", "landArea"):
        v = g(k)
        if v is not None:
            listing[k] = v
    for k in ("rooms", "short", "desc"):
        v = g(k)
        if v:
            listing[k] = v
    feats = g("features")
    if feats:
        listing["features"] = feats
    if g("invest"):
        listing["invest"] = True
        listing["investKind"] = "Инвестиция"
    if g("isComplex"):
        listing["isComplex"] = True
    lat, lng = g("lat"), g("lng")
    if lat is not None and lng is not None:
        listing["coords"] = [lat, lng]
    # hue для плейсхолдер-фото (пока нет реальных фото)
    listing["hue"] = (abs(hash(listing["id"])) % 360)
    listing.setdefault("features", [])
    listing.setdefault("desc", listing.get("short", title))
    listing.setdefault("short", "")
    return listing


def render_data_js(listings):
    header = (
        "// ============================================================\n"
        "// Gurevic Real Estate — БАЗА ОБЪЕКТОВ (LISTINGS).\n"
        "// АВТОСГЕНЕРИРОВАНО из Notion скриптом tools/notion_sync.py — не править вручную.\n"
        "// Справочники и координаты — в js/config.js.\n"
        "// ============================================================\n\n"
        "const LISTINGS =\n"
    )
    body = json.dumps(listings, ensure_ascii=False, indent=2)
    return header + body + ";\n"


def sync_once(token, db, dry_run=False):
    pages = notion_query_all(token, db)
    listings = [x for x in (page_to_listing(p) for p in pages) if x]
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] Notion: страниц {len(pages)}, к публикации {len(listings)}")
    out = render_data_js(listings)
    if dry_run:
        print(out[:2000] + ("\n… (обрезано)" if len(out) > 2000 else ""))
        print("\n[dry-run] файл НЕ записан.")
        return
    with open(DATA_JS, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"[{ts}] ok: {len(listings)} объектов → {DATA_JS}")


def main():
    ap = argparse.ArgumentParser(description="Синхронизация каталога из Notion в js/data.js")
    env_tok, env_db = load_secrets()
    ap.add_argument("--token", default=env_tok)
    ap.add_argument("--db", default=env_db)
    ap.add_argument("--dry-run", action="store_true", help="показать результат, не записывать файл")
    ap.add_argument("--watch", type=int, metavar="SEC",
                    help="ПОСТОЯННОЕ обновление: пересинхронизировать каждые SEC секунд (напр. 300)")
    args = ap.parse_args()

    if not args.token or not args.db:
        sys.exit(f"Нужны NOTION_TOKEN и NOTION_DB_ID (env, --token/--db или файл {SECRETS_FILE}).")

    if args.watch:
        print(f"[watch] обновление каждые {args.watch} с. Ctrl+C — стоп.")
        while True:
            try:
                sync_once(args.token, args.db)
            except Exception as e:  # noqa: BLE001 — не роняем демон из-за разовой ошибки сети
                print(f"[warn] {e}")
            time.sleep(args.watch)
    else:
        sync_once(args.token, args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
