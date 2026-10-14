"""SEO outputs: JSON-LD objects, sitemap.xml, robots.txt, legacy redirect pages."""

import json
from xml.sax.saxutils import escape as xml_escape

from markupsafe import escape


# ---------------------------------------------------------------- JSON-LD
def agent_jsonld(site, home_url, logo_url):
    c = site["contacts"]
    return {
        "@context": "https://schema.org",
        "@type": "RealEstateAgent",
        "@id": site["site_url"] + "#agency",   # один и тот же узел на всех языках/страницах
        "name": site["brand"] + " Real Estate",
        "alternateName": site["site_name"],
        "legalName": site["legal_name"],
        "url": home_url,
        "logo": logo_url,
        "image": logo_url,
        "telephone": c["phone_e164"],
        "email": c["email"],
        "address": {"@type": "PostalAddress", "addressLocality": c["locality"], "addressCountry": c["country"]},
        "areaServed": [{"@type": "Country", "name": "Montenegro"}, {"@type": "Place", "name": "Budva Riviera"}],
        "sameAs": [c["instagram"]],
    }


def breadcrumbs_jsonld(items):
    """items: [(label, absolute url)]"""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": label, "item": url}
            for i, (label, url) in enumerate(items, start=1)
        ],
    }


def listing_jsonld(listing, name, description, url, images, per_month=False):
    data = {
        "@context": "https://schema.org",
        "@type": "RealEstateListing",
        "name": name,
        "description": description,
        "url": url,
    }
    if images:
        data["image"] = images
    if listing.object_id and not listing.confidential:
        data["identifier"] = listing.object_id
    offer = {"@type": "Offer", "priceCurrency": "EUR", "availability": "https://schema.org/InStock", "url": url}
    if listing.price and not listing.confidential:
        offer["price"] = listing.price
        if per_month:
            offer["priceSpecification"] = {
                "@type": "UnitPriceSpecification", "price": listing.price,
                "priceCurrency": "EUR", "unitCode": "MON",
            }
    data["offers"] = offer
    return data


# ---------------------------------------------------------------- sitemap / robots
def sitemap_xml(entries):
    """entries: [(loc, [(hreflang, href), …])] → sitemap with xhtml:link alternates."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    for loc, alternates in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        for hreflang, href in alternates:
            lines.append(f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{xml_escape(href)}"/>')
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt(site_url):
    return f"User-agent: *\nAllow: /\n\nSitemap: {site_url}sitemap.xml\n"


# ---------------------------------------------------------------- legacy redirects
_REDIRECT = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, follow">
<title>{title}</title>
<link rel="canonical" href="{canonical}">
{script}{refresh}
</head>
<body>
<p><a href="{target}">{label}</a></p>
</body>
</html>
"""


def redirect_html(target, canonical, title, label, script=""):
    """Static redirect: meta refresh (+ optional JS that runs first)."""
    refresh = f'<meta http-equiv="refresh" content="0; url={escape(target)}">'
    if script:
        # JS сам выбирает адрес; без JS — обычный meta refresh
        refresh = f"<noscript>{refresh}</noscript>"
    return _REDIRECT.format(
        title=escape(title), canonical=escape(canonical), target=escape(target),
        label=escape(label), script=script, refresh=refresh,
    )


def object_redirect_script(id_map, fallback):
    """object.html?id=<id> → new property path (inline id→path map)."""
    data = json.dumps(id_map, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    data = data.replace("<", "\\u003c")
    return (
        "<script>(function(){var m=" + data + ";"
        "var id='';try{id=new URLSearchParams(location.search).get('id')||'';}catch(e){}"
        "var p=m[id]||m[id.toLowerCase()]||" + json.dumps(fallback) + ";"
        "location.replace(p+location.hash);})();</script>\n"
    )
