"""Small HTTPS client for the user's alt account; no credential logging."""
import http.client
import json
import os
from pathlib import Path
import stat
from platform_files import read_private

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ['ROVE_STATE_ROOT']).resolve() if os.environ.get('ROVE_STATE_ROOT') else REPO_ROOT
ALLOWED_HOSTS = {"users.roblox.com", "games.roblox.com", "gamejoin.roblox.com", "apis.roblox.com",
                 "friends.roblox.com", "presence.roblox.com", "thumbnails.roblox.com",
                 "avatar.roblox.com", "inventory.roblox.com", "privatemessages.roblox.com",
                 "trades.roblox.com", "groups.roblox.com", "catalog.roblox.com", "economy.roblox.com"}


class SessionError(Exception):
    """Error messages in this module contain no request/response secrets."""


class RobloxSession:
    def __init__(self, *, cookie=None):
        if cookie is None:
            path = ROOT / "secrets/roblox-cookie.txt"
            try:
                cookie = read_private(path, 32768).decode('utf-8').strip()
            except (OSError, ValueError):
                raise SessionError("Cookie file must be a readable owner-only regular file") from None
        if not isinstance(cookie,str) or len(cookie)>32768:
            raise SessionError('Invalid account session')
        cookie=cookie.strip()
        if cookie.startswith(".ROBLOSECURITY="):
            cookie = cookie[len(".ROBLOSECURITY="):].rstrip(";")
        if not cookie or any(ord(c) < 33 or ord(c) > 126 or c == ";" for c in cookie):
            raise SessionError("Cookie file must contain only the cookie value")
        self._cookie = cookie
        self._csrf = {}

    def request(self, host, path, method="GET", payload=None, csrf_retry=False):
        if host not in ALLOWED_HOSTS or not path.startswith("/") or any(ord(c) < 32 for c in path):
            raise SessionError("Request destination is not allowed")
        if method not in {"GET", "POST"} and not (method == "DELETE" and host == "groups.roblox.com"):
            raise SessionError("Unsupported method")
        for attempt in range(2 if csrf_retry else 1):
            headers = {"Cookie": ".ROBLOSECURITY=" + self._cookie,
                       "Accept": "application/json", "User-Agent": "LocalRobloxResearch/1.0",
                       "Origin": "https://www.roblox.com", "Referer": "https://www.roblox.com/"}
            body = json.dumps(payload).encode() if payload is not None else None
            if body is not None:
                headers["Content-Type"] = "application/json"
            if host in self._csrf:
                headers["X-CSRF-TOKEN"] = self._csrf[host]
            connection = http.client.HTTPSConnection(host, timeout=20)
            try:
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                status = response.status
                token = response.getheader("x-csrf-token")
                challenge = bool(response.getheader("rblx-challenge-id"))
                content_type = response.getheader("content-type", "")
                raw = response.read(2 * 1024 * 1024 + 1)
            except Exception as error:
                raise SessionError("HTTPS request failed: " + type(error).__name__) from None
            finally:
                connection.close()
            if len(raw) > 2 * 1024 * 1024:
                raise SessionError("Response exceeded the size limit")
            if status == 403 and token and csrf_retry and attempt == 0 and not challenge:
                # Honor the server-issued anti-CSRF token once. Never solve or
                # evade an account challenge, and never follow a redirect.
                self._csrf[host] = token
                continue
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                value = None
            return {"http_status": status, "challenge_present": challenge,
                    "content_type": content_type, "data": value}
        raise SessionError("Request retry was exhausted")
