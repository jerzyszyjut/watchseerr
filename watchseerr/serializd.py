"""Serializd: the JSON API its own web app uses (unofficial, read-only here).

Public profiles need no login. Show ids are TMDB ids and a watchlist entry
names the TMDB *season* ids that were added, so a watchlisted season, not
the whole series, is what gets requested.
"""

from __future__ import annotations

from typing import Iterator

from .http import Client
from .models import Item

BASE = "https://serializd.onrender.com/api"
HEADERS = {
    # The API rejects requests without the web app's id.
    "X-Requested-With": "serializd_vercel",
    "Accept": "application/json",
    "Origin": "https://www.serializd.com",
    "Referer": "https://www.serializd.com/",
}
MAX_PAGES = 200


class SerializdError(Exception):
    pass


class Serializd:
    def __init__(self, client: Client | None = None):
        # Hosted on Render: the first request after a quiet spell can take
        # half a minute while the instance wakes up.
        self.http = client or Client(BASE, HEADERS, delay=0.5, timeout=90)

    def items(self, user: str) -> Iterator[Item]:
        page, total = 1, 1
        while page <= min(total, MAX_PAGES):
            data = self.http.get_json(f"/user/{user}/watchlistpage_v2/{page}",
                                      {"sort_by": "date_added_desc"})
            if "items" not in data:
                raise SerializdError(f"serializd user {user!r}: {data.get('message', data)}")
            for it in data["items"]:
                yield Item("tv", int(it["showId"]), it.get("showName") or str(it["showId"]),
                           [int(s) for s in it.get("seasonIds") or []] or None)
            total = data.get("totalPages") or 0
            page += 1
