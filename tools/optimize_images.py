#!/usr/bin/env python3
"""Адаптивные изображения сайта: WebP нескольких ширин + один JPEG-фолбэк на источник.

Источники (пути относительно корня репозитория) и ширины:
  BG_images/*.jpg              hero         640 / 1024 / 1600 / 2048
  img/listings/**              listing      480 / 800 / 1280 / 1600
  img/placeholders/*           placeholder  480 / 800 / 1200
  img/stock/**                 stock        480 / 800 / 1280 / 1600 / 2048
  img/team/**                  team         320 / 480 / 800 / 1200
  img/logo-*.png               logo         WebP lossless в родном размере; фолбэк — сам PNG

Правила: никогда не увеличиваем (если источник меньше самой большой ширины — последней
идёт его родная ширина), пропорции сохраняются, EXIF-ориентация применяется, метаданные
(EXIF/ICC) выкидываются, цвет приводится к sRGB, прозрачность у фото заливается белым.
Качество WebP 78 (ширины ≥1600 — 72, ширины ≤800 — 70) / JPEG 82 ступенчато снижается, если файл
не влезает в бюджет ширины (KINDS[...]["budgets"]).

Результат:
  img/derivatives/<транслит исходного пути без расширения>-<ширина>.<webp|jpg>
  img/derivatives.json — по строке на источник, ключи отсортированы:
    {"<исходный путь как в data.js/шаблонах>": {
        "width": W, "height": H,                  # размер оригинала после EXIF-поворота
        "webp": [[path, w], ...],                  # по возрастанию ширины
        "jpg":  [[path, w]],                       # фолбэк без WebP (у логотипов — исходный PNG)
        "kind": "hero|listing|placeholder|stock|team|logo",
        "sha1": "<sha1 содержимого источника>", "cfg": "<хеш настроек вида>"}}
  img/og/{default,buy,rent,invest,owners,about}.jpg — 1200×630 для Open Graph.

Инкрементально: источник пропускается, если sha1 и настройки не менялись и все файлы на
месте. Всё, на что не ссылается derivatives.json, удаляется — только внутри img/derivatives/.

Запуск: python tools/optimize_images.py [--check] [--force] [--jobs N]
  --check  ничего не пишет; код выхода 1, если у какого-то источника нет актуальных производных
  --force  пересобрать всё
"""

import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import re
import sys
import unicodedata

try:
    from PIL import Image, ImageChops, ImageCms, ImageFilter, ImageOps
except ImportError:  # pragma: no cover
    sys.exit("[x] Pillow не установлен: python -m pip install -r tools/requirements.txt")


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIV_DIR = "img/derivatives"
MANIFEST = "img/derivatives.json"
OG_DIR = "img/og"
PIPELINE_VERSION = "2"  # поднять, чтобы пересобрать всё при смене алгоритма (2: стартовое качество по ширине)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# widths — целевые ширины; fallback — ширина единственного JPEG; budgets — потолок WebP (КБ)
# для ширины (родные промежуточные ширины берут бюджет ближайшей большей); jpg_kb — потолок JPEG.
KINDS = {
    "hero": {
        "widths": [640, 1024, 1600, 2048], "fallback": 1600,
        "budgets": {640: 80, 1024: 160, 1600: 300, 2048: 340}, "jpg_kb": 420,
    },
    # JPEG-фолбэк 800w: его видят только браузеры без WebP и превью OG — экономим вес репозитория
    "listing": {
        "widths": [480, 800, 1280, 1600], "fallback": 800,
        "budgets": {480: 60, 800: 120, 1280: 260, 1600: 380}, "jpg_kb": 160,
    },
    "placeholder": {
        "widths": [480, 800, 1200], "fallback": 800,
        "budgets": {480: 60, 800: 120, 1200: 220}, "jpg_kb": 160,
    },
    "stock": {
        "widths": [480, 800, 1280, 1600, 2048], "fallback": 1280,
        "budgets": {480: 60, 800: 120, 1280: 240, 1600: 320, 2048: 380}, "jpg_kb": 300,
    },
    "team": {
        "widths": [320, 480, 800, 1200], "fallback": 800,
        "budgets": {320: 30, 480: 60, 800: 120, 1200: 220}, "jpg_kb": 160,
    },
    "logo": {"lossless": True},
}
WEBP_LADDER = (78, 74, 70, 66, 62, 58)
# Стартовое качество WebP по ширине: большие кадры (≥1600, retina-hero) и карточные (≤800) сжимаем
# сильнее — на них артефакты q70–72 не видны, а вес падает на 15–30 %. Дальше — лестница вниз до бюджета.
WEBP_START_LARGE = (1600, 72)   # ширина ≥ 1600 → q72
WEBP_START_CARD = (800, 70)     # ширина ≤ 800 → q70
JPEG_LADDER = (82, 78, 74, 70)
NATIVE_GAP = 1.15  # родную ширину добавляем, только если она заметно больше последней стандартной

# Open Graph: (имя, кандидаты-источники по приоритету, кадр (x, y, zoom): центр в долях
# исходника и увеличение относительно максимального кадра 1200:630). Логотип — внизу слева,
# поэтому кадр выбран так, чтобы слева внизу не было главного объекта.
OG_SIZE = (1200, 630)
OG_SPECS = (
    ("default", ("BG_images/01.jpg",), (0.50, 0.58, 1.0)),
    ("buy", ("BG_images/05.jpg",), (0.50, 0.55, 1.0)),
    ("rent", ("BG_images/04.jpg",), (0.50, 0.62, 1.0)),
    ("invest", ("img/stock/invest-coast.jpg", "BG_images/02.jpg"), (0.55, 0.50, 1.0)),
    ("owners", ("img/stock/owners-interior.jpg", "BG_images/03.jpg"), (0.50, 0.50, 1.0)),
    ("about", ("BG_images/02.jpg",), (0.50, 0.55, 1.0)),
)
OG_LOGOS = ("img/logo-stacked.png", "img/logo-word.png")
OG_KB = 250  # WhatsApp не показывает превью тяжелее ~300 КБ
NAVY = (20, 39, 59)


# ---------------------------------------------------------------------------
# пути и имена

CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g",  # украинский
    "ј": "j", "љ": "lj", "њ": "nj", "ћ": "c", "ђ": "dj", "џ": "dz",  # сербский/черногорский
}
SPECIAL = {"đ": "dj", "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "þ": "th"}


def ascii_component(text):
    """Одна часть пути → ASCII: Ž→z Š→s Č/Ć→c Đ→dj, кириллица → латиница, [^a-z0-9._-] → '-'."""
    out = []
    for ch in unicodedata.normalize("NFC", text).lower():
        if ch in CYRILLIC:
            out.append(CYRILLIC[ch])
        elif ch in SPECIAL:
            out.append(SPECIAL[ch])
        else:
            out.append("".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)))
    slug = re.sub(r"[^a-z0-9._-]", "-", "".join(out))
    slug = re.sub(r"-{2,}", "-", slug).strip("-.")
    return slug or "x"


def ascii_base(key):
    """'img/listings/žb-26-001p/01.jpg' → 'img/listings/zb-26-001p/01'."""
    parts = key.split("/")
    parts[-1] = os.path.splitext(parts[-1])[0]
    return "/".join(ascii_component(p) for p in parts)


def deriv_path(base, width, ext):
    return f"{DERIV_DIR}/{base}-{width}.{ext}"


def abspath(root, rel):
    return os.path.join(root, *rel.split("/"))


def rel_key(root, path):
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    return unicodedata.normalize("NFC", rel)


def sha1_file(path):
    digest = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cfg_hash(kind):
    payload = json.dumps({"v": PIPELINE_VERSION, "kind": kind, "spec": KINDS[kind],
                          "webp": WEBP_LADDER, "webp_start": [WEBP_START_LARGE, WEBP_START_CARD],
                          "jpg": JPEG_LADDER, "gap": NATIVE_GAP}, sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()[:8]


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def write_if_changed(path, data):
    """Пишет файл, только если содержимое отличается (git не видит лишних изменений)."""
    try:
        with open(path, "rb") as fh:
            if fh.read() == data:
                return False
    except OSError:
        pass
    write_atomic(path, data)
    return True


# ---------------------------------------------------------------------------
# поиск источников

def _images_in(folder, recursive):
    if not os.path.isdir(folder):
        return []
    found = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in filenames:
            if not name.startswith(".") and os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                found.append(os.path.join(dirpath, name))
        if not recursive:
            break
    return found


def discover(root):
    """Список (ключ, вид), отсортированный по ключу."""
    sources = {}

    def add(paths, kind):
        for path in paths:
            sources.setdefault(rel_key(root, path), kind)

    hero = [p for p in _images_in(os.path.join(root, "BG_images"), False)
            if os.path.splitext(p)[1].lower() in (".jpg", ".jpeg", ".webp")
            and "logo" not in os.path.basename(p).lower()]
    add(hero, "hero")
    add(_images_in(os.path.join(root, "img", "listings"), True), "listing")
    add(_images_in(os.path.join(root, "img", "placeholders"), False), "placeholder")
    add(_images_in(os.path.join(root, "img", "stock"), True), "stock")
    add(_images_in(os.path.join(root, "img", "team"), True), "team")
    add([p for p in _images_in(os.path.join(root, "img"), False)
         if re.fullmatch(r"logo-.+\.png", os.path.basename(p), flags=re.I)], "logo")
    return sorted(sources.items())


def assign_bases(sources):
    """Уникальная ASCII-основа имени для каждого источника (детерминированно, по порядку ключей)."""
    bases, taken = {}, set()
    for key, _kind in sources:
        base = ascii_base(key)
        if base in taken:
            base = f"{base}-{hashlib.sha1(key.encode()).hexdigest()[:6]}"
        taken.add(base)
        bases[key] = base
    return bases


# ---------------------------------------------------------------------------
# обработка изображений

def target_widths(src_w, widths):
    out = [w for w in widths if w <= src_w]
    if src_w < widths[-1] and (not out or src_w > out[-1] * NATIVE_GAP):
        out.append(src_w)
    return out


def budget_for(spec, width):
    budgets = spec["budgets"]
    bigger = [w for w in sorted(budgets) if w >= width]
    return budgets[bigger[0] if bigger else max(budgets)] * 1024


def display_size(im):
    orientation = im.getexif().get(0x0112, 1)
    w, h = im.size
    return ((h, w) if orientation in (5, 6, 7, 8) else (w, h)), orientation in (5, 6, 7, 8)


def open_prepared(path, need_w=None, keep_alpha=False):
    """Открывает файл, уменьшает декодирование JPEG до нужного, поворачивает по EXIF,
    приводит к sRGB. Возвращает (картинка, (ширина, высота) оригинала после поворота)."""
    im = Image.open(path)
    (dw, dh), swapped = display_size(im)
    if need_w and im.format == "JPEG" and need_w < dw:
        need_h = -(-need_w * dh // dw)
        im.draft(im.mode, (need_h, need_w) if swapped else (need_w, need_h))
    icc = im.info.get("icc_profile")
    im = ImageOps.exif_transpose(im)
    im = to_srgb(im, icc)
    if keep_alpha:
        im = im.convert("RGBA")
    elif im.mode != "RGB":
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, "white")
        flat.paste(rgba, mask=rgba.getchannel("A"))
        im = flat
    im.info = {}
    return im, (dw, dh)


_SRGB = None


def to_srgb(im, icc):
    global _SRGB
    if im.mode == "P":
        im = im.convert("RGBA")
    elif im.mode not in ("RGB", "RGBA", "L", "LA", "CMYK"):
        im = im.convert("RGB")
    if not icc:
        return im.convert("RGB") if im.mode == "CMYK" else im
    try:
        profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if "srgb" in ImageCms.getProfileDescription(profile).lower() and im.mode != "CMYK":
            return im
        if _SRGB is None:
            _SRGB = ImageCms.createProfile("sRGB")
        alpha = im.getchannel("A") if im.mode in ("RGBA", "LA") else None
        base = im.convert("RGB" if im.mode in ("RGBA", "LA") else im.mode) if alpha else im
        converted = ImageCms.profileToProfile(base, profile, _SRGB, outputMode="RGB")
        if alpha is not None:
            converted.putalpha(alpha)
        return converted
    except (OSError, ValueError, ImageCms.PyCMSError):
        return im.convert("RGB") if im.mode == "CMYK" else im


def encode(im, fmt, quality, lossless=False):
    buf = io.BytesIO()
    if fmt == "webp":
        if lossless:
            im.save(buf, "WEBP", lossless=True, quality=100, method=6, exact=False)
        else:
            im.save(buf, "WEBP", quality=quality, method=6)
    else:
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=2)
    return buf.getvalue()


def webp_ladder(width):
    """Лестница качества WebP для ширины: старт по WEBP_START_*, затем ступени WEBP_LADDER ниже старта."""
    if width >= WEBP_START_LARGE[0]:
        start = WEBP_START_LARGE[1]
    elif width <= WEBP_START_CARD[0]:
        start = WEBP_START_CARD[1]
    else:
        return WEBP_LADDER
    return (start,) + tuple(q for q in WEBP_LADDER if q < start)


def encode_within(im, fmt, ladder, budget):
    """Первое качество из лестницы, которое укладывается в бюджет (иначе — минимальное)."""
    for q in ladder:
        data = encode(im, fmt, q)
        if len(data) <= budget:
            return data, q, False
    return data, q, True


def resized(im, size):
    if im.size == size:
        return im.copy()
    out = im.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)
    out.info = {}
    return out


def process_source(root, key, kind, base, sha1):
    """Рабочая функция (в отдельном процессе): пишет файлы, возвращает запись манифеста."""
    spec = KINDS[kind]
    path = abspath(root, key)
    outputs = []  # (путь, байты, бюджет|None, качество, превышен)
    try:
        if kind == "logo":
            im, (dw, dh) = open_prepared(path, keep_alpha=True)
            data = encode(im, "webp", 100, lossless=True)
            webp_rel = deriv_path(base, dw, "webp")
            write_atomic(abspath(root, webp_rel), data)
            outputs.append((webp_rel, len(data), None, "lossless", False))
            entry = {"width": dw, "height": dh, "webp": [[webp_rel, dw]], "jpg": [[key, dw]]}
        else:
            with Image.open(path) as probe:
                (dw, dh), _ = display_size(probe)
            widths = target_widths(dw, spec["widths"])
            im, _ = open_prepared(path, need_w=widths[-1])
            fb_candidates = [w for w in widths if w <= spec["fallback"]]
            fb_w = fb_candidates[-1] if fb_candidates else widths[0]
            webp, jpg = [], []
            for w in widths:
                frame = resized(im, (w, max(1, round(w * dh / dw))))
                budget = budget_for(spec, w)
                data, q, over = encode_within(frame, "webp", webp_ladder(w), budget)
                rel = deriv_path(base, w, "webp")
                write_atomic(abspath(root, rel), data)
                outputs.append((rel, len(data), budget, q, over))
                webp.append([rel, w])
                if w == fb_w:
                    budget = spec["jpg_kb"] * 1024
                    data, q, over = encode_within(frame, "jpg", JPEG_LADDER, budget)
                    rel = deriv_path(base, w, "jpg")
                    write_atomic(abspath(root, rel), data)
                    outputs.append((rel, len(data), budget, q, over))
                    jpg.append([rel, w])
            entry = {"width": dw, "height": dh, "webp": webp, "jpg": jpg}
        entry.update({"kind": kind, "sha1": sha1, "cfg": cfg_hash(kind)})
        return {"key": key, "entry": entry, "outputs": outputs, "error": None}
    except Exception as exc:  # битый файл не должен срывать остальные
        return {"key": key, "entry": None, "outputs": outputs, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Open Graph

def _gradient(size, fn, vertical):
    """Маска L размера size: значение fn(t), t ∈ [0, 1] вдоль оси (сверху вниз или слева направо)."""
    length = size[1] if vertical else size[0]
    strip = Image.new("L", (1, length) if vertical else (length, 1))
    strip.putdata([max(0, min(255, round(255 * fn(i / (length - 1))))) for i in range(length)])
    return strip.resize(size, Image.Resampling.NEAREST)


def build_og(root, src_key, frame):
    W, H = OG_SIZE
    fx, fy, zoom = frame
    im, _ = open_prepared(abspath(root, src_key), need_w=round(W * 2 * zoom))
    # кадр 1200:630 вокруг фокуса (не меньше 1200×630 пикселей исходника)
    sw, sh = im.size
    if sw / sh > W / H:
        cw, ch = sh * W / H, sh
    else:
        cw, ch = sw, sw * H / W
    scale = max(1.0, min(zoom, cw / W))
    cw, ch = round(cw / scale), round(ch / scale)
    left = min(max(0, round(fx * sw - cw / 2)), sw - cw)
    top = min(max(0, round(fy * sh - ch / 2)), sh - ch)
    photo = im.crop((left, top, left + cw, top + ch)).resize((W, H), Image.Resampling.LANCZOS)

    # мягкое затемнение navy: снизу (под логотип) и слева, плюс лёгкая общая вуаль
    def ease(t):
        return t * t * (3 - 2 * t)
    bottom = _gradient((W, H), lambda y: 0.82 * ease(max(0.0, (y - 0.36) / 0.64)), vertical=True)
    left_g = _gradient((W, H), lambda x: 0.40 * ease(max(0.0, 1 - x / 0.62)), vertical=False)
    mask = ImageChops.screen(ImageChops.screen(bottom, left_g), Image.new("L", (W, H), 18))
    canvas = Image.composite(Image.new("RGB", (W, H), NAVY), photo, mask)

    logo_key = next((k for k in OG_LOGOS if os.path.isfile(abspath(root, k))), None)
    if logo_key:
        with Image.open(abspath(root, logo_key)) as raw:
            logo = raw.convert("RGBA")
        logo = logo.crop(logo.getchannel("A").getbbox())
        target_w = min(300 if "stacked" in logo_key else 380, logo.width)
        size = (target_w, round(logo.height * target_w / logo.width))
        logo = logo.convert("RGBa").resize(size, Image.Resampling.LANCZOS).convert("RGBA")
        x, y = 64, H - 56 - logo.height
        # тень под логотипом для читаемости на светлых участках
        shadow_alpha = logo.getchannel("A").point(lambda a: a * 0.55)
        pad = 24
        shadow = Image.new("L", (logo.width + 2 * pad, logo.height + 2 * pad))
        shadow.paste(shadow_alpha, (pad, pad))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        canvas.paste(Image.new("RGB", shadow.size, (8, 18, 29)), (x - pad, y - pad + 2), shadow)
        canvas.paste(logo, (x, y), logo)
    data, _q, _over = encode_within(canvas, "jpg", JPEG_LADDER, OG_KB * 1024)
    return data


def og_jobs(root):
    jobs = []
    for name, candidates, frame in OG_SPECS:
        src = next((c for c in candidates if os.path.isfile(abspath(root, c))), None)
        jobs.append((name, src, frame))
    return jobs


# ---------------------------------------------------------------------------
# манифест

def load_manifest(root):
    try:
        with open(abspath(root, MANIFEST), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def dump_manifest(manifest):
    keys = sorted(manifest)
    lines = ["{"]
    for i, key in enumerate(keys):
        entry = json.dumps(manifest[key], ensure_ascii=False, sort_keys=True, separators=(", ", ": "))
        lines.append(f"  {json.dumps(key, ensure_ascii=False)}: {entry}{',' if i < len(keys) - 1 else ''}")
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def is_current(root, key, kind, base, sha1, entry):
    if not isinstance(entry, dict):
        return False
    if entry.get("sha1") != sha1 or entry.get("kind") != kind or entry.get("cfg") != cfg_hash(kind):
        return False
    webp, jpg = entry.get("webp") or [], entry.get("jpg") or []
    if not webp or not jpg:
        return False
    for rel, w in webp:
        if rel != deriv_path(base, w, "webp") or not os.path.isfile(abspath(root, rel)):
            return False
    for rel, w in jpg:
        expected = key if kind == "logo" else deriv_path(base, w, "jpg")
        if rel != expected or not os.path.isfile(abspath(root, rel)):
            return False
    return True


def sweep(root, manifest):
    """Удаляет из img/derivatives всё, на что манифест не ссылается. Возвращает число файлов."""
    keep = {os.path.normcase(abspath(root, rel))
            for entry in manifest.values() for rel, _w in entry["webp"] + entry["jpg"]}
    top = abspath(root, DERIV_DIR)
    removed = 0
    if not os.path.isdir(top):
        return 0
    for dirpath, _dirs, files in os.walk(top, topdown=False):
        for name in files:
            full = os.path.join(dirpath, name)
            if os.path.normcase(full) not in keep:
                os.remove(full)
                removed += 1
        if dirpath != top and not os.listdir(dirpath):
            os.rmdir(dirpath)
    return removed


# ---------------------------------------------------------------------------
# отчёт

def mb(n):
    return f"{n / 1048576:.1f} MB"


def kb(n):
    return f"{n / 1024:.0f} KB"


def report(root, sources, manifest, generated, attempted, failures, removed, og_written):
    sizes, kinds = {}, {}
    src_total = 0
    for key, kind in sources:
        size = os.path.getsize(abspath(root, key))
        src_total += size
        k = kinds.setdefault(kind, {"n": 0, "src": 0, "out": 0})
        k["n"] += 1
        k["src"] += size
        entry = manifest.get(key)
        if not entry:
            continue
        for rel, _w in entry["webp"] + (entry["jpg"] if kind != "logo" else []):
            sizes[rel] = os.path.getsize(abspath(root, rel))
            k["out"] += sizes[rel]
    out_total = sum(sizes.values())
    webp_total = sum(v for p, v in sizes.items() if p.endswith(".webp"))
    print(f"[*] источников: {len(sources)} ({mb(src_total)}); производных: {len(sizes)} файлов, "
          f"{mb(out_total)} (webp {mb(webp_total)}, jpg {mb(out_total - webp_total)})")
    print(f"[*] пересобрано: {generated}, без изменений: {len(sources) - attempted}, "
          f"удалено устаревших: {removed}, OG обновлено: {og_written}")
    for kind, k in sorted(kinds.items()):
        print(f"    {kind:<12} {k['n']:>3} шт.  {mb(k['src']):>9} → {mb(k['out']):>8}")

    # что реально грузит страница: одна webp нужной ширины вместо оригинала
    def width_stats(kind, width):
        vals = [(sizes[rel], key) for key, k in sources if k == kind and key in manifest
                for rel, w in manifest[key]["webp"] if w == width and rel in sizes]
        return vals

    checks = [("hero", 1600, 300), ("hero", 2048, 340), ("listing", 480, 60), ("listing", 800, 120),
              ("placeholder", 480, 60), ("placeholder", 800, 120), ("stock", 800, 120), ("stock", 1600, 320)]
    print("[*] цели (webp):")
    for kind, width, limit in checks:
        vals = width_stats(kind, width)
        if not vals:
            continue
        biggest, who = max(vals)
        avg = sum(v for v, _ in vals) / len(vals)
        mark = "ok" if biggest <= limit * 1024 else "!!"
        print(f"    [{mark}] {kind} {width}w: средн. {kb(avg)}, макс. {kb(biggest)} ({who}) — цель ≤ {limit} KB")
    print("[*] самые крупные файлы:")
    for rel, size in sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:10]:
        print(f"    {kb(size):>7}  {rel}")
    for key, err in failures:
        print(f"[x] {key}: {err}")


# ---------------------------------------------------------------------------

def main():
    for stream in (sys.stdout, sys.stderr):  # кириллица в консоли Windows (как build_site.py)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    parser = argparse.ArgumentParser(description="WebP/JPEG-производные изображений + img/derivatives.json + OG")
    parser.add_argument("--check", action="store_true", help="только проверить; 1 — если что-то не собрано")
    parser.add_argument("--force", action="store_true", help="пересобрать всё")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 2), help="параллельных процессов")
    parser.add_argument("--root", default=PROJECT_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = os.path.abspath(args.root)

    sources = discover(root)
    bases = assign_bases(sources)
    old = load_manifest(root)
    todo, manifest = [], {}
    for key, kind in sources:
        sha1 = sha1_file(abspath(root, key))
        if not args.force and is_current(root, key, kind, bases[key], sha1, old.get(key)):
            manifest[key] = old[key]
        else:
            todo.append((key, kind, bases[key], sha1))

    if args.check:
        stale_og = [f"{OG_DIR}/{name}.jpg" for name, src, _f in og_jobs(root)
                    if src and not os.path.isfile(abspath(root, f"{OG_DIR}/{name}.jpg"))]
        stale_entries = sorted(set(old) - {k for k, _ in sources})
        for key, kind, _b, _s in todo:
            print(f"[?] нет актуальных производных: {key} ({kind})")
        for rel in stale_og:
            print(f"[?] нет OG-картинки: {rel}")
        for key in stale_entries:
            print(f"[?] в манифесте запись без источника: {key}")
        if todo or stale_og or stale_entries:
            print(f"[x] не собрано: {len(todo)} источник(ов), OG: {len(stale_og)}, лишних записей: {len(stale_entries)}"
                  " — запустите python tools/optimize_images.py")
            return 1
        print(f"[ok] все {len(sources)} источников и OG-картинки актуальны")
        return 0

    failures = []
    if todo:
        print(f"[*] обработка {len(todo)} из {len(sources)} источников ({args.jobs} проц.)…", flush=True)
        if args.jobs > 1 and len(todo) > 1:
            with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
                results = list(pool.map(process_source, *zip(*[(root, *t) for t in todo])))
        else:
            results = [process_source(root, *t) for t in todo]
        for res in results:
            if res["error"]:
                failures.append((res["key"], res["error"]))
                continue
            manifest[res["key"]] = res["entry"]
            for rel, size, budget, q, over in res["outputs"]:
                if over:
                    print(f"[?] {rel}: {kb(size)} при минимальном качестве {q} — больше бюджета {kb(budget)}")

    write_if_changed(abspath(root, MANIFEST), dump_manifest(manifest))
    removed = sweep(root, manifest)

    generated = len(todo) - len(failures)
    og_written = 0
    for name, src, frame in og_jobs(root):
        if not src:
            print(f"[?] OG {name}: нет ни одного источника из списка")
            continue
        try:
            data = build_og(root, src, frame)
        except Exception as exc:
            failures.append((f"{OG_DIR}/{name}.jpg", f"{type(exc).__name__}: {exc}"))
            continue
        og_written += write_if_changed(abspath(root, f"{OG_DIR}/{name}.jpg"), data)

    report(root, sources, manifest, generated, len(todo), failures, removed, og_written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
