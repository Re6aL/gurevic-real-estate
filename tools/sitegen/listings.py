"""Listings data layer (ARCHITECTURE §6, brief §F/§G).

Sources: js/data.js (`const LISTINGS = [...]`, sales CRM) and optional js/rentals.js
(`const RENTALS = [...]`, rentals CRM). Works both with the current data.js (no new keys —
kind/section/district/crmTitle are derived) and with the new keys written by notion_sync.py.

API:
    load(root, i18n, districts) -> Listings
    Listings.query(section=None, category=None, kind=None) -> [Listing]
    Listings.by_slug(section, slug) / by_id(id)
    Listings.title / name / card_text / description / location_text / params (l, lang)
"""

import json
import os
import re

from .fmt import fmt_num, fmt_price
from .text import normalize, slugify

KINDS = ("apartment", "house", "villa", "land", "hotel", "commercial", "business", "development")
# Property Type из CRM (и старое поле type в data.js) → kind
TYPE_ALIASES = {
    "apartment": "apartment", "house": "house", "villa": "villa", "land": "land",
    "hotel": "hotel", "commercial": "commercial", "office": "commercial", "retail": "commercial",
    "industrial": "commercial", "warehouse": "commercial", "business": "business",
    "gradnja": "development", "development": "development",
}
BUY_KINDS = {"apartment", "house", "villa", "land"}
CATEGORY = {
    "buy": {"apartment": "apartments", "house": "houses", "villa": "villas", "land": "land"},
    "invest": {"hotel": "hotels", "land": "land", "commercial": "commercial",
               "business": "commercial", "development": "development"},
    "rent": {"apartment": "apartments", "house": "houses", "villa": "houses"},
}
CONFIDENTIAL_KINDS = {"hotel", "commercial", "business", "land"}  # только в разделе invest

PLACEHOLDER = {
    "apartment": "img/placeholders/apartment.png", "house": "img/placeholders/house.png",
    "villa": "img/placeholders/house.png", "land": "img/placeholders/land.png",
}
PLACEHOLDER_DEFAULT = "img/placeholders/complex.png"
# Иллюстрации для конфиденциальных инвест-объектов (brief §H); если файла нет — плейсхолдер
CONFIDENTIAL_ILLUSTRATION = {
    "hotel": "img/stock/invest-hotel.jpg", "commercial": "img/stock/invest-restaurant.jpg",
    "business": "img/stock/invest-restaurant.jpg", "land": "img/stock/invest-land.jpg",
    "development": "img/stock/invest-development.jpg",
}

# Автозаголовки старой синхронизации: «Квартира — Будва — центр», «Квартира 26 м² — …»
_AUTO_TITLE_RE = re.compile(
    r"^(?:Квартира|Дом|Вилла|Участок|Коммерческое помещение|Отель|Объект)(?: [\d.,]+ м²)? — .+$"
)
_VILLA_RE = re.compile(r"(?<![a-zа-я])(?:vila|villa|вилла)(?![a-zа-я])")
_INT_RE = re.compile(r"\d+")

_CAMEL_PASSTHROUGH = {
    "bathrooms": "bathrooms", "floor": "floor", "balconies": "balconies", "view": "view",
    "furnishing": "furnishing", "condition": "condition", "parking": "parking",
    "distanceToSea": "distance_to_sea", "completionDate": "completion_date",
    "paymentPlan": "payment_plan", "transferTax": "transfer_tax",
    "projectName": "project_name", "projectId": "project_id",
}


class Listing:
    """Normalized listing; attributes as in ARCHITECTURE §6 (+ a few helpers)."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __repr__(self):
        return f"<Listing {self.section}/{self.slug}>"

    @property
    def price_on_request(self):
        return not self.price

    @property
    def path(self):
        return f"{self.section}/{self.slug}/"


def _load_derivatives(root):
    path = os.path.join(root, "img", "derivatives.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except ValueError:
        return {}


def _thumb(root, derivatives, src, min_width=400):
    """Small preview (map mini cards): the smallest webp/jpg derivative ≥ min_width, else the source."""
    entry = derivatives.get(src) or {}
    for fmt in ("webp", "jpg"):
        items = sorted((int(w), p) for p, w in entry.get(fmt) or [] if os.path.isfile(os.path.join(root, p)))
        if items:
            return next((p for w, p in items if w >= min_width), items[-1][1])
    return src


def read_js_array(path):
    """JSON array between the first '[' and the last ']' of a JS file ([] when absent)."""
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return []
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------- districts
class Districts:
    def __init__(self, root):
        with open(os.path.join(root, "src", "districts.json"), encoding="utf-8") as f:
            self.items = json.load(f)["districts"]
        self.by_key = {d["key"]: d for d in self.items}
        self._alias = {}
        for d in self.items:
            for alias in [d["ru"], d["latin"], d["key"], *d.get("aliases", [])]:
                self._alias[normalize(alias).strip()] = d["key"]
        specific = [d for d in self.items if d["key"] not in ("budva-center", "other")]
        self._specific = [(d["key"], [self._compile(k) for k in d.get("keywords", [])]) for d in specific]
        self._budva = [self._compile(k) for k in self.by_key["budva-center"].get("keywords", [])]

    @staticmethod
    def _compile(keyword):
        if keyword.startswith("re:"):
            return re.compile(keyword[3:])
        return re.compile(re.escape(normalize(keyword)))

    def from_label(self, label):
        return self._alias.get(normalize(label or "").strip())

    def from_text(self, text, specific_only=True):
        s = normalize(text or "")
        for key, patterns in self._specific:
            if any(p.search(s) for p in patterns):
                return key
        if not specific_only and any(p.search(s) for p in self._budva):
            return "budva-center"
        return None

    def detect(self, raw):
        """districtKey → label (if specific) → keywords in title → label → 'budva' → other."""
        key = raw.get("districtKey") or raw.get("district")
        if key in self.by_key:
            return key
        by_label = self.from_label(raw.get("location"))
        if by_label and by_label not in ("budva-center", "other"):
            return by_label
        text = " ".join(str(raw.get(k) or "") for k in ("crmTitle", "title", "projectName"))
        found = self.from_text(text)
        if found:
            return found
        if by_label:
            return by_label
        return self.from_text(text, specific_only=False) or "other"

    def coords(self, key):
        return self.by_key.get(key, self.by_key["other"])["coords"]

    def region(self, key):
        return self.by_key.get(key, self.by_key["other"])["region"]


# ---------------------------------------------------------------- normalization
def _num(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    m = re.search(r"\d+(?:[.,]\d+)?", str(value))
    if not m:
        return None
    v = float(m.group(0).replace(",", "."))
    return int(v) if v.is_integer() else v


def _derive_kind(raw):
    kind = str(raw.get("kind") or "").lower()
    if kind in KINDS:
        return kind
    invest_kind = str(raw.get("investKind") or "").lower()
    if invest_kind.startswith("девелоп") or invest_kind.startswith("develop") or (raw.get("invest") and raw.get("isComplex")):
        return "development"
    if invest_kind.startswith("отель") or invest_kind.startswith("hotel"):
        return "hotel"
    t = TYPE_ALIASES.get(str(raw.get("type") or "").lower(), "apartment")
    if t == "house" and _VILLA_RE.search(normalize(str(raw.get("crmTitle") or raw.get("title") or ""))):
        return "villa"
    return t


def _derive_section(raw, kind, source):
    section = str(raw.get("section") or "").lower()
    if section in ("buy", "rent", "invest"):
        return section
    if source == "rentals" or str(raw.get("deal") or "").lower() == "rent":
        return "rent"
    return "buy" if kind in BUY_KINDS else "invest"


def _crm_title(raw):
    if "crmTitle" in raw:
        return (raw.get("crmTitle") or "").strip() or None
    title = (raw.get("title") or "").strip()
    if not title or _AUTO_TITLE_RE.match(title):
        return None
    return title


def _texts(raw):
    texts = {"card": {}, "description": {}, "location": {}}
    given = raw.get("texts") or {}
    for part in texts:
        for lang, value in (given.get(part) or {}).items():
            if isinstance(value, str) and value.strip():
                texts[part][lang] = value.strip()
    # Старые поля CRM (только русский текст «Website Description» и т.п.)
    legacy = {"card": "cardDescription", "description": "propertyDescription", "location": "locationDescription"}
    for part, field in legacy.items():
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            texts[part].setdefault("ru", value.strip())
    return texts


def _normalize(raw, source, districts, root, warnings, derivatives=None):
    kind = _derive_kind(raw)
    section = _derive_section(raw, kind, source)
    category = CATEGORY.get(section, {}).get(kind)
    disclosure = str(raw.get("disclosure") or "").lower()
    if disclosure not in ("public", "confidential"):
        disclosure = "confidential" if section == "invest" and kind in CONFIDENTIAL_KINDS else "public"
    confidential = disclosure == "confidential"
    district = districts.detect(raw)

    images = []
    for path in raw.get("images") or []:
        if isinstance(path, str) and os.path.isfile(os.path.join(root, path)):
            images.append(path)
        else:
            warnings.append(f"listing {raw.get('id')}: image not found: {path}")
    if confidential:
        images = []
    illustration = PLACEHOLDER.get(kind, PLACEHOLDER_DEFAULT)
    if confidential:
        stock = CONFIDENTIAL_ILLUSTRATION.get(kind)
        if stock and os.path.isfile(os.path.join(root, stock)):
            illustration = stock

    coords = raw.get("coords")
    if not (isinstance(coords, (list, tuple)) and len(coords) == 2 and all(isinstance(c, (int, float)) for c in coords)):
        coords = None
    if confidential:
        coords = None

    bedrooms = raw.get("bedrooms")
    if not isinstance(bedrooms, int):
        m = _INT_RE.search(str(raw.get("rooms") or ""))
        bedrooms = int(m.group(0)) if m else None

    price = raw.get("monthlyPrice") if section == "rent" and raw.get("monthlyPrice") else raw.get("price")
    price = int(_num(price) or 0)

    rent = None
    if section == "rent":
        rent = {
            "monthly_price": price or None,
            "terms": [t for t in (raw.get("rentalTerms") or []) if t in ("off_season", "year")],
            "deposit": _num(raw.get("deposit")),
            "available_from": raw.get("availableFrom"),
            "min_term_months": _num(raw.get("minTermMonths")),
            "utilities": raw.get("utilities"),
            "pets": raw.get("pets"),
        }

    object_id = (raw.get("objectId") or "").strip() or None
    derivatives = derivatives or {}
    fields = dict(
        id=str(raw.get("id") or object_id or ""),
        object_id=object_id,
        slug=slugify(object_id or raw.get("id") or raw.get("title") or "object"),
        section=section, category=category, type=kind, kind=kind,
        district=district, district_label_raw=raw.get("location"),
        region=districts.region(district),
        coords=coords,
        map_coords=None if confidential else (coords or districts.coords(district)),
        price=price,
        area=_num(raw.get("area")), land_area=_num(raw.get("landArea")),
        bedrooms=bedrooms,
        features=[str(f).strip() for f in raw.get("features") or [] if str(f).strip()] if not confidential else [],
        images=images, illustration=illustration,
        thumb=_thumb(root, derivatives, images[0] if images else illustration),
        crm_title=_crm_title(raw),
        confidential=confidential, disclosure=disclosure,
        is_complex=bool(raw.get("isComplex")) or kind == "development",
        units=list(raw.get("units") or []) if not confidential else [],
        rent=rent,
        texts=_texts(raw) if not confidential else {"card": {}, "description": {}, "location": {}},
        source=source,
        raw=raw,
    )
    for camel, snake in _CAMEL_PASSTHROUGH.items():
        value = raw.get(camel)
        fields[snake] = None if value in ("", None) or confidential and snake in ("project_name", "project_id") else value
    return Listing(**fields)


# ---------------------------------------------------------------- collection
class Listings:
    def __init__(self, items, i18n, districts):
        self.items = items
        self.i18n = i18n
        self.districts = districts
        self._by_slug = {(l.section, l.slug): l for l in items}
        self._by_id = {}
        for l in items:
            for key in (l.id, l.id.lower(), l.object_id, (l.object_id or "").lower(), l.slug):
                if key:
                    self._by_id.setdefault(key, l)

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def query(self, section=None, category=None, kind=None):
        return [
            l for l in self.items
            if (section is None or l.section == section)
            and (category is None or l.category == category)
            and (kind is None or l.kind == kind)
        ]

    def by_slug(self, section, slug):
        return self._by_slug.get((section, slug))

    def by_id(self, ident):
        return self._by_id.get(ident) or self._by_id.get(str(ident).lower())

    # ------------------------------------------------ localized texts
    # Политика заголовков (решение координатора):
    #   * не-проекты: H1 и заголовок карточки — сгенерированный локализованный заголовок
    #     («Квартира 56 м² — Ластва Грбальска»); CRM-название не показывается никогда
    #     (в нём бывают имена владельцев: «Stan od Aleksandra u …»);
    #   * проекты строительства (kind=development): CRM-название = имя проекта;
    #   * confidential — анонимно: «{Тип}, {регион}».
    def _t(self, lang, key, **fmt):
        return self.i18n.t(lang, key, **fmt)

    def _own(self, lang, key):
        """Value of `key` only when it exists in `lang` itself (no cross-language fallback).

        Grammar-dependent fragments (Russian locatives «в Бечичи», «в центре Будвы») must not
        leak into another language's sentence: a de page falls back to the neutral pattern
        instead of an English/Russian fragment.
        """
        value = self.i18n.raw(lang, key)
        return value if isinstance(value, str) and value else None

    def type_name(self, kind, lang):
        return self._t(lang, f"common.types.{kind}")

    def district_name(self, l, lang):
        return self._t(lang, f"common.districts.{l.district}")

    def district_title(self, l, lang):
        """District as used in titles: «Будва, центр» instead of «Будва — центр» (no double dash)."""
        return self._own(lang, f"property.gen.district_title.{l.district}") or self.district_name(l, lang)

    def region_name(self, l, lang):
        return self._t(lang, f"common.regions.{l.region}")

    def where(self, l, lang):
        """Place phrase: «в Бечичи» / «in central Budva» / fallback «в районе {district}»."""
        own = self._own(lang, f"property.gen.where_in.{l.district}")
        if own:
            return own
        if l.district == "other":
            return self._t(lang, "property.gen.where_other")
        return self._t(lang, "property.gen.where", district=self.district_name(l, lang))

    def project_name(self, l):
        """Name of a public development project (CRM title), else None."""
        if l.kind == "development" and not l.confidential:
            return l.crm_title or l.project_name or None
        return None

    def params(self, l, lang):
        """[(icon, text)] — the structured facts shown on cards (no invented data)."""
        out = []
        if l.kind == "land":
            if l.land_area or l.area:
                out.append(("land", self._t(lang, "common.params.area", n=fmt_num(l.land_area or l.area, lang))))
            return out
        if l.area:
            out.append(("area", self._t(lang, "common.params.area", n=fmt_num(l.area, lang))))
        if l.land_area:
            out.append(("land", self._t(lang, "common.params.land_area", n=fmt_num(l.land_area, lang))))
        if l.bedrooms:
            out.append(("bed", self.i18n.plural(lang, "common.plural.bedrooms", l.bedrooms)))
        bathrooms = _num(l.bathrooms)
        if isinstance(bathrooms, int) and bathrooms > 0:
            out.append(("bath", self.i18n.plural(lang, "common.plural.bathrooms", bathrooms)))
        return out

    def _fmt(self, l, lang):
        type_name = self.type_name(l.kind, lang)
        area = l.land_area if l.kind == "land" else l.area
        return {
            "type": type_name,
            "type_lc": self._t(lang, f"common.types_lc.{l.kind}"),
            "district": self.district_name(l, lang),
            "district_title": self.district_title(l, lang),
            "where": self.where(l, lang),
            "region": self.region_name(l, lang),
            "area": fmt_num(area, lang) if area else "",
            "params": ", ".join(text for _, text in self.params(l, lang)),
            "id": l.object_id or l.id,
            "name": self.project_name(l) or "",
        }

    def title(self, l, lang):
        """Localized H1: '{Type} {area} m² — {District}' (anonymized for confidential).

        Development projects with a name: '{name} — {District}' (the type is shown as the eyebrow;
        a unit's area is not the project's area, so it is never put into the title)."""
        f = self._fmt(l, lang)
        if l.confidential:
            return self._t(lang, "property.gen.confidential_title", **f)
        if l.kind == "development":
            key = "property.gen.title_project" if f["name"] else "property.gen.title_no_area"
        else:
            key = "property.gen.title" if f["area"] else "property.gen.title_no_area"
        return self._t(lang, key, **f)

    def name(self, l, lang):
        """Card heading: the project name for public development projects, else the localized title.

        Never the CRM title of an apartment/house/villa/land listing (owners' names)."""
        return self.project_name(l) or self.title(l, lang)

    def has_card_text(self, l, lang):
        """True when the card has its own text (CRM card text in this language, or the
        confidential note); generated card text only repeats the card's facts."""
        return bool(l.texts["card"].get(lang)) or l.confidential

    def card_text(self, l, lang):
        if l.texts["card"].get(lang):
            return l.texts["card"][lang]
        f = self._fmt(l, lang)
        if l.confidential:
            return self._t(lang, "property.gen.confidential_card", **f)
        return self._t(lang, "property.gen.card" if f["params"] else "property.gen.card_no_params", **f)

    def _facts_sentence(self, l, lang):
        """«Площадь дома — 175 м², участок — 3 700 м², 3 спальни.» from structured fields only."""
        parts = []

        def n(v):
            return fmt_num(v, lang)
        if l.kind == "land":
            if l.land_area or l.area:
                parts.append(self._t(lang, "property.gen.part_plot", n=n(l.land_area or l.area)))
        else:
            if l.area:
                key = {"house": "property.gen.part_area_house", "villa": "property.gen.part_area_house",
                       "development": "property.gen.part_area_unit"}.get(l.kind, "property.gen.part_area")
                parts.append(self._t(lang, key, n=n(l.area)))
            if l.land_area:
                parts.append(self._t(lang, "property.gen.part_land", n=n(l.land_area)))
            if l.bedrooms:
                parts.append(self.i18n.plural(lang, "common.plural.bedrooms", l.bedrooms))
            bathrooms = _num(l.bathrooms)
            if isinstance(bathrooms, int) and bathrooms > 0:
                parts.append(self.i18n.plural(lang, "common.plural.bathrooms", bathrooms))
        if not parts:
            return ""
        text = ", ".join(parts)
        return text[:1].upper() + text[1:] + "."

    def _price_sentence(self, l, lang):
        price = fmt_price(l.price, lang) if l.price else ""
        if l.section == "rent":
            return self._t(lang, "property.gen.price_rent", price=price) if price else ""
        if not price:
            return self._t(lang, "property.gen.price_on_request")
        area = l.land_area if l.kind == "land" else l.area
        if area and l.kind != "development":
            per = fmt_price(round(l.price / float(area)), lang)
            return self._t(lang, "property.gen.price_per_m2", price=price, per=per)
        return self._t(lang, "property.gen.price", price=price)

    def description(self, l, lang):
        """«Об объекте»: CRM text in this language, else sentences built from structured fields.
        Paragraphs are separated by a blank line."""
        if l.texts["description"].get(lang):
            return l.texts["description"][lang]
        f = self._fmt(l, lang)
        if l.confidential:
            return self._t(lang, "property.gen.confidential_description", **f)
        lead_key = "property.gen.lead_project" if f["name"] else "property.gen.lead"
        first = [self._t(lang, lead_key, **f), self._facts_sentence(l, lang), self._price_sentence(l, lang)]
        closing = self._t(lang, "property.gen.closing" if f["params"] else "property.gen.closing_no_params", **f)
        return " ".join(p for p in first if p) + "\n\n" + closing

    def location_text(self, l, lang):
        if l.texts["location"].get(lang):
            return l.texts["location"][lang]
        f = self._fmt(l, lang)
        if l.confidential:
            return self._t(lang, "property.gen.location_confidential", **f)
        about = self._own(lang, f"property.gen.district_about.{l.district}")
        tail = self._t(lang, "property.gen.location_coords" if l.coords else "property.gen.location_approx", **f)
        if about:
            return about + " " + tail
        return self._t(lang, "property.gen.location", **f) + " " + tail

    def facts(self, l, lang):
        """Fact groups for the property page: [(group_key, [(label_key, value, icon)])].

        Labels are i18n keys property.facts.<label_key>; values are localized strings
        (free-text CRM values are passed through as they are)."""
        t = self._t

        def n(v):
            return fmt_num(v, lang)
        main, money, rent, more = [], [], [], []
        main.append(("type", self.type_name(l.kind, lang), "building"))
        if l.confidential:
            main.append(("region", self.region_name(l, lang), "pin"))
            return [("main", main)]
        main.append(("district", self.district_name(l, lang), "pin"))
        if l.kind == "land":
            if l.land_area or l.area:
                main.append(("plot", t(lang, "common.params.area", n=n(l.land_area or l.area)), "land"))
        else:
            if l.area:
                main.append(("area_unit" if l.kind == "development" else "area",
                             t(lang, "common.params.area", n=n(l.area)), "area"))
            if l.land_area:
                main.append(("plot", t(lang, "common.params.area", n=n(l.land_area)), "land"))
            if l.bedrooms:
                main.append(("bedrooms", n(l.bedrooms), "bed"))
            bathrooms = _num(l.bathrooms)
            if isinstance(bathrooms, int) and bathrooms > 0:
                main.append(("bathrooms", n(bathrooms), "bath"))
        for key, icon in (("floor", "floor"), ("balconies", "area"), ("view", "pin")):
            value = getattr(l, key, None)
            if value not in (None, ""):
                main.append((key, str(value), icon))

        if l.section == "rent" and l.rent:
            r = l.rent
            rent.append(("monthly", self._money(l.price, lang, per_month=True), "key"))
            if r.get("terms"):
                rent.append(("terms", ", ".join(t(lang, f"common.rental_terms.{x}") for x in r["terms"]), "calendar"))
            if r.get("min_term_months"):
                rent.append(("min_term", self.i18n.plural(lang, "property.plural.months", r["min_term_months"]), "calendar"))
            if r.get("deposit") is not None:
                rent.append(("deposit", self._money(r["deposit"], lang) if r["deposit"]
                             else t(lang, "property.values.no_deposit"), "document"))
            if r.get("available_from"):
                rent.append(("available_from", self.date(r["available_from"], lang), "calendar"))
            if r.get("utilities") in ("included", "not_included", "partial"):
                rent.append(("utilities", t(lang, f"property.values.utilities.{r['utilities']}"), "check"))
            if r.get("pets") in ("allowed", "not_allowed", "by_agreement"):
                rent.append(("pets", t(lang, f"property.values.pets.{r['pets']}"), "check"))
        else:
            money.append(("price", self._money(l.price, lang), "key"))
            area = l.land_area if l.kind == "land" else l.area
            if l.price and area and l.kind != "development":
                money.append(("price_m2", fmt_price(round(l.price / float(area)), lang), "area"))
            for key in ("payment_plan", "transfer_tax"):
                value = getattr(l, key, None)
                if value not in (None, ""):
                    money.append((key, str(value), "document"))

        for key, attr, icon in (("furnishing", "furnishing", "check"), ("condition", "condition", "check"),
                                ("parking", "parking", "check"), ("distance_to_sea", "distance_to_sea", "pin"),
                                ("completion", "completion_date", "calendar")):
            value = getattr(l, attr, None)
            if value not in (None, ""):
                more.append((key, str(value), icon))
        groups = [("main", main), ("rent" if l.section == "rent" else "money", rent or money), ("more", more)]
        return [(g, rows) for g, rows in groups if rows]

    def _money(self, value, lang, per_month=False):
        if not value:
            return self._t(lang, "common.price.on_request")
        text = fmt_price(value, lang)
        return f"{text} {self._t(lang, 'common.units.per_month')}" if per_month else text

    def date(self, value, lang):
        """ISO date → «1 ноября 2026» / «1 November 2026» via property.months.m1…m12 + property.date."""
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(value or ""))
        if not m:
            return str(value or "")
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not 1 <= mo <= 12:
            return str(value)
        month = self._t(lang, f"property.months.m{mo}")
        return self._t(lang, "property.date", d=d, month=month, y=y)

    @staticmethod
    def catalog_order(items):
        """Default catalog order: with photos first, then with a price; CRM order otherwise (stable)."""
        return sorted(items, key=lambda x: (0 if x.images else 1, 0 if x.price else 1))

    def similar(self, l, limit=3):
        """Same section + category, without l; with photos first, then by price closeness."""
        pool = [x for x in self.items if x is not l and x.section == l.section and x.category == l.category]

        def key(x):
            closeness = abs(x.price - l.price) if l.price and x.price else float("inf")
            return (0 if x.images else 1, closeness, x.slug)
        return sorted(pool, key=key)[:limit]


def load(root, i18n, districts=None, warnings=None):
    warnings = warnings if warnings is not None else []
    districts = districts or Districts(root)
    items = []
    derivatives = _load_derivatives(root)
    sources = (("sales", "js/data.js"), ("rentals", "js/rentals.js"))
    for source, rel in sources:
        for raw in read_js_array(os.path.join(root, rel)):
            if not isinstance(raw, dict):
                continue
            items.append(_normalize(raw, source, districts, root, warnings, derivatives))
    # Уникальность slug внутри раздела: дубликаты получают суффикс -2, -3…
    seen = {}
    for l in items:
        base, n = l.slug or "object", 1
        slug = base
        while (l.section, slug) in seen:
            n += 1
            slug = f"{base}-{n}"
        if slug != l.slug:
            warnings.append(f"listing {l.id}: slug {l.slug!r} taken in {l.section}/, using {slug!r}")
        l.slug = slug
        seen[(l.section, slug)] = l
    return Listings(items, i18n, districts)
