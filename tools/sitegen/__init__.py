"""Gurevic Real Estate — static site generator (Jinja2 + i18n).

Modules:
    text      slugs, transliteration, text normalization for matching
    i18n      dictionaries i18n/<lang>/<ns>.json, fallback chain, missing-key report
    routes    route table (ARCHITECTURE §3) and URL helpers
    listings  data layer over js/data.js + js/rentals.js (ARCHITECTURE §6)
    render    Jinja2 environment, template globals/filters (ARCHITECTURE §4)
    seo       sitemap.xml, robots.txt, legacy redirects, JSON-LD builders
    core      build orchestration, manifest, static copy, stale cleanup
    checks    link/asset/id/alt/SEO checker used by tools/check_site.py

Entry point: tools/build_site.py (see `python tools/build_site.py --help`).
"""

__all__ = ["core"]
