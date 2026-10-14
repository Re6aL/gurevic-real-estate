"""Route table (ARCHITECTURE §3) and URL helpers.

Paths are relative to the language root ("" = home, folders end with "/").
`meta` is the i18n prefix of the page's SEO strings: "<ns>" or "<ns>.categories.<sub>"
(keys `<meta>.meta.title`, `<meta>.meta.description`, `<meta>.h1`).
Page CSS/JS listed here are optional: files that do not exist yet are skipped.
"""

import posixpath
from dataclasses import dataclass, field

# Общие наборы ассетов по семействам страниц
_FORMS_CSS = ("css/forms.css",)
_FORMS_JS = ("js/forms.js",)


@dataclass(frozen=True)
class Route:
    key: str
    path: str
    template: str
    ns: str
    sub: str = None          # подкатегория для meta-префикса (<ns>.categories.<sub>)
    section: str = None      # buy | rent | invest
    category: str = None     # apartments | houses | ... (как в listings)
    parent: str = None       # ключ родителя для хлебных крошек
    css: tuple = ()
    js: tuple = ()
    js_ns: tuple = ("common",)
    body_class: str = ""
    sitemap: bool = True
    extra: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def meta(self):
        return f"{self.ns}.categories.{self.sub}" if self.sub else self.ns

    @property
    def label_key(self):
        """i18n key of the short route label (menus, breadcrumbs)."""
        return "common.routes." + self.key.replace(".", "_")


def _catalog(key, path, section, category=None, parent=None):
    ns = section
    return Route(
        key, path, "pages/catalog.html", ns, sub=category, section=section, category=category,
        parent=parent or "home",
        css=("css/catalog.css",) + _FORMS_CSS, js=("js/catalog.js",) + _FORMS_JS,
        js_ns=("common", "catalog", "forms"), body_class=f"page-catalog page-{section}",
    )


def _invest_cat(key, path, category):
    return Route(
        key, path, "pages/invest_category.html", "invest", sub=category, section="invest",
        category=category, parent="invest",
        css=("css/invest.css",) + _FORMS_CSS, js=_FORMS_JS + ("js/invest.js",),
        js_ns=("common", "forms", "invest"), body_class="page-invest page-invest-category",
    )


def _owners_sub(key, path, sub):
    return Route(
        key, path, "pages/owners_service.html", "owners", sub=sub, parent="owners",
        css=("css/owners.css",) + _FORMS_CSS, js=_FORMS_JS + ("js/owners.js",),
        js_ns=("common", "forms", "owners"), body_class="page-owners page-owners-service",
        extra={"service": sub},
    )


def _info(key, path, template, ns, forms=False):
    return Route(
        key, path, template, ns, parent="home",
        css=("css/info.css",) + (_FORMS_CSS if forms else ()), js=_FORMS_JS if forms else (),
        js_ns=("common", "forms") if forms else ("common",), body_class=f"page-info page-{ns}",
    )


ROUTES = [
    # без forms.css/js: на главной нет форм, чат догружает их сам (SITE.assets)
    Route("home", "", "pages/home.html", "home",
          css=("css/home.css",), js=("js/home.js",),
          js_ns=("common", "home"), body_class="page-home"),
    _catalog("buy", "buy/", "buy"),
    _catalog("buy.apartments", "buy/apartments/", "buy", "apartments", "buy"),
    _catalog("buy.houses", "buy/houses/", "buy", "houses", "buy"),
    _catalog("buy.villas", "buy/villas/", "buy", "villas", "buy"),
    _catalog("buy.land", "buy/land/", "buy", "land", "buy"),
    _catalog("rent", "rent/", "rent"),
    _catalog("rent.apartments", "rent/apartments/", "rent", "apartments", "rent"),
    _catalog("rent.houses", "rent/houses/", "rent", "houses", "rent"),
    Route("invest", "invest/", "pages/invest.html", "invest", section="invest", parent="home",
          css=("css/invest.css",) + _FORMS_CSS, js=_FORMS_JS + ("js/invest.js",),
          js_ns=("common", "forms", "invest"), body_class="page-invest"),
    _invest_cat("invest.hotels", "invest/hotels/", "hotels"),
    _invest_cat("invest.land", "invest/land/", "land"),
    _invest_cat("invest.commercial", "invest/commercial/", "commercial"),
    _invest_cat("invest.development", "invest/development-projects/", "development"),
    Route("owners", "owners/", "pages/owners.html", "owners", parent="home",
          css=("css/owners.css",) + _FORMS_CSS, js=_FORMS_JS + ("js/owners.js",),
          js_ns=("common", "forms", "owners"), body_class="page-owners"),
    _owners_sub("owners.sell", "owners/sell/", "sell"),
    _owners_sub("owners.rent_out", "owners/rent-out/", "rent_out"),
    _owners_sub("owners.management", "owners/property-management/", "management"),
    _info("about", "about/", "pages/about.html", "about"),
    _info("services", "services/", "pages/services.html", "services", forms=True),
    _info("contact", "contact/", "pages/contact.html", "contact", forms=True),
    _info("privacy", "privacy/", "pages/privacy.html", "privacy"),
    Route("map", "map/", "pages/map.html", "map", parent="home",
          css=("css/map.css",), js=("js/map.js",), js_ns=("common", "map"), body_class="page-map"),
]

# Динамический маршрут страницы объекта: путь {section}/{slug}/
PROPERTY = Route("property", "{section}/{slug}/", "pages/property.html", "property",
                 css=("css/property.css",) + _FORMS_CSS, js=("js/property.js",) + _FORMS_JS,
                 js_ns=("common", "property", "forms"), body_class="page-property")

# 404 (корень, язык-нейтральная) — не маршрут, но рендерится тем же движком
NOT_FOUND = Route("404", "404.html", "pages/404.html", "common", sitemap=False, body_class="page-404")

BY_KEY = {r.key: r for r in ROUTES}
BY_KEY[PROPERTY.key] = PROPERTY

# (section, category) → ключ маршрута категории
CATEGORY_ROUTE = {(r.section, r.category): r.key for r in ROUTES if r.section and r.category}


def listing_path(listing):
    return f"{listing.section}/{listing.slug}/"


def route_path(route_key, listing=None):
    """Path relative to the language root."""
    if route_key == "property":
        if listing is None:
            raise ValueError("url('property') needs listing=")
        return listing_path(listing)
    try:
        return BY_KEY[route_key].path
    except KeyError:
        raise KeyError(f"unknown route key {route_key!r}") from None


def lang_prefix(lang, languages):
    return languages[lang]["prefix"]


def output_file(url_path):
    """'en/buy/' → 'en/buy/index.html'; '' → 'index.html'; 'x.html' stays."""
    if url_path == "" or url_path.endswith("/"):
        return url_path + "index.html"
    return url_path


def relative(from_file, target):
    """Relative URL from the page file `from_file` to root-relative `target`.

    Folder targets keep a trailing slash ("./", "../", "../buy/").
    """
    from_dir = posixpath.dirname(from_file) or "."
    is_dir = target == "" or target.endswith("/")
    clean = target.rstrip("/") or "."
    rel = posixpath.relpath(clean, from_dir)
    if is_dir:
        return "./" if rel == "." else rel + "/"
    return rel
