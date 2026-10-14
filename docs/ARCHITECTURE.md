# Gurevic Real Estate — architecture of the v3 site (static generator + 7 languages)

This document is the **contract** shared by everybody who edits the site. Read it fully
before changing anything. Russian is the primary content language; the site is
translated into en, de, fr, pl, uk, he (Hebrew is RTL and mirrored).

## 0. Ground rules

- Hosting: GitHub Pages, legacy build, branch `main`, folder `/` →
  `https://re6al.github.io/gurevic-real-estate/` (a **sub-path**!). A custom domain may be
  added later. Therefore: **every internal link and asset reference is relative** and is
  produced by the generator helpers `url()` / `asset()`. Never hard-code `/buy/` or
  `https://…` for internal links. Absolute URLs exist only in canonical / hreflang / OG /
  JSON-LD / sitemap and are built from `site.site_url`.
- No build step on GitHub's side: the generator runs locally and in the hourly
  `notion-sync` GitHub Action; its output (HTML) is committed.
- Python ≥ 3.11 stdlib + **Jinja2 3.1.x** (+ Pillow for images). Pinned in
  `tools/requirements.txt`. No Node build, no npm deps in the site. Vanilla JS, no frameworks.
- Do not invent facts about the business (deal counts, awards, guarantees, yields, office
  address, licences). Financial figures are always "preliminary / indicative / subject to
  verification". Never promise returns.
- Never publish private CRM data: owner names, commission, cadastral numbers of listings,
  exact addresses, documents. Only the district.
- Never commit secrets. The repository is public.
- Accessibility, mobile and speed are requirements, not extras (see §9).

## 1. Directory layout

```
src/
  site.json                 global config (site_url, languages, contacts, lead endpoint…)
  districts.json            district catalogue: key → aliases (data labels) + coords
  templates/
    base.html               HTML skeleton (head, header include, main, footer include, scripts)
    partials/header.html    top menu (nav + dropdowns + lang switcher + phone dropdown + burger)
    partials/footer.html    bottom menu (sitemap columns, contacts, legal, languages)
    macros/ui.html          generic macros: breadcrumbs, section heads, buttons, icons
    macros/cards.html       listing card macro (catalog + invest subpages)
    macros/forms.html       form-field macros + the concrete lead forms (owned by forms agent)
    pages/<page>.html       one template per page type (see §3)
i18n/<lang>/<namespace>.json   UI strings, one file per namespace per language
tools/
  build_site.py             CLI entry: python tools/build_site.py [--out DIR] [--lang ru,en] [--strict] [--only PREFIX]
  sitegen/                  generator package (core, i18n, routes, listings, render, checks)
  check_site.py             link/asset/id/alt checker over a built output dir
  optimize_images.py        image derivatives (webp/jpg, responsive widths) + img/derivatives.json
  notion_sync.py            Notion → js/data.js (sales) and js/rentals.js (rentals)
css/style.css               base styles (tokens, header, footer, catalog, cards, property)
css/<page>.css              page-specific styles, linked only by that page
js/site.js                  header/menu/burger/lang switcher/contact dropdown (every page)
js/<page>.js                page-specific scripts
api/lead-worker/            Cloudflare Worker: form → Notion "Website Leads" (+ Telegram)
docs/                       ARCHITECTURE.md, NOTION_SETUP.md, CONTENT_TODO.md
```

Generated output (committed, never edit by hand): `index.html`, `404.html`, `robots.txt`,
`sitemap.xml`, the route folders (`buy/`, `rent/`, `invest/`, `owners/`, `about/`,
`services/`, `contact/`, `privacy/`, `map/`), the language folders (`en/`, `de/`, `fr/`,
`pl/`, `uk/`, `he/`) and the legacy redirect files `sale.html`, `rent.html`,
`investments.html`, `object.html`, `map.html`. The generator owns a manifest
`.generated-manifest.json` listing every file it wrote, and deletes stale generated files
from the previous manifest (never anything else).

## 2. Languages and URLs

| code | native name | dir | prefix | og:locale |
|---|---|---|---|---|
| ru | Русский | ltr | (root) | ru_RU |
| en | English | ltr | `en/` | en_GB |
| de | Deutsch | ltr | `de/` | de_DE |
| fr | Français | ltr | `fr/` | fr_FR |
| pl | Polski | ltr | `pl/` | pl_PL |
| uk | Українська | ltr | `uk/` | uk_UA |
| he | עברית | **rtl** | `he/` | he_IL |

- Russian lives at the root. `hreflang` alternates are emitted for all 7 plus
  `x-default` → the English URL.
- `<html lang="he" dir="rtl">` for Hebrew. Everything mirrors (see §9.3).
- Language switcher: links to the **same route** in the other language. The choice is
  remembered in `localStorage['gre_lang']` (wrapped in try/catch). On first visit to any
  page, if nothing is stored and `navigator.languages` prefers another supported language,
  show a small dismissible suggestion bar ("This page is available in English → Switch").
  **Never auto-redirect** (crawlers).
- Fallback chain for missing strings: `lang → en → ru`. `--strict` fails the build when
  a key is missing in `ru` or `en`; for other languages it reports missing keys.

## 3. Routes

Paths are relative to the language root. `key` is what templates pass to `url()`.

| key | path | template | notes |
|---|---|---|---|
| home | `` | pages/home.html | splash (keyhole) + hero + directions + about teaser + CTA. No listing grids. |
| buy | `buy/` | pages/catalog.html | section=buy, category=None |
| buy.apartments | `buy/apartments/` | pages/catalog.html | category=apartments |
| buy.houses | `buy/houses/` | pages/catalog.html | category=houses |
| buy.villas | `buy/villas/` | pages/catalog.html | category=villas |
| buy.land | `buy/land/` | pages/catalog.html | category=land (private-build plots) |
| rent | `rent/` | pages/catalog.html | section=rent (long-term only) + short-term "in development" panel |
| rent.apartments | `rent/apartments/` | pages/catalog.html | |
| rent.houses | `rent/houses/` | pages/catalog.html | houses+villas |
| invest | `invest/` | pages/invest.html | lead-generation page, NOT a catalog |
| invest.hotels | `invest/hotels/` | pages/invest_category.html | |
| invest.land | `invest/land/` | pages/invest_category.html | land for commercial development |
| invest.commercial | `invest/commercial/` | pages/invest_category.html | restaurants, retail, offices, warehouses/logistics, businesses |
| invest.development | `invest/development-projects/` | pages/invest_category.html | CRM type Gradnja |
| owners | `owners/` | pages/owners.html | agency for sellers/landlords + listing request form |
| owners.sell | `owners/sell/` | pages/owners_service.html | |
| owners.rent_out | `owners/rent-out/` | pages/owners_service.html | |
| owners.management | `owners/property-management/` | pages/owners_service.html | |
| about | `about/` | pages/about.html | Ilia Gurevich |
| services | `services/` | pages/services.html | |
| contact | `contact/` | pages/contact.html | |
| privacy | `privacy/` | pages/privacy.html | |
| map | `map/` | pages/map.html | Leaflet map; not in main nav, linked from buy/rent |
| property | `{section}/{slug}/` | pages/property.html | one page per published listing, section ∈ buy/rent/invest |

`404.html` is generated once at the root (GitHub Pages serves it for every unknown URL):
language-neutral, links to the home page of every language.

Legacy files (root only) redirect with `<meta http-equiv="refresh">` + `<link rel=canonical>`
+ JS: `sale.html→buy/`, `rent.html→rent/`, `investments.html→invest/`, `map.html→map/`,
`object.html?id=<id>` → the listing's new path (inline id→path map), otherwise `buy/`.
`leads.html` is deleted (it only read the visitor's own localStorage).

### Main navigation (header)
Аренда (rent ▾ apartments, houses, short-term "скоро") · Покупка (buy ▾ apartments, houses,
villas, land) · Инвестиции (invest ▾ hotels, land, commercial, development) · Владельцам
(owners ▾ sell, rent-out, management) · Услуги · О нас · Контакты · [language ▾] · [phone ▾]
Dropdowns open on hover (pointer: fine) **and** on click/Enter (button with
`aria-expanded`); on ≤1024px everything collapses into a burger off-canvas panel.

### Footer ("нижнее меню")
Columns: Аренда / Покупка / Инвестиции / Владельцам / Агентство (about, services, contact,
privacy) + contacts block (phone, WhatsApp, Telegram, email, Instagram) + language list +
legal line `DOO GUREVIC BUDVA · Budva, Montenegro · © 2026`.

## 4. Templating contract (Jinja2)

Environment: `autoescape=True`, `trim_blocks`, `lstrip_blocks`, `undefined=StrictUndefined`.
Every page template `{% extends "base.html" %}` and fills blocks:
`head_extra`, `main`, `scripts_extra`. Base provides header, footer, skip link, JSON-LD slot.

Globals/filters available in every template:

| name | signature | result |
|---|---|---|
| `t` | `t(key, **fmt)` | translated string for current lang (dotted key `ns.path.key`). `str.format(**fmt)` applied. Keys ending in `_html` return `Markup` (trusted HTML from our own dictionaries); others are escaped. |
| `url` | `url(route_key, lang=None, listing=None)` | **relative** URL from the current page to the route (in `lang`, default current). For `property` pass `listing=`. Always ends with `/` for folders (never `index.html`). |
| `abs_url` | same | absolute URL (site_url based) |
| `asset` | `asset("css/style.css")` | relative path to a root asset + `?v=<8-char content hash>` |
| `img` | `img(src, alt, sizes, cls, loading="lazy", width=None, height=None, fetchpriority=None)` | `<picture>` with webp srcset from `img/derivatives.json` + jpg fallback; falls back to plain `<img>` if no derivatives |
| `fmt_price` | `fmt_price(value, per_month=False)` | locale formatted (`€213 000` ru, `€213,000` en, `213.000 €` de, `213 000 €` fr/pl/uk, he: `€213,000`) |
| `fmt_num` | `fmt_num(value)` | locale grouping |
| `lang`, `dir`, `languages`, `site`, `page`, `route` | | context |
| `listings` | `listings.query(section=…, category=…)` | normalized listing objects (§6) |

`page` object (set by the route + i18n): `key`, `ns`, `title`, `description`, `h1`,
`og_image`, `breadcrumbs` (list of `(label, url)`), `body_class`, `css` (extra css files),
`js` (extra js files, loaded with `defer`), `js_ns` (i18n namespaces exposed to JS),
`noindex`, `category`, `section`.

SEO strings live in i18n: `<ns>.meta.title`, `<ns>.meta.description` (category pages:
`<ns>.categories.<category>.meta.title` etc.). Titles ≤ 60 chars, descriptions 120–160 chars.

### JS bridge
Base template emits before other scripts:
```html
<script>window.SITE={lang:"ru",dir:"ltr",root:"../../",leadEndpoint:"",contacts:{…},i18n:{common:{…},forms:{…}}};</script>
```
`SITE.i18n[ns]` contains the `js` sub-object of each namespace listed in `page.js_ns`
(always `common`). `js/site.js` defines `SITE.t('forms.required', {n: 3})` (lookup in
`SITE.i18n.forms.required`, `{n}` placeholders). JS must never contain user-visible
literals — everything comes from `SITE.t`. Number/currency formatting in JS uses
`Intl.NumberFormat(SITE.lang …)`.

## 5. i18n files

`i18n/<lang>/<ns>.json`, nested objects, UTF-8, 2-space indent, keys in English
snake_case. A key present in `ru` must exist in `en`; other languages are filled by
translators. HTML is allowed only in keys ending with `_html` (and only `<br> <strong>
<em> <a href="…">` built with `{placeholders}` for URLs).

| namespace | owner | content |
|---|---|---|
| common | foundation | site name, nav, footer, languages, buttons, breadcrumbs, units, property types, categories, districts, contacts labels, 404, lang-suggest bar; `common.js.*` |
| forms | forms | field labels, placeholders, options, validation, consent, success/fallback; `forms.js.*` |
| chat | forms | chat widget script; `chat.js.*` |
| home | home | home page |
| catalog | catalog | shared catalog UI (filters, sort, counts, empty states, short-term panel) + `catalog.js.*` |
| buy, rent | catalog | page copy, category landing copy, meta |
| property | catalog | property page labels + description templates + `property.js.*` |
| map | catalog | map page |
| invest | invest | invest page + category pages + illustrative cases |
| owners | owners | owners pages, contract outlines |
| about, services, contact, privacy | info | those pages |

Translation quality bar: native, natural, real-estate register; keep proper names
(Budva, Bečići, DOO GUREVIC BUDVA); Ilia Gurevich name forms: ru «Илья Гуревич»,
uk «Ілля Гуревич», en/de/fr/pl «Ilia Gurevich», he «איליה גורביץ'»; the legal/local form
«Ilija Gurević» may appear in every language as the registered name.

## 6. Listings data layer (`tools/sitegen/listings.py`)

Sources: `js/data.js` (sales CRM "Objekati"; `const LISTINGS = [...]`) and optional
`js/rentals.js` (`const RENTALS = [...]`, rentals CRM). Both written by `notion_sync.py`.
Parse the JSON array between the first `[` and the last `]`.

Normalized listing (Python object/dict, also used by templates):

```
id            raw id from data (may contain non-ASCII, e.g. "žb-26-001p")
object_id     "BD-26-003S" or None
slug          ASCII slug of object_id/id: lowercase, Ž→z Š→s Č/Ć→c Đ→dj, Cyrillic→Latin, [^a-z0-9-] removed
section       buy | rent | invest
category      apartments | houses | villas | land | hotels | commercial | development   (route suffix)
type          apartment | house | villa | land | hotel | commercial | business | development
district      district key from src/districts.json (matched via aliases), or "other"
district_label_raw   original label
coords        [lat, lng] or None (never shown precisely for confidential invest)
price         int or 0;  price_on_request = price == 0
area, land_area, bedrooms (int|None), bathrooms, floor, balconies, view, furnishing,
condition, parking, distance_to_sea, completion_date, payment_plan, transfer_tax
features      list[str]
images        list of original paths (relative to site root), may be empty
crm_title     raw CRM title, None when it was auto-generated by the sync
confidential  bool (invest only; see below)
units         list of units for projects (unitCode, floor, rooms, area, view, price, status)
rent          dict or None: monthly_price, terms (["off_season","year"]), deposit,
              available_from, min_term_months, utilities, pets
texts         {"card": {lang: str}, "description": {lang: str}, "location": {lang: str}}
              only CRM-provided texts (ru from "Website Description", other langs from
              "Website Description EN"/"DE"… when present); otherwise generated (see below)
```

Classification (sales DB):
- `Property Type` Apartment→apartment, House→house, Villa→villa, Land→land,
  Hotel→hotel, Commercial/Office/Retail/Industrial/Warehouse→commercial,
  Business→business, Gradnja→development.
- Optional CRM select `Website Section` (Buy/Invest) overrides; default: apartment, house,
  villa, land → **buy**; hotel, commercial, business, development → **invest**.
- buy categories: apartment→apartments, house→houses, villa→villas, land→land.
- invest categories: hotel→hotels, land→land, commercial/business→commercial,
  development→development.
- rentals DB: section **rent**; apartment→apartments, house/villa→houses.
- Optional CRM select `Disclosure` (Public/Confidential). Default: development → Public;
  hotel/commercial/business/invest-land → **Confidential**. Confidential listings: title,
  card and page are anonymized (`"{Type}, {region}"`), no CRM name, no photos (category
  illustration instead), no map pin (district text only), price labelled "indicative".

Generated texts (when the CRM gives none) are built **per language** from structured fields
via i18n templates in `property.json` (`property.gen.*`), e.g.
`"{type} in {district}: {area} m², {bedrooms_phrase}."` — never with invented facts.
Localized title when `crm_title` is None: `"{Type} {area} m² — {District}"`.
When `crm_title` exists it is shown as the project/listing name under a localized H1.

API: `load(root) -> Listings`; `Listings.query(section=None, category=None)`;
`Listings.by_slug(section, slug)`; `title(l, lang)`, `card_text(l, lang)`,
`description(l, lang)`, `location_text(l, lang)`.

## 7. Forms and leads

All forms are rendered by macros in `src/templates/macros/forms.html` and enhanced by
`js/forms.js` (validation messages from `SITE.t`, honeypot, timing, submit, success and
fallback states). Payload (JSON, `POST SITE.leadEndpoint`, `Content-Type: text/plain`
to avoid CORS preflight):

```json
{
  "form": "investor | investor_company | owner | contact | rent_request | buy_request | property_request | chat",
  "lang": "ru", "page": "<absolute page url>", "ts": "<ISO time>", "elapsed_ms": 12345,
  "hp": "", "consent": true, "consent_version": "2026-10",
  "utm": {"source": "", "medium": "", "campaign": ""},
  "fields": { "name": "...", "company": "...", "email": "...", "phone": "...", "...": "..." }
}
```

Field names (`fields.*`) are the same keys as in `docs/NOTION_SETUP.md` → "Website Leads".
When `leadEndpoint` is empty or the request fails, the form shows the **fallback**: a
summary of what the visitor typed + buttons "Send via WhatsApp" (prefilled `wa.me` text),
"Telegram" (opens `t.me/hurewicz`, text copied to clipboard) and "E-mail" (prefilled
`mailto:`). So every CTA works before the backend is deployed.
Investor forms never ask for passport data or financial documents.

## 8. Shared front-end pieces

- `css/style.css`: tokens (`--navy #14273b`, `--navy-2`, `--gold #b9975b`, `--gold-2`,
  `--gold-dark`, `--ink`, `--muted`, `--line`, `--bg`, `--bg-soft`, `--radius`, shadows,
  `--font-display` Futura PT, `--font-body` system stack), header, footer, buttons,
  sections, catalog hero, filter panel, cards, property page. Keep the existing visual
  language (navy header, gold pill phone button, uppercase Futura nav, white cards).
- Page agents put page-specific CSS in `css/<page>.css`; never edit another agent's file.
- Icons: inline SVG via `macros/ui.html` `icon(name)`; no icon fonts, no emoji in UI chrome.
- Scripts: `defer`, no inline handlers (`onclick=`), no global leaks except `SITE`, `Chat`.

## 9. Quality requirements

### 9.1 Speed
- Pre-rendered HTML (cards, texts) — content visible without JS.
- Images through `img()` (webp + srcset + width/height + lazy except LCP image with
  `fetchpriority="high"`). Hero images ≤ 300 KB at 1920w. Card thumbs ≤ 60 KB.
- One base CSS + one page CSS; fonts: preload `futura-book.woff2` only, `font-display:swap`
  (the Jost fallback is never preloaded).
- Third-party only where needed: Leaflet on `map/` only; Google Maps iframe on property
  pages behind a click-to-load facade.
### 9.2 Accessibility (WCAG 2.2 AA)
Skip link, landmarks, one H1, logical headings, labels for every input, errors linked by
`aria-describedby` + `aria-live`, visible focus, keyboard-operable menus/dropdowns/gallery,
44×44 px touch targets on mobile, contrast ≥ 4.5:1 for text (gold text on white must use
`--gold-dark` or darker), `prefers-reduced-motion` disables splash/slider/zoom animations,
alt texts from i18n.
### 9.3 RTL (Hebrew)
Use CSS logical properties everywhere (`margin-inline-start`, `padding-inline`,
`inset-inline-start`, `text-align: start`, `border-inline-start`…). Directional icons
(arrows, chevrons, carets of sliders) are flipped with `[dir="rtl"] .icon-dir { transform: scaleX(-1) }`.
Phone numbers, e-mails, prices and IDs are wrapped in `<bdi>`/`dir="ltr"` spans so they
don't scramble. Hebrew font stack: `'Segoe UI', 'Arial Hebrew', 'Noto Sans Hebrew', Arial, sans-serif`
(Futura PT has no Hebrew glyphs — use it only for Latin/Cyrillic).
### 9.4 SEO
Per page: unique `<title>`, meta description, one H1, H2 sections, self canonical,
hreflang alternates, Open Graph (`og:title`, `og:description`, `og:url`, `og:image`
1200×630, `og:locale`, `og:locale:alternate`, `og:type`), Twitter card, JSON-LD
(`RealEstateAgent` on home/about/contact, `BreadcrumbList` on inner pages,
`RealEstateListing`+`Offer` on property pages). `sitemap.xml` with `xhtml:link`
alternates; `robots.txt` pointing to it. Filters never create indexable URLs.

## 10. Verifying your work

- Build into a private folder: `python tools/build_site.py --out <scratch>/site-<you>`
  and serve it: `python -m http.server <unique port 8800-8899> --directory <that folder>`
  (run in background; stop it when done).
- Screenshots: headless Chrome, private profile:
  `"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --hide-scrollbars --user-data-dir=<scratch>/chrome-<you> --window-size=1366,900 --screenshot=<file>.png --virtual-time-budget=5000 http://localhost:<port>/<path>`
  (mobile: `--window-size=390,844`; read the PNG with the Read tool to look at it).
  Rendered DOM after JS: `--dump-dom` instead of `--screenshot`.
- `python tools/check_site.py <out dir>` must report 0 broken links/assets.
- Do **not** use the shared in-app browser pane and do not run `git add/commit/push` —
  the coordinator integrates and commits.

## 11. Integration notes (foundation → page agents)

- **Chat on every page.** `tools/sitegen/core.py` adds `js/chat.js` (after the page's own
  scripts) and the `chat` i18n namespace to every page (`GLOBAL_JS`, `GLOBAL_JS_NS`). Do not add
  them to routes or templates again. Any element with `data-chat-open` opens the chat;
  the chat loads `js/forms.js`/`css/forms.css` itself on pages without forms.
- **Asset hashes are line-ending independent**: `asset()` hashes text files (`.css .js .json …`)
  with CRLF→LF, so a Windows checkout (`core.autocrlf=true`) and the Linux CI produce the same
  HTML. Write new files with LF anyway.
- **Logos** in header/footer go through `img()` (lossless WebP from `img/derivatives.json`);
  `.logo picture, .foot-logo picture, .nav-panel-head picture { display: contents }` keeps the
  flex layout. Page templates that show a logo should do the same.
- **Fonts**: `assets/fonts/futura-*.woff2` contain only ASCII + Cyrillic — no `ć č ž š đ`,
  `é ü ß`, `ł ą ę`, `²`, `« »`. Those glyphs fall back per character to **'GR Jost'**
  (Jost, SIL OFL — `assets/fonts/jost/`, latin + latin-ext subsets with `unicode-range`,
  weights 300/400/600/700, approved by the client), then to system faces
  (`--font-display: 'Futura PT', 'GR Jost', Futura, …`). Futura PT stays first, so Cyrillic
  and ASCII keep Futura. Jost is not preloaded: a subset downloads only when a page uses it.
- **Rental value labels**: `common.rent_values.utilities.{included,not_included,partial}`,
  `common.rent_values.pets.{allowed,not_allowed,by_agreement}`; rental terms are
  `common.rental_terms.{off_season,year,short_term}`.
- **CI** (`.github/workflows/notion-sync.yml`): venv with `tools/requirements.txt` →
  notion sync → Dropbox photos → `notion_sync.py --sanitize` → `optimize_images.py` →
  `build_site.py --strict` → `check_site.py` → commit. A strict-build or checker failure
  blocks the hourly commit, so keep `python tools/build_site.py --strict` and
  `python tools/check_site.py` green before handing work over.
- **`.nojekyll`** at the root: GitHub Pages serves the files as they are (no Jekyll pass).
- **Tests**: `python -m unittest discover tools/tests`; worker:
  `cd api/lead-worker && node --test` (on Node 24 `node --test api/lead-worker/test` with a
  directory argument does not work; use `node --test "api/lead-worker/test/*.test.mjs"`).
