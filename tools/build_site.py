#!/usr/bin/env python3
"""Gurevic Real Estate — static site build (Jinja2 templates × 7 languages).

    python tools/build_site.py                      # full build into the repo root
    python tools/build_site.py --out ../site-test   # private folder (static dirs are copied)
    python tools/build_site.py --lang ru,en         # only these languages (partial build)
    python tools/build_site.py --only buy/,en/buy/  # only pages whose path starts with a prefix
    python tools/build_site.py --only index.html    # only the root-language home ("/" too; Git Bash mangles "/")
    python tools/build_site.py --check              # render everything, report i18n gaps, write nothing
    python tools/build_site.py --strict             # fail on missing ru/en keys and missing assets

Partial builds (--lang/--only) never delete files and merge into the existing manifest.
See docs/ARCHITECTURE.md.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from sitegen.core import build  # noqa: E402


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):  # кириллица в консоли Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Build the static site from src/ + i18n/ + js/data.js")
    ap.add_argument("--out", default=ROOT, help="output directory (default: repo root)")
    ap.add_argument("--lang", default="", help="comma-separated subset of languages, e.g. ru,en")
    ap.add_argument("--strict", action="store_true",
                    help="fail on i18n keys missing in ru/en, ru keys absent in en, missing assets")
    ap.add_argument("--only", default="", help="comma-separated output path prefixes, e.g. buy/,en/invest/; '/' or 'index.html' = root home only")
    ap.add_argument("--check", action="store_true",
                    help="render without writing; print missing i18n keys per language (exit 1 on problems with --strict)")
    ap.add_argument("-q", "--quiet", action="store_true", help="errors only")
    args = ap.parse_args(argv)
    langs = [x.strip() for x in args.lang.split(",") if x.strip()] or None
    return build(ROOT, out=args.out, langs=langs, strict=args.strict, only=args.only or None,
                 check=args.check, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
