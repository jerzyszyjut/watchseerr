"""Letterboxd: no public API, so this reads the HTML a browser would.

A watchlist (or list) page carries the films' slugs; each film's own page
links to TMDB, and that link says both the id and whether TMDB files it as a
film or a series (Letterboxd also lists miniseries such as Chernobyl, whose
`data-tmdb-id` is empty but whose link is themoviedb.org/tv/87108).
Slug -> TMDB is cached forever: slugs do not change meaning.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Iterator

from .http import Client, HTTPError
from .models import Item

log = logging.getLogger(__name__)

BASE = "https://letterboxd.com"
SLUG = re.compile(r'data-(?:item-slug|film-slug)="([^"]+)"')
NAME = re.compile(r'data-item-slug="([^"]+)"[^>]*?data-item-(?:full-display-)?name="([^"]*)"'
                  r'|data-item-name="([^"]*)"[^>]*?data-item-slug="([^"]+)"')
TMDB = re.compile(r"themoviedb\.org/(movie|tv)/(\d+)")
TITLE = re.compile(r'<meta property="og:title" content="([^"]*)"')
LAST_PAGE = re.compile(r'/page/(\d+)/"')

MAX_PAGES = 200  # 28 films a page: 5600 films


class Letterboxd:
    def __init__(self, cache: dict[str, list], client: Client | None = None):
        # Letterboxd streams its pages slowly (5-10 s for a film page), which
        # is pacing enough; the delay only matters for cached-page bursts.
        self.http = client or Client(BASE, {"Accept": "text/html"}, delay=0.5)
        self.cache = cache  # slug -> [media_type, tmdb_id, title] | [None, None, title]

    def list_path(self, user: str, list_slug: str | None) -> str:
        if not list_slug or list_slug == "watchlist":
            return f"/{user}/watchlist/"
        return f"/{user}/list/{list_slug}/"

    def slugs(self, user: str, list_slug: str | None = None) -> Iterator[tuple[str, str]]:
        """(slug, display name) for every film on the list, in page order."""
        path = self.list_path(user, list_slug)
        page, last = 1, 1
        while page <= min(last, MAX_PAGES):
            text = self.http.get_text(path if page == 1 else f"{path}page/{page}/")
            names = {}
            for m in NAME.finditer(text):
                slug, name = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
                names[slug] = html.unescape(name)
            found = list(dict.fromkeys(SLUG.findall(text)))
            if not found:
                break
            for slug in found:
                yield slug, names.get(slug, slug)
            pages = [int(p) for p in LAST_PAGE.findall(text)]
            last = max(pages + [page])
            page += 1

    def resolve(self, slug: str) -> tuple[str | None, int | None, str]:
        if slug in self.cache:
            t, i, title = self.cache[slug]
            return t, i, title
        text = self.http.get_text(f"/film/{slug}/")
        m = TMDB.search(text)
        t = TITLE.search(text)
        title = html.unescape(t.group(1)) if t else slug
        result = (m.group(1), int(m.group(2)), title) if m else (None, None, title)
        self.cache[slug] = list(result)
        return result

    def items(self, user: str, list_slug: str | None = None) -> Iterator[Item]:
        for slug, name in self.slugs(user, list_slug):
            try:
                media_type, tmdb_id, title = self.resolve(slug)
            except HTTPError as e:
                log.warning("letterboxd: could not read /film/%s/: %s", slug, e)
                continue
            if tmdb_id is None or media_type is None:
                log.warning("letterboxd: %s has no TMDB link, skipped", name)
                continue
            yield Item(media_type, tmdb_id, title)
