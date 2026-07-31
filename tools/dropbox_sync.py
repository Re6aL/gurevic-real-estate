#!/usr/bin/env python3
"""Sync listing images from Dropbox folders into the public static site.

Expected Dropbox layout:
  <DROPBOX_MEDIA_ROOT>/<Object ID>/00-cover.jpg, 01.jpg, ...

The script uses a short-lived Dropbox access token obtained from a refresh token.
No credential or Dropbox URL is written into js/data.js or committed to git.
"""

import argparse
import base64
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:
    Image = ImageOps = None
    UnidentifiedImageError = OSError


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(PROJECT_ROOT, "js", "data.js")
IMAGE_ROOT = os.path.join(PROJECT_ROOT, "img", "listings")
MAX_IMAGES = 8
MAX_BYTES = 15 * 1024 * 1024
MAX_PUBLIC_BYTES = 900 * 1024
MAX_PUBLIC_SIDE = 2200
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def fail(message):
    raise RuntimeError(message)


def request_json(url, payload, headers=None):
    headers = headers or {}
    content_type = headers.get("Content-Type", "")
    if content_type == "application/json":
        data = json.dumps(payload).encode()
    elif isinstance(payload, dict):
        data = urllib.parse.urlencode(payload).encode()
    else:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        fail(f"Dropbox API returned HTTP {exc.code}: {detail}")


def access_token():
    direct = os.environ.get("DROPBOX_ACCESS_TOKEN")
    if direct:
        return direct
    key = os.environ.get("DROPBOX_APP_KEY")
    secret = os.environ.get("DROPBOX_APP_SECRET")
    refresh = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if not all((key, secret, refresh)):
        fail("Set DROPBOX_APP_KEY, DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN in GitHub Secrets.")
    token = request_json(
        "https://api.dropboxapi.com/oauth2/token",
        {"grant_type": "refresh_token", "refresh_token": refresh},
        {"Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode()},
    )
    return token["access_token"]


def api(token, endpoint, payload):
    return request_json(
        f"https://api.dropboxapi.com/2/{endpoint}", payload,
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )


def list_folder(token, path):
    result = api(token, "files/list_folder", {"path": path, "recursive": False, "include_deleted": False})
    entries = result.get("entries", [])
    while result.get("has_more"):
        result = api(token, "files/list_folder/continue", {"cursor": result["cursor"]})
        entries.extend(result.get("entries", []))
    return entries


def natural_key(value):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def load_listings():
    text = open(DATA_JS, encoding="utf-8").read()
    match = re.search(r"const LISTINGS\s*=\s*(\[.*?\]);\s*$", text, flags=re.S)
    if not match:
        fail("Could not read LISTINGS from js/data.js")
    return text, match, json.loads(match.group(1))


def write_listings(source, match, listings):
    body = json.dumps(listings, ensure_ascii=False, indent=2)
    updated = source[:match.start(1)] + body + source[match.end(1):]
    with open(DATA_JS, "w", encoding="utf-8") as target:
        target.write(updated)


def is_supported_image(data):
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    )


def optimize_for_web(data, path, destination):
    if Image is None:
        fail("Pillow is required for public image optimization.")
    try:
        # A JPEG that already meets the public size limit is publication-ready.
        # Validate it, but keep the realtor's original encoding byte-for-byte.
        if data.startswith(b"\xff\xd8\xff") and len(data) <= MAX_PUBLIC_BYTES:
            with Image.open(io.BytesIO(data)) as source:
                source.verify()
            with open(destination, "wb") as output:
                output.write(data)
            return len(data)

        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((MAX_PUBLIC_SIDE, MAX_PUBLIC_SIDE), Image.Resampling.LANCZOS)
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                image = flattened
            else:
                image = image.convert("RGB")

            encoded = b""
            for quality in (84, 80, 76, 72, 68, 64, 60):
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
                encoded = buffer.getvalue()
                if len(encoded) <= MAX_PUBLIC_BYTES:
                    break

            if len(encoded) > MAX_PUBLIC_BYTES:
                ratio = min(0.92, math.sqrt(MAX_PUBLIC_BYTES / len(encoded)) * 0.94)
                resized = image.resize(
                    (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                    Image.Resampling.LANCZOS,
                )
                buffer = io.BytesIO()
                resized.save(buffer, "JPEG", quality=68, optimize=True, progressive=True)
                encoded = buffer.getvalue()

        with open(destination, "wb") as output:
            output.write(encoded)
        return len(encoded)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        fail(f"{path}: image cannot be decoded ({exc})")


def download_file(token, path, destination):
    req = urllib.request.Request("https://content.dropboxapi.com/2/files/download", method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Dropbox-API-Arg", json.dumps({"path": path}))
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            content_type = response.headers.get_content_type().lower()
            if not (content_type.startswith("image/") or content_type == "application/octet-stream"):
                fail(f"{path}: unsupported content type {content_type}")
            data = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        fail(f"{path}: Dropbox download failed ({exc.code}: {detail})")
    if len(data) > MAX_BYTES:
        print(f"[warn] {path}: image is larger than {MAX_BYTES // 1024 // 1024} MB; skipped")
        return False
    if not is_supported_image(data):
        fail(f"{path}: file contents are not a supported JPEG, PNG or WebP image")
    return optimize_for_web(data, path, destination)


def sync(root, dry_run=False):
    token = access_token()
    source, match, listings = load_listings()
    folders = {
        item["name"].casefold(): item["path_display"]
        for item in list_folder(token, root)
        if item.get(".tag") == "folder"
    }
    changed, copied = 0, 0
    for listing in listings:
        object_id = str(listing.get("objectId") or "").strip()
        folder = folders.get(object_id.casefold())
        if not folder:
            continue
        files = [
            item for item in list_folder(token, folder)
            if item.get(".tag") == "file" and os.path.splitext(item["name"])[1].lower() in IMAGE_EXTENSIONS
        ]
        files.sort(key=lambda item: natural_key(item["name"]))
        if not files:
            print(f"[warn] {object_id}: no supported images in Dropbox folder")
            continue
        listing_id = listing["id"]
        public_paths = []
        with tempfile.TemporaryDirectory(prefix="gurevic-dropbox-") as staging:
            for item in files:
                if len(public_paths) >= MAX_IMAGES:
                    break
                index = len(public_paths) + 1
                filename = f"{index:02d}.jpg"
                if not download_file(token, item["path_display"], os.path.join(staging, filename)):
                    continue
                public_paths.append(f"img/listings/{listing_id}/{filename}")
            if not public_paths:
                print(f"[warn] {object_id}: no usable images after validation")
                continue
            if not dry_run:
                target = os.path.join(IMAGE_ROOT, listing_id)
                os.makedirs(target, exist_ok=True)
                for old in os.listdir(target):
                    if os.path.splitext(old)[1].lower() in IMAGE_EXTENSIONS:
                        os.remove(os.path.join(target, old))
                for filename in os.listdir(staging):
                    shutil.copy2(os.path.join(staging, filename), os.path.join(target, filename))
        if listing.get("images") != public_paths:
            listing["images"] = public_paths
            listing["photos"] = len(public_paths)
            changed += 1
        copied += len(public_paths)
        print(f"[ok] {object_id}: {len(public_paths)} image(s)")
    if changed and not dry_run:
        write_listings(source, match, listings)
    print(f"Dropbox: folders {len(folders)}, updated listings {changed}, copied images {copied}")


def main():
    parser = argparse.ArgumentParser(description="Sync public listing images from Dropbox")
    parser.add_argument("--root", default=os.environ.get("DROPBOX_MEDIA_ROOT"), help="Dropbox folder containing Object ID subfolders")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.root:
        sys.exit("Set DROPBOX_MEDIA_ROOT, for example /Website photos")
    try:
        sync(args.root, args.dry_run)
    except RuntimeError as exc:
        sys.exit(f"[dropbox] {exc}")


if __name__ == "__main__":
    main()
