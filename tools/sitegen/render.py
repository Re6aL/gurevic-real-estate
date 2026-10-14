"""Jinja2 environment and template globals (ARCHITECTURE §4).

Globals read the *current page state* (set before each render), so they also work inside
macros imported without context: t, url, asset, img, fmt_price… The page-level variables
lang, dir, languages, site, page, route, listing are passed as render context.
"""

import hashlib
import json
import os
import posixpath
import urllib.parse
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape

from . import fmt as fmtmod
from .i18n import MISSING, safe_format
from .routes import BY_KEY, relative, route_path

try:  # Pillow нужен только для width/height у картинок без деривативов
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


TEXT_ASSETS = (".css", ".js", ".json", ".svg", ".txt", ".html", ".xml")


def _quote(path):
    return urllib.parse.quote(path, safe="/-_.~")


class PageState(SimpleNamespace):
    """lang, file (output path, posix), route, listing, absolute (bool), page."""


class Renderer:
    def __init__(self, root, site, i18n, listings, report):
        self.root = root
        self.site = site
        self.i18n = i18n
        self.listings = listings
        self.report = report  # dict: warnings (set), missing_assets (set)
        self.languages = {l["code"]: l for l in site["languages"]}
        self.site_url = site["site_url"].rstrip("/") + "/"
        self.state = None
        self._hash = {}
        self._dims = {}
        self._derivatives = None

        self.env = Environment(
            loader=FileSystemLoader(os.path.join(root, "src", "templates")),
            autoescape=True, trim_blocks=True, lstrip_blocks=True,
            undefined=StrictUndefined, keep_trailing_newline=True,
        )
        self.env.policies["json.dumps_kwargs"] = {"sort_keys": False, "ensure_ascii": False}
        g = self.env.globals
        g.update(
            t=self.t, tl=self.tl, t_has=self.t_has, t_source=self.t_source, plural=self.plural,
            url=self.url, abs_url=self.abs_url, lang_url=self.lang_url,
            path=self.path, abs_path=self.abs_path, asset=self.asset, asset_exists=self.exists,
            css_files=self.css_files, js_files=self.js_files,
            img=self.img, img_exists=self.exists, image_size=self.image_size,
            fmt_price=self.fmt_price, fmt_num=self.fmt_num,
            listings=listings,
            listing_title=self._lfun("title"), listing_name=self._lfun("name"),
            listing_card=self._lfun("card_text"), listing_description=self._lfun("description"),
            listing_location=self._lfun("location_text"), listing_params=self._lfun("params"),
            district_name=lambda key: self.t(f"common.districts.{key}"),
            type_name=lambda kind: self.t(f"common.types.{kind}"),
        )
        self.env.filters["bdi"] = lambda s: Markup("<bdi>%s</bdi>") % s
        self.env.filters["num"] = self.fmt_num

    # ------------------------------------------------------------ i18n
    def _value(self, lang, key, fmt):
        value = self.i18n.lookup(lang, key)
        if value is MISSING:
            return key
        if isinstance(value, str):
            if key.endswith("_html"):
                # доверенный HTML из наших словарей; подставляемые значения экранируются
                return Markup(value).format(**fmt) if fmt else Markup(value)
            return safe_format(value, fmt) if fmt else value
        return value

    def t(self, key, **fmt):
        return self._value(self.state.lang, key, fmt)

    def tl(self, lang, key, **fmt):
        """Translate into another language (404 page, language switcher)."""
        return self._value(lang, key, fmt)

    def t_has(self, key):
        return self.i18n.has(self.state.lang, key)

    def t_source(self, lang, key):
        """Language the value of `key` actually comes from (lang → en → ru), or None."""
        return next((c for c in self.i18n.chain(lang) if self.i18n.raw(c, key) is not MISSING), None)

    def plural(self, key, n, **fmt):
        return self.i18n.plural(self.state.lang, key, n, **fmt)

    # ------------------------------------------------------------ URLs
    def _target(self, route_key, lang, listing):
        lang = lang or self.state.lang
        if route_key not in BY_KEY:
            raise KeyError(f"url(): unknown route {route_key!r}")
        return self.languages[lang]["prefix"] + route_path(route_key, listing)

    def url(self, route_key, lang=None, listing=None):
        target = self._target(route_key, lang, listing)
        if self.state.absolute:
            return self.site_url + target
        return relative(self.state.file, target)

    def abs_url(self, route_key, lang=None, listing=None):
        return self.site_url + self._target(route_key, lang, listing)

    def lang_url(self, code):
        """The current page in another language (relative)."""
        st = self.state
        if st.route.key in BY_KEY:
            return self.url(st.route.key, lang=code, listing=st.listing)
        return self.url("home", lang=code)

    def path(self, p):
        """Relative path to a root file, no cache-busting (fonts preload, data files)."""
        p = p.lstrip("/")
        if self.state.absolute:
            return self.site_url + _quote(p)
        return _quote(relative(self.state.file, p))

    def abs_path(self, p):
        return self.site_url + _quote(p.lstrip("/"))

    def exists(self, p):
        return bool(p) and os.path.isfile(os.path.join(self.root, p.split("?")[0]))

    def _content_hash(self, p):
        if p not in self._hash:
            with open(os.path.join(self.root, p), "rb") as f:
                data = f.read()
            # git с core.autocrlf=true отдаёт на Windows CRLF, а в CI — LF: хэш текстовых
            # ассетов считаем по LF, иначе каждая сборка в CI «меняла» бы все страницы
            if p.endswith(TEXT_ASSETS):
                data = data.replace(b"\r\n", b"\n")
            self._hash[p] = hashlib.md5(data).hexdigest()[:8]
        return self._hash[p]

    def asset(self, p):
        """Relative path + ?v=<8-char content hash>."""
        p = p.lstrip("/")
        if not self.exists(p):
            self.report["missing_assets"].add(p)
            return self.path(p)
        return f"{self.path(p)}?v={self._content_hash(p)}"

    def _existing(self, files, kind):
        out = []
        for f in files:
            if f in out:
                continue
            if self.exists(f):
                out.append(f)
            else:
                self.report["optional_missing"].add(f)
        return out

    def css_files(self, extra=()):
        return self._existing(list(self.state.page.css) + list(extra or ()), "css")

    def js_files(self, extra=()):
        return self._existing(list(self.state.page.js) + list(extra or ()), "js")

    # ------------------------------------------------------------ images
    def derivatives(self):
        if self._derivatives is None:
            path = os.path.join(self.root, "img", "derivatives.json")
            self._derivatives = {}
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        self._derivatives = json.load(f)
                except ValueError as exc:
                    self.report["warnings"].add(f"img/derivatives.json unreadable: {exc}")
        return self._derivatives

    def dims(self, p):
        if p not in self._dims:
            self._dims[p] = None
            if Image is not None:
                try:
                    with Image.open(os.path.join(self.root, p)) as im:
                        w, h = im.size
                        # EXIF Orientation 5–8 = повёрнуто на 90°: браузер покажет w/h наоборот
                        if im.getexif().get(0x0112, 1) in (5, 6, 7, 8):
                            w, h = h, w
                        self._dims[p] = (w, h)
                except Exception:  # битый файл — просто без размеров
                    pass
        return self._dims[p]

    def image_size(self, p):
        """(width, height) of a root image (derivatives.json or Pillow), None if unknown."""
        p = (p or "").lstrip("/")
        entry = self.derivatives().get(p)
        if entry and entry.get("width"):
            return entry["width"], entry["height"]
        return self.dims(p) if self.exists(p) else None

    def img(self, src, alt, sizes="100vw", cls="", loading="lazy", width=None, height=None,
            fetchpriority=None, fallback=None, pic_cls="", decoding="async"):
        """<picture> with webp/jpg srcset from img/derivatives.json, or plain <img>.

        Missing `src` → `fallback` (if given and present) → empty output + warning.
        """
        src = (src or "").lstrip("/")
        if not self.exists(src):
            if fallback and self.exists(fallback.lstrip("/")):
                src = fallback.lstrip("/")
            else:
                self.report["warnings"].add(f"img(): file not found: {src}")
                return Markup("")
        entry = self.derivatives().get(src)
        size = (entry["width"], entry["height"]) if entry and entry.get("width") else self.dims(src)
        if width is None and height is None and size:
            width, height = size
        attrs = []
        if cls:
            attrs.append(f' class="{escape(cls)}"')
        attrs.append(f' alt="{escape(alt or "")}"')
        if width:
            attrs.append(f' width="{int(width)}"')
        if height:
            attrs.append(f' height="{int(height)}"')
        if loading and fetchpriority != "high":
            attrs.append(f' loading="{escape(loading)}"')
        if decoding:
            attrs.append(f' decoding="{escape(decoding)}"')
        if fetchpriority:
            attrs.append(f' fetchpriority="{escape(fetchpriority)}"')

        def srcset(items):
            return ", ".join(f"{self.path(p)} {int(w)}w" for p, w in items if self.exists(p))

        if entry and (entry.get("webp") or entry.get("jpg")):
            jpg = [x for x in entry.get("jpg") or [] if self.exists(x[0])]
            webp = srcset(entry.get("webp") or [])
            fallback_src = self.path(jpg[-1][0]) if jpg else self.path(src)
            # самый большой jpg ≤ 1280 — разумный src для браузеров без srcset
            for p, w in jpg:
                if w <= 1280:
                    fallback_src = self.path(p)
            parts = [f'<picture class="{escape(pic_cls)}">' if pic_cls else "<picture>"]
            if webp:
                parts.append(f'<source type="image/webp" srcset="{webp}" sizes="{escape(sizes)}">')
            jpg_set = srcset(jpg)
            extra = f' srcset="{jpg_set}" sizes="{escape(sizes)}"' if jpg_set else ""
            parts.append(f'<img src="{fallback_src}"{extra}{"".join(attrs)}>')
            parts.append("</picture>")
            return Markup("".join(parts))
        return Markup(f'<img src="{self.path(src)}"{"".join(attrs)}>')

    # ------------------------------------------------------------ numbers
    def fmt_num(self, value):
        return fmtmod.fmt_num(value, self.state.lang)

    def fmt_price(self, value, per_month=False):
        if not value:
            return self.t("common.price.on_request")
        text = fmtmod.fmt_price(value, self.state.lang)
        return f"{text}{fmtmod.NBSP}{self.t('common.units.per_month')}" if per_month else text

    def _lfun(self, name):
        return lambda l: getattr(self.listings, name)(l, self.state.lang)

    # ------------------------------------------------------------ render
    def render(self, state, template, context):
        self.state = state
        return self.env.get_template(template).render(**context)

    def render_string(self, state, source, context):
        self.state = state
        return self.env.from_string(source).render(**context)


def page_root(file):
    """Relative path from a page file to the site root ('./', '../', …)."""
    depth = posixpath.dirname(file).count("/") + 1 if posixpath.dirname(file) else 0
    return "../" * depth or "./"
