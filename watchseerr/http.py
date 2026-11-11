"""A small HTTP client on urllib: retries, backoff, and per-host pacing."""

from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import __version__

log = logging.getLogger(__name__)

USER_AGENT = f"watchseerr/{__version__} (+https://github.com/jerzyszyjut/watchseerr)"


class HTTPError(Exception):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.status = status
        self.url = url
        self.body = body


class Client:
    """Pacing keeps scrapers polite: at most one request per `delay` seconds."""

    def __init__(self, base: str = "", headers: dict[str, str] | None = None,
                 delay: float = 0.0, timeout: float = 60.0, retries: int = 3):
        self.base = base.rstrip("/")
        self.headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})}
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self._last = 0.0

    def _pace(self) -> None:
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def request(self, method: str, path: str, params: dict[str, Any] | None = None,
                body: Any = None) -> tuple[int, str]:
        url = path if path.startswith("http") else self.base + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        data = None
        headers = dict(self.headers)
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        last: HTTPError | None = None
        for attempt in range(self.retries):
            self._pace()
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    return r.status, raw.decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                raw = e.read()
                if e.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                text = raw.decode("utf-8", "replace")
                last = HTTPError(e.code, url, text)
                if e.code == 429:
                    time.sleep(float(e.headers.get("Retry-After") or 5 * (attempt + 1)))
                    continue
                if e.code < 500:
                    raise last from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = HTTPError(-1, url, str(e))
            log.debug("retrying %s %s (%s)", method, url, last)
            time.sleep(2 * (attempt + 1))
        assert last is not None
        raise last

    def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        return self.request("GET", path, params)[1]

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return json.loads(self.get_text(path, params))

    def post_json(self, path: str, body: Any) -> Any:
        text = self.request("POST", path, body=body)[1]
        return json.loads(text) if text else None
