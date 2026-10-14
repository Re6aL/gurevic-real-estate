"""i18n dictionaries: i18n/<lang>/<namespace>.json.

Lookup key: "ns.path.to.key". Fallback chain: lang → en → ru (ARCHITECTURE §2).
Every miss along the chain is recorded per language for the --check / --strict report.
"""

import json
import os
from collections import defaultdict

MISSING = object()
FALLBACK = ("en", "ru")
BASE_LANGS = ("ru", "en")  # --strict: ключ обязан быть в ru и en


PLURAL_FORMS = {"zero", "one", "two", "few", "many", "other"}


def _flatten(obj, prefix=""):
    """Dotted leaf keys of a nested dict (lists and plural dicts {one, few, …} are leaves:
    the set of plural forms legitimately differs between languages)."""
    if isinstance(obj, dict) and obj and set(obj) <= PLURAL_FORMS:
        yield prefix
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{prefix}.{k}" if prefix else k)
    else:
        yield prefix


class _Keep(dict):
    """format_map helper: unknown placeholders stay as-is instead of raising KeyError."""

    def __missing__(self, key):
        return "{" + key + "}"


def safe_format(text, values):
    try:
        return text.format_map(_Keep(values))
    except (ValueError, IndexError, AttributeError):
        return text


def _deep_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class I18n:
    def __init__(self, root, langs):
        self.root = root
        self.langs = list(langs)
        self.data = {}  # lang -> ns -> dict
        self.errors = []  # битые JSON-файлы
        for lang in self.langs:
            self.data[lang] = {}
            folder = os.path.join(root, "i18n", lang)
            if not os.path.isdir(folder):
                continue
            for name in sorted(os.listdir(folder)):
                if not name.endswith(".json"):
                    continue
                path = os.path.join(folder, name)
                try:
                    with open(path, encoding="utf-8") as f:
                        self.data[lang][name[:-5]] = json.load(f)
                except (OSError, ValueError) as exc:
                    self.errors.append(f"i18n/{lang}/{name}: {exc}")
        self.missing = defaultdict(set)  # lang -> {key}

    # ---------- lookup ----------
    def raw(self, lang, key):
        ns, _, path = key.partition(".")
        node = self.data.get(lang, {}).get(ns, MISSING)
        if node is MISSING:
            return MISSING
        if not path:
            return node
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return MISSING
        return node

    def chain(self, lang):
        seen = []
        for code in (lang, *FALLBACK):
            if code not in seen:
                seen.append(code)
        return seen

    def lookup(self, lang, key, record=True):
        """Value for `key` in `lang` with fallback; MISSING when absent everywhere."""
        for code in self.chain(lang):
            value = self.raw(code, key)
            if value is not MISSING:
                return value
            if record:
                self.missing[code].add(key)
        return MISSING

    def has(self, lang, key):
        return self.lookup(lang, key, record=False) is not MISSING

    def t(self, lang, key, **fmt):
        """Plain translated value (str.format applied to strings); the key itself when missing."""
        value = self.lookup(lang, key)
        if value is MISSING:
            return key
        if isinstance(value, str) and fmt:
            value = safe_format(value, fmt)
        return value

    def plural(self, lang, key, n, **fmt):
        """`key` is a dict {one, few, many, other…}; the form is chosen by `n` in the
        language where the dictionary was found. Placeholder {n} = formatted number."""
        from .fmt import PLURAL_FALLBACK, fmt_num, plural_category
        for code in self.chain(lang):
            node = self.raw(code, key)
            if isinstance(node, dict):
                for cat in PLURAL_FALLBACK[plural_category(n, code)]:
                    if isinstance(node.get(cat), str):
                        return safe_format(node[cat], {"n": fmt_num(n, lang), **fmt})
            self.missing[code].add(key)
        return f"{n}"

    # ---------- JS bundle ----------
    def js_bundle(self, lang, namespaces):
        """{ns: merged `js` sub-object} for SITE.i18n (ru ← en ← lang, so JS never lacks a key)."""
        out = {}
        for ns in namespaces:
            merged = {}
            for code in reversed(self.chain(lang)):
                part = self.data.get(code, {}).get(ns, {})
                if isinstance(part, dict) and isinstance(part.get("js"), dict):
                    merged = _deep_merge(merged, part["js"])
            out[ns] = merged
        return out

    # ---------- reports ----------
    def static_diff(self, reference="ru"):
        """{lang: {"missing": [...], "extra": [...]}} — keys compared with the reference language."""
        ref = {f"{ns}.{k}" for ns, d in self.data.get(reference, {}).items() for k in _flatten(d)}
        report = {}
        for lang in self.langs:
            if lang == reference:
                continue
            have = {f"{ns}.{k}" for ns, d in self.data.get(lang, {}).items() for k in _flatten(d)}
            report[lang] = {"missing": sorted(ref - have), "extra": sorted(have - ref)}
        return report
