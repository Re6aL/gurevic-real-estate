#!/usr/bin/env python3
"""One-time local OAuth helper for a Dropbox refresh token.

Set DROPBOX_APP_KEY and DROPBOX_APP_SECRET only in the current terminal, run this
script, approve read-only access in the browser, then copy the printed refresh
token directly into GitHub Secrets. The token is never saved by this script.
"""

import base64
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer


APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
HOST, PORT = "127.0.0.1", 8765
REDIRECT_URI = f"http://{HOST}:{PORT}/callback"
STATE = secrets.token_urlsafe(24)
result = {"code": None, "error": None}


class Callback(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - method name is prescribed by BaseHTTPRequestHandler
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if urllib.parse.urlparse(self.path).path != "/callback" or query.get("state", [""])[0] != STATE:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid Dropbox OAuth response.")
            result["error"] = "Invalid OAuth response or state mismatch."
            return
        if "error" in query:
            result["error"] = query["error"][0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Dropbox authorization was declined. You may close this page.")
            return
        result["code"] = query.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Dropbox connected. Return to the terminal; you may close this page.")

    def log_message(self, *_):
        pass


def exchange(code):
    credentials = base64.b64encode(f"{APP_KEY}:{APP_SECRET}".encode()).decode()
    payload = urllib.parse.urlencode({
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }).encode()
    request = urllib.request.Request("https://api.dropboxapi.com/oauth2/token", data=payload, method="POST")
    request.add_header("Authorization", f"Basic {credentials}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    if not APP_KEY or not APP_SECRET:
        sys.exit("Set DROPBOX_APP_KEY and DROPBOX_APP_SECRET in this terminal before running this helper.")
    params = urllib.parse.urlencode({
        "client_id": APP_KEY,
        "response_type": "code",
        "token_access_type": "offline",
        "redirect_uri": REDIRECT_URI,
        "state": STATE,
    })
    url = f"https://www.dropbox.com/oauth2/authorize?{params}"
    print("Opening Dropbox authorization in your browser...")
    print("If it does not open, visit this URL:", url)
    webbrowser.open(url)
    server = HTTPServer((HOST, PORT), Callback)
    while not result["code"] and not result["error"]:
        server.handle_request()
    if result["error"]:
        sys.exit(f"Dropbox authorization failed: {result['error']}")
    tokens = exchange(result["code"])
    refresh = tokens.get("refresh_token")
    if not refresh:
        sys.exit("Dropbox did not return a refresh token. Check token_access_type=offline and the app settings.")
    print("\nAdd this value as the GitHub secret DROPBOX_REFRESH_TOKEN:\n")
    print(refresh)
    print("\nDo not save it in a project file or send it in chat.")


if __name__ == "__main__":
    main()
