"""Text helpers: ASCII slugs, transliteration, normalization for keyword matching."""

import re
import unicodedata

# Кириллица → латиница (ru + uk), для slug'ов из названий
_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e", "ё": "e",
    "є": "ye", "ж": "zh", "з": "z", "и": "i", "і": "i", "ї": "yi", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
# Латиница Черногории/Сербии
_LAT = {"ž": "z", "š": "s", "č": "c", "ć": "c", "đ": "dj", "dž": "dz"}
# Кириллические буквы, визуально совпадающие с латинскими: в CRM-ID встречается
# «СT-24-001P» с русской «С» — это «CT», а не «ST».
_HOMOGLYPH = {
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p",
    "с": "c", "т": "t", "х": "x", "у": "y", "і": "i",
}
_OBJECT_ID_RE = re.compile(r"^[a-z]{2}-\d{2}-\d+[a-z]?$")


def _strip_marks(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _latinize(s, table):
    out = []
    for ch in s:
        out.append(table.get(ch, ch))
    return "".join(out)


def _ascii_slug(s):
    s = _strip_marks(s)
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return re.sub(r"-{2,}", "-", s).strip("-")


def slugify(text):
    """ASCII slug: lowercase, Ž→z Š→s Č/Ć→c Đ→dj, Cyrillic→Latin, [^a-z0-9-] removed.

    Object IDs written with Cyrillic look-alikes ("СT-24-001P") are mapped by shape
    (→ "ct-24-001p") so the slug matches what people read.
    """
    s = (text or "").strip().lower()
    if not s:
        return ""
    s = s.replace("dž", "dz")
    glyph = _ascii_slug(_latinize(_latinize(s, _HOMOGLYPH), _LAT))
    if _OBJECT_ID_RE.match(glyph):
        return glyph
    return _ascii_slug(_latinize(_latinize(s, _LAT), _CYR))


def normalize(text):
    """Lowercase, diacritics stripped (č→c, ž→z, đ→dj) — for keyword matching."""
    s = (text or "").lower().replace("đ", "dj")
    return _strip_marks(s)


# Сокращения, после точки которых предложение не кончается («Réf. BD-25-001»)
_ABBREV = {"réf", "ref", "nr", "no", "n°", "ul", "ул", "вул", "г", "д", "str", "tel", "тел"}


def truncate(text, limit=160, min_sentence=100):
    """Cut text to at most `limit` chars.

    Prefers, in this order (each only when at least `min_sentence` chars remain):
    a whole sentence; the last sentence cut before its « — » tail and closed with
    a period («…запрос просмотра — агентство GUREVIĆ» → «…запрос просмотра.»);
    otherwise a word boundary plus an ellipsis — meta descriptions read better
    without «…агентство…»."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    head = text[: limit + 1]  # «… Будва.» ровно на границе тоже годится
    for m in reversed(list(re.finditer(r"[.!?](?= )", head))):
        end = m.end()
        if end < min_sentence:
            break
        word = head[:m.start()].rsplit(" ", 1)[-1].lower()
        if len(word) <= 1 or word in _ABBREV:
            continue
        return head[:end]
    dash = max(head.rfind(" — ", 0, limit), head.rfind(" – ", 0, limit))
    if dash >= min_sentence:
        return head[:dash].rstrip(" ,;:") + "."
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:—–-") + "…"
