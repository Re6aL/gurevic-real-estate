#!/usr/bin/env python3
"""Check a built site folder: broken internal links/assets/anchors, duplicate ids,
<img> without alt, missing <title>/<h1>/meta description/canonical, more than one <h1>.

    python tools/check_site.py                 # the repo root (only pages listed in .generated-manifest.json)
    python tools/check_site.py ../site-test    # a private build folder
    python tools/check_site.py DIR --all       # every .html in DIR, manifest or not

Absolute URLs under site_url (canonical, hreflang, og:image, sitemap) are mapped to local files.
Exit code 1 when any error is found.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from sitegen.checks import Checker, html_files  # noqa: E402


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", nargs="?", default=ROOT, help="built site folder (default: repo root)")
    ap.add_argument("--all", action="store_true", help="check every .html, not only manifest files")
    ap.add_argument("--site-url", default=None, help="override site_url from src/site.json")
    ap.add_argument("-v", "--verbose", action="store_true", help="print warnings too")
    ap.add_argument("--max", type=int, default=200, help="max errors to print (default 200)")
    args = ap.parse_args(argv)

    site_url = args.site_url
    if site_url is None:
        with open(os.path.join(ROOT, "src", "site.json"), encoding="utf-8") as f:
            site_url = json.load(f)["site_url"]
    out = os.path.abspath(args.dir)
    files, from_manifest = html_files(out, manifest_only=not args.all)
    if not files:
        print(f"[x] no .html files found in {out}")
        return 1
    checker = Checker(out, site_url)
    for rel in files:
        checker.check_page(rel)
    checker.check_sitemap()

    for e in checker.errors[: args.max]:
        print(f"[x] {e}")
    if len(checker.errors) > args.max:
        print(f"[x] … and {len(checker.errors) - args.max} more")
    if args.verbose:
        for w in checker.warnings:
            print(f"[?] {w}")
    scope = "manifest pages" if from_manifest else "all .html files"
    status = "ok" if not checker.errors else "x"
    print(f"[{status}] {checker.pages} pages ({scope}), {checker.links} internal links checked: "
          f"{len(checker.errors)} errors, {len(checker.warnings)} warnings")
    return 1 if checker.errors else 0


if __name__ == "__main__":
    sys.exit(main())
