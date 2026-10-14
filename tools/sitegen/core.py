"""Build orchestration: pages × languages → HTML, extras, manifest, stale cleanup, static copy."""

import json
import os
import shutil
import sys
import traceback
from dataclasses import dataclass
from types import SimpleNamespace

from jinja2 import TemplateError

from . import seo
from .i18n import BASE_LANGS, I18n
from .listings import Districts, load as load_listings
from .render import PageState, Renderer, page_root
from .routes import BY_KEY, CATEGORY_ROUTE, NOT_FOUND, PROPERTY, ROUTES, output_file
from .text import truncate

MANIFEST = ".generated-manifest.json"
AGENT_JSONLD_ROUTES = {"home", "about", "contact"}
GLOBAL_JS = ("js/chat.js",)      # подключаются на всех страницах после скриптов страницы
GLOBAL_JS_NS = ("chat",)
LAZY_ASSETS = ("css/forms.css", "js/forms.js")  # → SITE.assets
LEGACY = {  # старые страницы в корне → новый маршрут
    "sale.html": "buy", "rent.html": "rent", "investments.html": "invest", "map.html": "map",
}


@dataclass
class Spec:
    lang: str
    route: object
    listing: object = None
    url_path: str = ""

    @property
    def file(self):
        return output_file(self.url_path)


def load_site(root):
    with open(os.path.join(root, "src", "site.json"), encoding="utf-8") as f:
        return json.load(f)


class _Only(list):
    """--only prefixes; truthy even when only exact paths ("/") were given."""
    def __bool__(self):
        return True


class Builder:
    def __init__(self, root, out=None, langs=None, strict=False, only=None, quiet=False):
        self.root = os.path.abspath(root)
        self.out = os.path.abspath(out or root)
        self.strict = strict
        self.only, self.only_exact = self._parse_only(only)
        self.quiet = quiet
        self.site = load_site(self.root)
        self.site_url = self.site["site_url"].rstrip("/") + "/"
        self.languages = {l["code"]: l for l in self.site["languages"]}
        self.all_langs = [l["code"] for l in self.site["languages"]]
        self.langs = self.all_langs if not langs else [c for c in self.all_langs if c in langs]
        unknown = set(langs or ()) - set(self.all_langs)
        if unknown:
            raise SystemExit(f"unknown language(s): {', '.join(sorted(unknown))}")
        self.report = {"warnings": set(), "missing_assets": set(), "optional_missing": set()}
        self.errors = []
        self.i18n = I18n(self.root, self.all_langs)
        self.errors += self.i18n.errors
        load_warnings = []
        self.districts = Districts(self.root)
        self.listings = load_listings(self.root, self.i18n, self.districts, load_warnings)
        self.report["warnings"].update(load_warnings)
        self.r = Renderer(self.root, self.site, self.i18n, self.listings, self.report)
        self.outputs = {}  # rel path → text

    @staticmethod
    def _parse_only(only):
        """--only: output path prefixes ("buy/", "en/invest/"). "/" or "index.html" select exactly the
        root-language home (url_path ""); "en/" + "index.html" likewise selects only the en home."""
        prefixes, exact = [], set()
        for raw in (only or "").split(","):
            p = raw.strip().lstrip("/")
            if not raw.strip():
                continue
            if p == "" or p == "index.html" or p.endswith("/index.html"):
                exact.add(p[: -len("index.html")] if p.endswith("index.html") else "")
            else:
                prefixes.append(p)
        if not prefixes and not exact:
            return None, set()
        return _Only(prefixes), exact

    def _match_only(self, path):
        return path in self.only_exact or any(path.startswith(p) for p in self.only)

    def log(self, msg):
        if not self.quiet:
            print(msg)

    # ------------------------------------------------------------ planning
    def specs(self):
        out = []
        for lang in self.langs:
            prefix = self.languages[lang]["prefix"]
            for route in ROUTES:
                out.append(Spec(lang, route, None, prefix + route.path))
            for l in self.listings:
                out.append(Spec(lang, PROPERTY, l, prefix + l.path))
        if self.only:
            out = [s for s in out if self._match_only(s.url_path)]
        return out

    def _selected(self, rel):
        return not self.only or self._match_only(rel)

    # ------------------------------------------------------------ page object
    def _abs(self, lang, path):
        return self.site_url + self.languages[lang]["prefix"] + path

    def _og_default(self, route):
        """img/og/<ns>.jpg (1200×630, готовит optimize_images.py) → site default → BG_images/01.jpg."""
        for candidate in (f"img/og/{route.ns}.jpg", self.site["default_og_image"], "BG_images/01.jpg"):
            if self.r.exists(candidate):
                return candidate
        return self.site["default_og_image"]

    def _og_listing_image(self, src):
        """Smallest jpg derivative ≥ 1200 px wide (OG previews), else the original photo."""
        jpgs = sorted((w, p) for p, w in (self.r.derivatives().get(src) or {}).get("jpg") or [] if self.r.exists(p))
        return next((p for w, p in jpgs if w >= 1200), jpgs[-1][1] if jpgs else src)

    def make_page(self, spec, state):
        r, t, lang, route, l = self.r, self.r.t, spec.lang, spec.route, spec.listing
        page = SimpleNamespace(
            key=route.key, ns=route.ns, lang=lang, url_path=spec.url_path,
            section=route.section, category=route.category, sub=route.sub,
            # чат-помощник (js/chat.js + i18n chat) — на каждой странице, последним скриптом;
            # forms.js/forms.css он догружает сам, если страница их не подключила
            body_class=route.body_class, css=list(route.css), js=list(route.js) + list(GLOBAL_JS),
            js_ns=list(dict.fromkeys(("common",) + tuple(route.js_ns) + GLOBAL_JS_NS)),
            noindex=False, og_type="website", og_image=self._og_default(route),
            listing=l, jsonld=[],
        )
        if route is PROPERTY:
            title = self.listings.title(l, lang)
            name = self.listings.name(l, lang)
            per_month = l.section == "rent"
            price = r.fmt_price(l.price, per_month=per_month)
            if not l.price:
                price_phrase = price  # «Цена по запросу»
            elif l.confidential:
                price_phrase = t("common.price.indicative", price=price)
            else:
                price_phrase = t("property.meta.price", price=price)
            fmt = dict(title=title, name=name, price=price, price_phrase=price_phrase, id=l.object_id or l.id,
                       district=self.listings.district_name(l, lang))
            # конфиденциальный инвест-объект: без ID и подробностей в сниппете (brief §A «Конфиденциальность»)
            sfx = "_confidential" if l.confidential else ""
            page.title = t("property.meta.title" + sfx, **fmt)
            page.description = truncate(t("property.meta.description" + sfx, card=self.listings.card_text(l, lang), **fmt), 160)
            page.h1 = title
            page.section, page.category = l.section, l.category
            if l.images:
                page.og_image = self._og_listing_image(l.images[0])
            elif l.confidential and r.exists(l.illustration):
                page.og_image = l.illustration
        elif route is NOT_FOUND:
            page.title = t("common.not_found.meta.title")
            page.description = t("common.not_found.meta.description")
            page.h1 = t("common.not_found.h1")
            page.noindex = True
        else:
            page.title = t(f"{route.meta}.meta.title")
            page.description = t(f"{route.meta}.meta.description")
            page.h1 = t(f"{route.meta}.h1")

        # canonical + hreflang
        if route is NOT_FOUND:
            page.canonical = None
            page.alternates = []
        else:
            path = l.path if l else route.path
            page.canonical = self._abs(lang, path)
            page.alternates = [
                {"hreflang": c, "abs": self._abs(c, path)} for c in self.all_langs
            ] + [{"hreflang": "x-default", "abs": self._abs(self.site["x_default"], path)}]
        page.og_locale = self.languages[lang]["og_locale"]
        page.og_locale_alternates = [self.languages[c]["og_locale"] for c in self.all_langs if c != lang]

        # хлебные крошки: [(label, rel url)] + абсолютные для JSON-LD
        crumbs = []
        if route is not NOT_FOUND:
            chain = []
            if route is PROPERTY:
                chain = ["home", l.section]
                cat_key = CATEGORY_ROUTE.get((l.section, l.category))
                if cat_key:
                    chain.append(cat_key)
            else:
                key = route.key
                while key:
                    chain.insert(0, key)
                    key = BY_KEY[key].parent
            for key in chain:
                label = t("common.routes.home") if key == "home" else t(BY_KEY[key].label_key)
                crumbs.append((label, r.url(key), r.abs_url(key)))
            if route is PROPERTY:
                crumbs.append((page.h1, r.url("property", listing=l), r.abs_url("property", listing=l)))
        page.breadcrumbs = [(label, url) for label, url, _ in crumbs]

        # JSON-LD
        if route.key in AGENT_JSONLD_ROUTES:
            page.jsonld.append(seo.agent_jsonld(self.site, self._abs(lang, ""), r.abs_path(self.site["logo"])))
        if len(crumbs) > 1:
            page.jsonld.append(seo.breadcrumbs_jsonld([(label, a) for label, _, a in crumbs]))
        if route is PROPERTY:
            images = [r.abs_path(p) for p in l.images[:6]]
            page.jsonld.append(seo.listing_jsonld(
                l, self.listings.name(l, lang), self.listings.description(l, lang),
                page.canonical, images, per_month=l.section == "rent"))
        return page

    def context(self, spec, state, page):
        r, lang = self.r, spec.lang
        languages = []
        for code in self.all_langs:
            info = dict(self.languages[code])
            if spec.route is NOT_FOUND:
                info["url"] = r.url("home", lang=code)
                info["abs"] = r.abs_url("home", lang=code)
            else:
                info["url"] = r.lang_url(code)
                info["abs"] = next(a["abs"] for a in page.alternates if a["hreflang"] == code)
            info["current"] = code == lang
            languages.append(info)
        root = self.site_url if state.absolute else page_root(state.file)
        site_js = {
            "lang": lang,
            "dir": self.languages[lang]["dir"],
            "root": root,
            "page": page.key,
            "url": page.canonical,
            "leadEndpoint": self.site.get("lead_endpoint", ""),
            "consentVersion": self.site.get("consent_version", ""),
            "contacts": self.site["contacts"],
            "alternates": {x["code"]: x["url"] for x in languages},
            "langNames": {x["code"]: x["name"] for x in languages},
            # только языки, где фраза реально переведена (без fallback: «доступно на English» по-немецки — нельзя)
            "langSuggest": {c: self.i18n.raw(c, "common.lang_suggest") for c in self.all_langs
                            if isinstance(self.i18n.raw(c, "common.lang_suggest"), dict)},
            "i18n": self.i18n.js_bundle(lang, page.js_ns),
            # версии (?v=hash) файлов, которые скрипты догружают сами (чат → формы)
            "assets": {p: r.asset(p) for p in LAZY_ASSETS if r.exists(p)},
        }
        if spec.listing is not None:
            site_js["listing"] = {"id": spec.listing.id, "objectId": spec.listing.object_id,
                                  "section": spec.listing.section, "slug": spec.listing.slug}
        return {
            "lang": lang, "dir": self.languages[lang]["dir"], "languages": languages,
            "site": self.site, "page": page, "route": spec.route, "listing": spec.listing,
            "site_js": site_js,
        }

    def render_spec(self, spec):
        state = PageState(lang=spec.lang, file=spec.file, route=spec.route, listing=spec.listing,
                          absolute=spec.route is NOT_FOUND, page=None)
        self.r.state = state
        page = self.make_page(spec, state)
        state.page = page
        ctx = self.context(spec, state, page)
        return self.r.render(state, spec.route.template, ctx)

    # ------------------------------------------------------------ extras
    def extras(self):
        out = {}
        if self._selected("404.html"):
            spec = Spec(self.site["default_lang"], NOT_FOUND, None, "404.html")
            self._try_render(spec, out)
        if self.only:
            return out
        out["robots.txt"] = seo.robots_txt(self.site_url)
        entries = []
        for route in ROUTES:
            if route.sitemap:
                entries += self._sitemap_entries(route.path)
        for l in self.listings:
            entries += self._sitemap_entries(l.path)
        out["sitemap.xml"] = seo.sitemap_xml(entries)
        # legacy redirects (корень)
        for name, key in LEGACY.items():
            target = BY_KEY[key].path
            out[name] = seo.redirect_html(target, self.site_url + target, self.site["site_name"],
                                          self.site_url + target)
        id_map = {}
        for l in self.listings:
            for ident in (l.id, l.object_id):
                if ident:
                    id_map.setdefault(ident, l.path)
                    id_map.setdefault(ident.lower(), l.path)
        out["object.html"] = seo.redirect_html(
            "buy/", self.site_url + "buy/", self.site["site_name"], self.site_url + "buy/",
            script=seo.object_redirect_script(id_map, "buy/"))
        return out

    def _sitemap_entries(self, path):
        alternates = [(c, self._abs(c, path)) for c in self.all_langs]
        alternates.append(("x-default", self._abs(self.site["x_default"], path)))
        return [(self._abs(c, path), alternates) for c in self.all_langs]

    def _try_render(self, spec, out):
        try:
            out[spec.file] = self.render_spec(spec)
        except Exception as exc:  # ошибка шаблона/генератора — с местом в шаблоне
            if isinstance(exc, TemplateError) and getattr(exc, "lineno", None):
                where = f"{getattr(exc, 'filename', None) or spec.route.template}:{exc.lineno}"
            else:
                tb = traceback.extract_tb(exc.__traceback__)
                where = next((f"{os.path.relpath(f.filename, self.root)}:{f.lineno}" for f in reversed(tb)
                              if f.filename.endswith(".html")), f"{tb[-1].filename}:{tb[-1].lineno}")
            self.errors.append(f"{spec.file}: {type(exc).__name__} at {where}: {exc}")

    # ------------------------------------------------------------ run
    def render_all(self):
        specs = self.specs()
        for spec in specs:
            self._try_render(spec, self.outputs)
        self.outputs.update(self.extras())
        return specs

    def i18n_problems(self):
        """Errors that fail --strict: ru/en misses + keys of ru absent in en."""
        problems = []
        for lang in BASE_LANGS:
            for key in sorted(self.i18n.missing.get(lang, ())):
                problems.append(f"i18n: missing key in {lang}: {key}")
        diff = self.i18n.static_diff("ru").get("en", {})
        for key in diff.get("missing", []):
            problems.append(f"i18n: key present in ru but missing in en: {key}")
        return problems

    def print_report(self, check=False):
        missing = self.i18n.missing
        self.log("i18n keys used but missing (falls back lang → en → ru):")
        for lang in self.all_langs:
            keys = sorted(missing.get(lang, ()))
            shown = keys if (check or lang in BASE_LANGS) else keys[:5]
            more = f" … (+{len(keys) - len(shown)}, see --check)" if len(keys) > len(shown) else ""
            self.log(f"  {lang}: {len(keys)}" + (": " + ", ".join(shown) + more if keys else ""))
        if check:
            self.log("i18n static diff vs ru (keys missing / extra per language):")
            for lang, d in self.i18n.static_diff("ru").items():
                self.log(f"  {lang}: missing {len(d['missing'])}, extra {len(d['extra'])}")
                for key in d["missing"]:
                    self.log(f"    - {key}")
                for key in d["extra"]:
                    self.log(f"    + {key}")
        if self.report["optional_missing"]:
            self.log("optional page assets not present yet (skipped): "
                     + ", ".join(sorted(self.report["optional_missing"])))
        for w in sorted(self.report["warnings"]):
            self.log(f"[warn] {w}")
        for a in sorted(self.report["missing_assets"]):
            self.log(f"[warn] asset() target missing: {a}")

    def write(self):
        os.makedirs(self.out, exist_ok=True)
        written = 0
        for rel, text in sorted(self.outputs.items()):
            dest = os.path.join(self.out, *rel.split("/"))
            data = text.replace("\r\n", "\n").encode("utf-8")
            if os.path.isfile(dest):
                with open(dest, "rb") as f:
                    if f.read() == data:
                        continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
            written += 1
        return written

    def manifest(self):
        path = os.path.join(self.out, MANIFEST)
        previous = []
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    previous = json.load(f).get("files", [])
            except ValueError:
                previous = []
        current = set(self.outputs)
        partial = bool(self.only) or self.langs != self.all_langs
        removed = []
        if partial:
            current |= set(previous)
        else:
            for rel in sorted(set(previous) - current):
                dest = os.path.normpath(os.path.join(self.out, *rel.split("/")))
                if not dest.startswith(self.out + os.sep) or not os.path.isfile(dest):
                    continue
                os.remove(dest)
                removed.append(rel)
                folder = os.path.dirname(dest)
                while folder.startswith(self.out + os.sep) and not os.listdir(folder):
                    os.rmdir(folder)
                    folder = os.path.dirname(folder)
        data = json.dumps({"generator": "tools/build_site.py", "files": sorted(current)},
                          ensure_ascii=False, indent=1) + "\n"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
        return removed

    def copy_static(self):
        """Out-of-tree builds get a copy of the static dirs so the folder is servable."""
        if os.path.normcase(self.out) == os.path.normcase(self.root):
            return 0
        copied = 0
        for d in self.site.get("static_dirs", []):
            src_dir = os.path.join(self.root, d)
            for base, _, files in os.walk(src_dir):
                rel = os.path.relpath(base, self.root)
                for name in files:
                    src = os.path.join(base, name)
                    dst = os.path.join(self.out, rel, name)
                    st = os.stat(src)
                    if os.path.isfile(dst):
                        dt = os.stat(dst)
                        if dt.st_size == st.st_size and int(dt.st_mtime) == int(st.st_mtime):
                            continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    copied += 1
        return copied


def build(root, out=None, langs=None, strict=False, only=None, check=False, quiet=False):
    """Returns process exit code."""
    b = Builder(root, out, langs, strict, only, quiet)
    specs = b.render_all()
    b.print_report(check=check)
    strict_problems = b.i18n_problems() if strict else []
    if strict:
        strict_problems += [f"asset missing: {a}" for a in sorted(b.report["missing_assets"])]
        if not b.r.exists("js/site.js"):  # base.html подключает его только если файл есть
            strict_problems.append("asset missing: js/site.js")
    for e in b.errors:
        print(f"[x] {e}", file=sys.stderr)
    for p in strict_problems:
        print(f"[x] {p}", file=sys.stderr)
    failed = bool(b.errors or strict_problems)
    if check:
        b.log(f"check: {len(specs)} pages rendered, {len(b.errors)} errors, "
              f"{len(strict_problems)} strict problems — nothing written")
        return 1 if failed else 0
    if failed:
        print("[x] build failed — nothing written", file=sys.stderr)
        return 1
    written = b.write()
    removed = b.manifest()
    copied = b.copy_static()
    b.log(f"[ok] {len(b.outputs)} files generated ({written} changed, {len(removed)} stale removed"
          + (f", {copied} static files copied" if copied else "") + f") → {b.out}")
    for rel in removed:
        b.log(f"  removed stale: {rel}")
    return 0
