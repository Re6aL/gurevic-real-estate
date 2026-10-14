"""Locale number/price formatting and plural categories (no external deps)."""

NBSP = " "

# lang → (разделитель тысяч, десятичный разделитель)
_SEP = {
    "ru": (NBSP, ","), "uk": (NBSP, ","), "fr": (NBSP, ","), "pl": (NBSP, ","),
    "de": (".", ","), "en": (",", "."), "he": (",", "."),
}
# lang → шаблон цены: € перед числом или после
_PRICE = {
    "ru": "€{n}", "en": "€{n}", "he": "€{n}",
    "de": "{n}" + NBSP + "€", "fr": "{n}" + NBSP + "€", "pl": "{n}" + NBSP + "€", "uk": "{n}" + NBSP + "€",
}


def _number(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        text = str(value).replace(" ", "").replace(NBSP, "").replace(",", ".")
        return float(text) if "." in text else int(text)
    except ValueError:
        return None


def fmt_num(value, lang, decimals=None):
    """Grouped number: 213000 → '213 000' (ru) / '213,000' (en) / '213.000' (de)."""
    n = _number(value)
    if n is None:
        return str(value) if value not in (None, "") else ""
    group, dec = _SEP.get(lang, _SEP["en"])
    if decimals is None:
        decimals = 0 if float(n).is_integer() else 1
    text = f"{abs(n):,.{decimals}f}"
    whole, _, frac = text.partition(".")
    whole = whole.replace(",", group)
    out = whole + (dec + frac if frac else "")
    return ("-" if n < 0 else "") + out


def fmt_price(value, lang):
    """Price without the 'on request' / per-month logic (see render.fmt_price)."""
    return _PRICE.get(lang, _PRICE["en"]).format(n=fmt_num(round(_number(value) or 0), lang))


def plural_category(n, lang):
    """CLDR-like plural category for integers: one | few | many | other."""
    try:
        n = abs(int(n))
    except (TypeError, ValueError):
        return "other"
    if lang in ("ru", "uk"):
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if lang == "pl":
        if n == 1:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if lang == "fr":
        return "one" if n in (0, 1) else "other"
    if lang == "he":
        if n == 1:
            return "one"
        if n == 2:
            return "two"
        return "other"
    return "one" if n == 1 else "other"


# Цепочка запасных категорий, если в словаре нет нужной формы
PLURAL_FALLBACK = {"one": ("one", "other"), "two": ("two", "other", "many"),
                   "few": ("few", "other", "many"), "many": ("many", "other", "few"),
                   "other": ("other", "many", "few")}
