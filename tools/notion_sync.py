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
import urllib.parse

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
# СООТВЕТСТВИЕ ПОЛЕЙ: поле на сайте -> имя колонки в базе «Objekati».
# Приватные колонки CRM (Owner Name, Provizija, List Nep., Documents
# Folder, Person, Cadastral Municipality) НА САЙТ НЕ ПОПАДАЮТ.
# ------------------------------------------------------------------
FIELD_MAP = {
    "title":     "Aktualnost",     # Title — название объекта
    "objectId":  "Object ID",      # BD-26-019S — используется как id
    "type":      "Property Type",  # House/Apartment/Land/Commercial/…/Hotel/Gradnja
    "price":     "Cijena",         # Number (€)
    "area":      "Interjer (m²)",  # Number (м²)
    "landArea":  "Land (m²)",      # Number (м²)
    "rooms":     "Sp. sobe",       # Number — спальни
    "location":  "Location",       # полный адрес — публикуем ТОЛЬКО район
    "mapLink":   "Map Link",       # Google Maps short-link → координаты
    "features":  "Особенности",    # Multi-select — публичные преимущества объекта
    # Точное название колонки с фото задаётся через NOTION_PHOTOS_FIELD.
    # Значение намеренно не хранится в репозитории.
    "images":    os.environ.get("NOTION_PHOTOS_FIELD", ""),
    "status":    "Status",         # Adding/Available/For Re-evaluation/Reserved/Sold
}

# Property Type (англ.) -> ключ типа на сайте (+ инвест-блок для Hotel/Gradnja)
TYPE_EN2KEY = {
    "apartment": "apartment", "house": "house", "land": "land",
    "commercial": "commercial", "industrial": "commercial",
    "office": "commercial", "retail": "commercial",
    "hotel": "hotel", "gradnja": "land",
}
INVEST_KINDS = {"hotel": "Отель — готовый бизнес", "gradnja": "Девелопмент"}

# Публикуем только эти статусы
PUBLISH_STATUSES = {"available"}

# Детект района из адресной строки (публикуем район, а не точный адрес)
DISTRICTS = [
    (("lastva grbaljska", "lastve grbaljskoj", "lustve grbaljskoj"), "Ластва Грбальска"),
    (("bečići", "becici", "beċići"), "Бечичи"),
    (("rafailovići", "rafailovici"), "Рафаиловичи"),
    (("pržno", "przno"), "Пржно"),
    (("sveti stefan", "sv. stefan", "sveti-stefan"), "Свети-Стефан"),
    (("rozino",), "Будва — Розино"),
    (("boreti",), "Бечичи"),
    (("lapčići", "lapcici"), "Лапчичи"),
    (("tudorovići", "tudorovici"), "Тудоровичи"),
    (("budva",), "Будва — центр"),
]

def detect_district(*texts):
    """Определяет район по адресу и названию, не публикуя точный адрес."""
    s = " ".join(str(x or "") for x in texts).lower()
    for keys, ru in DISTRICTS:
        if any(k in s for k in keys):
            return ru
    return "Будва — центр"


# ---- Map Link (maps.app.goo.gl) -> координаты, с кэшем ----
COORD_CACHE_FILE = os.path.join(os.path.dirname(SECRETS_FILE), "maplink_cache.json")
_RE_AT = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
_RE_3D4D = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
_RE_Q = re.compile(r"[?&]q=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)")

def _load_coord_cache():
    try:
        return json.load(open(COORD_CACHE_FILE, encoding="utf-8"))
    except Exception:
        return {}

def _save_coord_cache(cache):
    os.makedirs(os.path.dirname(COORD_CACHE_FILE), exist_ok=True)
    json.dump(cache, open(COORD_CACHE_FILE, "w", encoding="utf-8"))

def resolve_map_link(url, cache):
    """Следует редиректу goo.gl-ссылки и достаёт [lat, lng]. None при неудаче."""
    if not url:
        return None
    if url in cache:
        return cache[url]
    coords = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            final = r.geturl()
            html = r.read(200000).decode("utf-8", "ignore")
        for rx in (_RE_AT, _RE_3D4D, _RE_Q):
            m = rx.search(final) or rx.search(html)
            if m:
                coords = [round(float(m.group(1)), 6), round(float(m.group(2)), 6)]
                break
    except Exception:
        coords = None
    cache[url] = coords
    return coords


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


IMAGE_DIR = os.path.join(PROJECT_ROOT, "img", "listings")
IMAGE_LIMIT = 6
IMAGE_MAX_BYTES = 12 * 1024 * 1024
IMAGE_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def download_images(urls, listing_id):
    """Сохраняет фото из Notion как публичные файлы сайта.

    Notion выдаёт временные URL, поэтому в js/data.js сохраняются только
    относительные пути к скачанным изображениям, а не исходные ссылки.
    """
    if not urls:
        return []
    target_dir = os.path.join(IMAGE_DIR, listing_id)
    os.makedirs(target_dir, exist_ok=True)
    paths = []
    for index, url in enumerate(urls[:IMAGE_LIMIT], start=1):
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https":
                continue
            req = urllib.request.Request(url, headers={"User-Agent": "GurevicEstateSync/1.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                content_type = response.headers.get_content_type().lower()
                if content_type not in IMAGE_EXTENSIONS:
                    continue
                data = response.read(IMAGE_MAX_BYTES + 1)
            if len(data) > IMAGE_MAX_BYTES:
                continue
            filename = f"photo-{index}{IMAGE_EXTENSIONS[content_type]}"
            destination = os.path.join(target_dir, filename)
            with open(destination, "wb") as image_file:
                image_file.write(data)
            paths.append(f"img/listings/{listing_id}/{filename}")
        except Exception as exc:  # отдельное фото не должно срывать публикацию каталога
            print(f"[warn] фото {listing_id}/{index} не скачано: {exc}")
    return paths


# ============ маппинг Notion -> объект сайта ============
TYPE_RU = {
    "apartment": "Квартира", "house": "Дом", "land": "Участок",
    "commercial": "Коммерческое помещение", "hotel": "Отель",
}

def rooms_ru(n):
    n = int(n)
    if n == 1:
        return "1 спальня"
    if 2 <= n <= 4:
        return f"{n} спальни"
    return f"{n} спален"


def page_to_listing(page, coord_cache):
    props = page.get("properties", {})
    g = lambda key: prop_value(props, FIELD_MAP[key]) if FIELD_MAP.get(key) else None

    status = (g("status") or "").strip().lower()
    if PUBLISH_STATUSES and status not in PUBLISH_STATUSES:
        return None  # публикуем только Available

    obj_id = (g("objectId") or "").strip()
    type_en = (g("type") or "").strip().lower()
    tkey = TYPE_EN2KEY.get(type_en, "apartment")
    title = (g("title") or "").strip()
    district = detect_district(g("location"), title)
    area = g("area")
    land = g("landArea")
    rooms_n = g("rooms")
    price = g("price")

    if not title:
        # автозаголовок, если риелтор не заполнил Aktualnost
        bits = [TYPE_RU.get(tkey, "Объект")]
        if area:
            bits.append(f"{int(area)} м²")
        title = " ".join(bits) + f" — {district}"

    listing = {
        "id": slugify(obj_id or title, page["id"][:8]),
        "objectId": obj_id or None,
        "title": title,
        "type": tkey,
        "deal": "sale",              # в CRM нет колонки аренды — всё продажа
        "location": district,        # только район; точный адрес не публикуем
        "price": int(price) if price else 0,
    }
    if not price:
        listing["priceNote"] = "Цена по запросу"
    if area:
        listing["area"] = area
    if land:
        listing["landArea"] = land
    if rooms_n:
        listing["rooms"] = rooms_ru(rooms_n)

    if type_en in INVEST_KINDS:
        listing["invest"] = True
        listing["investKind"] = INVEST_KINDS[type_en]
    if type_en == "gradnja":
        listing["isComplex"] = True

    coords = resolve_map_link(g("mapLink"), coord_cache)
    if coords:
        listing["coords"] = coords

    images = download_images(g("images") or [], listing["id"])
    if images:
        listing["images"] = images

    # авто-описания (в CRM нет текстов; фото добавим позже из презентаций)
    p_bits = []
    if area:
        p_bits.append(f"площадь {int(area)} м²")
    if land:
        p_bits.append(f"участок {int(land)} м²")
    if rooms_n:
        p_bits.append(rooms_ru(rooms_n))
    params_txt = (", ".join(p_bits)) or "параметры уточняются"
    listing["short"] = f"{TYPE_RU.get(tkey, 'Объект')} в районе {district}: {params_txt}."
    listing["desc"] = (
        f"{title}.\n\n{TYPE_RU.get(tkey, 'Объект')} в районе {district} ({params_txt})."
        + (f" Идентификатор объекта: {obj_id}." if obj_id else "")
        + "\n\nФотографии и подробное описание предоставим по запросу — свяжитесь с нами"
        " в чате или по телефону, и риелтор пришлёт полную презентацию объекта."
    )
    raw_features = g("features") or []
    if isinstance(raw_features, str):
        raw_features = re.split(r"[,;\n]+", raw_features)
    listing["features"] = [str(feature).strip() for feature in raw_features if str(feature).strip()]
    listing["photos"] = len(images) or 4
    listing["hue"] = (abs(hash(listing["id"])) % 360)
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
    cache = _load_coord_cache()
    listings = [x for x in (page_to_listing(p, cache) for p in pages) if x]
    _save_coord_cache(cache)
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
