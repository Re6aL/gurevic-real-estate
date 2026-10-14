"""Static checks over a built site folder (used by tools/check_site.py).

Per generated .html page:
  * every internal href/src/srcset (and og:image/canonical/hreflang under site_url) resolves
    to an existing file — folder URLs → index.html, ?query and #hash stripped;
  * #anchors exist on the target page (or on the same page);
  * duplicate ids, <img> without alt;
  * SEO basics: <title>, meta description, canonical (unless noindex), exactly one <h1>.
Redirect stubs (meta refresh) are only link-checked.
"""

import json
import os
import posixpath
import re
import urllib.parse
from html.parser import HTMLParser

NOT_SITE_DIRS = {"src", "tools", "docs", "api", "i18n", "node_modules"}
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "whatsapp:", "blob:")
LINK_ATTRS = {
    "a": ("href",), "link": ("href",), "script": ("src",), "img": ("src", "srcset"),
    "source": ("src", "srcset"), "iframe": ("src",), "video": ("src", "poster"), "audio": ("src",),
    "embed": ("src",), "object": ("data",), "use": ("href", "xlink:href"),
}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.links = []          # (line, tag, attr, value)
        self.img_no_alt = []     # line
        self.h1 = 0
        self.title = None
        self._in_title = False
        self.description = None
        self.canonical = None
        self.refresh = False
        self.noindex = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        line = self.getpos()[0]
        if "id" in a and a["id"]:
            self.ids.append(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.append(a["name"])
        for attr in LINK_ATTRS.get(tag, ()):
            if a.get(attr):
                self.links.append((line, tag, attr, a[attr]))
        if tag == "img" and "alt" not in a:
            self.img_no_alt.append(line)
        if tag == "h1":
            self.h1 += 1
        if tag == "title":
            self._in_title = True
            self.title = ""
        if tag == "meta":
            name = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            if name == "description":
                self.description = a.get("content") or ""
            if name == "robots" and "noindex" in (a.get("content") or "").lower():
                self.noindex = True
            if (a.get("http-equiv") or "").lower() == "refresh":
                self.refresh = True
            if prop in ("og:image", "og:url") and a.get("content"):
                self.links.append((line, "meta", prop, a["content"]))
        if tag == "link" and "canonical" in (a.get("rel") or "").lower().split():
            self.canonical = a.get("href")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def _srcset_urls(value):
    return [part.strip().split()[0] for part in value.split(",") if part.strip()]


class Checker:
    def __init__(self, out_dir, site_url=None):
        self.out = os.path.abspath(out_dir)
        self.site_url = (site_url or "").rstrip("/") + "/" if site_url else None
        self.errors = []
        self.warnings = []
        self._parsed = {}
        self._kinds = {}
        self.pages = 0
        self.links = 0

    # ------------------------------------------------------------
    def _kind(self, rel):
        """'file' | 'dir' | None (cached: тысячи ссылок на одни и те же файлы)."""
        if rel not in self._kinds:
            full = os.path.join(self.out, *rel.split("/"))
            self._kinds[rel] = "file" if os.path.isfile(full) else "dir" if os.path.isdir(full) else None
        return self._kinds[rel]

    def parse(self, rel):
        if rel not in self._parsed:
            p = PageParser()
            with open(os.path.join(self.out, *rel.split("/")), encoding="utf-8", errors="replace") as f:
                p.feed(f.read())
            p.close()
            self._parsed[rel] = p
        return self._parsed[rel]

    def _local(self, page_rel, url):
        """URL → (root-relative file path, fragment, error) or None when external/skipped."""
        url = url.strip()
        if not url or url.startswith(SKIP_SCHEMES):
            return None
        absolute = bool(self.site_url) and url.startswith(self.site_url)
        if absolute:
            rest, base = url[len(self.site_url):], ""
        elif re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) or url.startswith("//"):
            return None  # внешний адрес
        else:
            rest, base = url, posixpath.dirname(page_rel)
        rest, _, frag = rest.partition("#")
        path = urllib.parse.unquote(rest.split("?")[0])
        if path.startswith("/"):
            # от корня домена — на GitHub Pages (подпуть /gurevic-real-estate/) сломается
            return (None, frag, "root-absolute URL breaks on the GitHub Pages sub-path")
        if path == "":
            return ("index.html" if absolute else page_rel, frag, None)
        joined = posixpath.normpath(posixpath.join(base, path))
        if joined == ".":
            return ("index.html", frag, None)
        if joined.startswith(".."):
            return (None, frag, "URL escapes the site root")
        if path.endswith("/"):
            joined += "/index.html"
        return (joined, frag, None)

    def _check_link(self, page_rel, line, tag, attr, url, ids):
        target = self._local(page_rel, url)
        if target is None:
            return
        self.links += 1
        where = f"{page_rel}:{line} <{tag} {attr}>"
        rel, frag, error = target
        if error:
            self.errors.append(f"{where}: {error}: {url}")
            return
        if self._kind(rel) == "dir":
            self.warnings.append(f"{where}: folder URL without trailing slash: {url}")
            rel = rel + "/index.html"
        if self._kind(rel) != "file":
            self.errors.append(f"{where}: broken link → {rel} ({url})")
            return
        if frag and tag in ("a", "link") and rel.endswith(".html"):
            frag = urllib.parse.unquote(frag)
            target_ids = ids if rel == page_rel else set(self.parse(rel).ids)
            if frag not in target_ids:
                self.errors.append(f"{where}: missing anchor #{frag} in {rel}")

    def check_page(self, rel):
        self.pages += 1
        p = self.parse(rel)
        ids = set(p.ids)
        seen, dups = set(), set()
        for i in p.ids:
            (dups if i in seen else seen).add(i)
        for d in sorted(dups):
            self.errors.append(f"{rel}: duplicate id=\"{d}\"")
        for line in p.img_no_alt:
            self.errors.append(f"{rel}:{line}: <img> without alt")
        for line, tag, attr, value in p.links:
            urls = _srcset_urls(value) if attr == "srcset" else [value]
            for url in urls:
                self._check_link(rel, line, tag, attr, url, ids)
        if p.canonical:
            self._check_link(rel, 0, "link", "canonical", p.canonical, ids)
        if p.refresh:
            return
        if not (p.title or "").strip():
            self.errors.append(f"{rel}: missing <title>")
        if not (p.description or "").strip():
            self.errors.append(f"{rel}: missing meta description")
        if not p.canonical and not p.noindex:
            self.errors.append(f"{rel}: missing canonical")
        if p.h1 == 0:
            self.errors.append(f"{rel}: missing <h1>")
        elif p.h1 > 1:
            self.errors.append(f"{rel}: {p.h1} <h1> elements (expected one)")

    def check_sitemap(self):
        path = os.path.join(self.out, "sitemap.xml")
        if not os.path.isfile(path):
            return
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for url in sorted(set(re.findall(r'<loc>([^<]+)</loc>|href="([^"]+)"', text))):
            url = url[0] or url[1]
            if url.startswith("http://www.sitemaps.org/") or url.startswith("http://www.w3.org/"):
                continue
            target = self._local("sitemap.xml", url)
            if target is None or target[2]:
                self.errors.append(f"sitemap.xml: URL outside the site: {url}")
                continue
            if self._kind(target[0]) != "file":
                self.errors.append(f"sitemap.xml: {url} → missing {target[0]}")


def html_files(out_dir, manifest_only=True):
    """Pages to check: from .generated-manifest.json when present, else every .html."""
    manifest = os.path.join(out_dir, ".generated-manifest.json")
    if manifest_only and os.path.isfile(manifest):
        with open(manifest, encoding="utf-8") as f:
            files = json.load(f).get("files", [])
        return sorted(f for f in files if f.endswith(".html")), True
    out = []
    for base, dirs, files in os.walk(out_dir):
        # исходники шаблонов и служебные папки — не страницы сайта
        dirs[:] = [d for d in dirs if not d.startswith(".") and not (base == out_dir and d in NOT_SITE_DIRS)]
        for name in files:
            if name.endswith(".html"):
                out.append(os.path.relpath(os.path.join(base, name), out_dir).replace(os.sep, "/"))
    return sorted(out), False
