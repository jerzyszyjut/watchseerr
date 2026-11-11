"""Offline tests: canned pages and a fake Seerr, no network."""

import json
import tempfile
import unittest
from pathlib import Path

from watchseerr.config import Config, Source
from watchseerr.http import HTTPError
from watchseerr.letterboxd import Letterboxd
from watchseerr.seerr import Seerr
from watchseerr.serializd import Serializd
from watchseerr.sync import Syncer


def poster(slug, name):
    return (f'<div class="react-component" data-item-name="{name}" data-item-slug="{slug}" '
            f'data-item-link="/film/{slug}/" data-target-link="/film/{slug}/"></div>')


class FakeHTTP:
    """Answers GETs from a dict, records POSTs."""

    def __init__(self, pages):
        self.pages = pages
        self.posts = []

    def _get(self, path):
        if path not in self.pages:
            raise HTTPError(404, path)
        return self.pages[path]

    def get_text(self, path, params=None):
        return self._get(path)

    def get_json(self, path, params=None):
        v = self._get(path)
        return json.loads(v) if isinstance(v, str) else v

    def post_json(self, path, body):
        self.posts.append((path, body))
        return {"id": len(self.posts)}


LB = {
    "/me/watchlist/": poster("dune-part-two", "Dune: Part Two (2024)")
    + poster("chernobyl", "Chernobyl (2019)")
    + poster("no-tmdb", "Obscure (1931)")
    + '<li class="paginate-page"><a href="/me/watchlist/page/2/">2</a></li>',
    "/me/watchlist/page/2/": poster("the-matrix", "The Matrix (1999)"),
    "/film/dune-part-two/": '<meta property="og:title" content="Dune: Part Two (2024)">'
    '<a href="https://www.themoviedb.org/movie/693134/">TMDB</a>',
    "/film/chernobyl/": '<a href="https://www.themoviedb.org/tv/87108/">TMDB</a>',
    "/film/no-tmdb/": "<p>nothing</p>",
    "/film/the-matrix/": '<a href="https://www.themoviedb.org/movie/603/">TMDB</a>',
}

SZ = {
    "/user/me/watchlistpage_v2/1": {
        "items": [
            {"showId": 1399, "showName": "Game of Thrones", "seasonIds": [3627, 3628]},
            {"showId": 1396, "showName": "Breaking Bad", "seasonIds": []},
        ],
        "totalPages": 1,
    },
}

SEERR = {
    "/user": {"results": [{"id": 1, "username": "admin"}, {"id": 7, "displayName": "Leyku"}]},
    "/movie/693134": {"title": "Dune: Part Two"},
    # already in the library
    "/movie/603": {"title": "The Matrix", "mediaInfo": {"status": 5}},
    "/tv/87108": {"name": "Chernobyl", "seasons": [{"id": 1, "seasonNumber": 1}]},
    "/tv/1399": {
        "name": "Game of Thrones",
        "seasons": [{"id": 3624, "seasonNumber": 0}, {"id": 3627, "seasonNumber": 1},
                    {"id": 3628, "seasonNumber": 2}, {"id": 3629, "seasonNumber": 3}],
        # season 1 is downloaded, so only season 2 is still missing
        "mediaInfo": {"status": 4, "seasons": [{"seasonNumber": 1, "status": 5}]},
    },
    "/tv/1396": {
        "name": "Breaking Bad",
        "seasons": [{"id": 10, "seasonNumber": 0}, {"id": 11, "seasonNumber": 1},
                    {"id": 12, "seasonNumber": 2}],
        # season 1 already requested by someone else
        "mediaInfo": {"status": 2, "requests": [{"status": 1, "seasons": [{"seasonNumber": 1}]}]},
    },
}


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name) / "state.json"
        self.seerr_http = FakeHTTP(SEERR)

    def tearDown(self):
        self.dir.cleanup()

    def run_sync(self, sources, dry_run=False, max_requests=25):
        cfg = Config("http://seerr", "key", sources, self.state, max_requests=max_requests)
        s = Syncer(cfg, dry_run=dry_run,
                   seerr=Seerr("http://seerr", "key", client=FakeHTTP.__new__(FakeHTTP)),
                   letterboxd=Letterboxd({}, client=FakeHTTP(LB)),
                   serializd=Serializd(client=FakeHTTP(SZ)))
        s.seerr.http = self.seerr_http
        return s.run()

    def bodies(self):
        return [b for _, b in self.seerr_http.posts]

    def test_letterboxd(self):
        r = self.run_sync([Source("letterboxd", "me", seerr_user="leyku")])
        self.assertEqual(self.bodies(), [
            {"mediaType": "movie", "mediaId": 693134, "userId": 7},
            {"mediaType": "tv", "mediaId": 87108, "seasons": [1], "userId": 7},
        ])
        self.assertEqual(len(r["letterboxd:me"].requested), 2)

    def test_serializd_watchlisted_seasons(self):
        self.run_sync([Source("serializd", "me")])
        self.assertEqual(self.bodies(), [
            {"mediaType": "tv", "mediaId": 1399, "seasons": [2]},
            {"mediaType": "tv", "mediaId": 1396, "seasons": [2]},
        ])

    def test_serializd_all_seasons(self):
        self.run_sync([Source("serializd", "me", seasons="all")])
        self.assertEqual(self.bodies()[0], {"mediaType": "tv", "mediaId": 1399, "seasons": [2, 3]})

    def test_second_run_asks_for_nothing(self):
        self.run_sync([Source("letterboxd", "me")])
        n = len(self.seerr_http.posts)
        self.run_sync([Source("letterboxd", "me")])
        self.assertEqual(len(self.seerr_http.posts), n)
        # and the slug cache spared the film pages
        self.assertIn("dune-part-two", json.loads(self.state.read_text())["letterboxd"])

    def test_dry_run_changes_nothing(self):
        r = self.run_sync([Source("letterboxd", "me")], dry_run=True)
        self.assertEqual(self.seerr_http.posts, [])
        self.assertEqual(len(r["letterboxd:me"].requested), 2)
        self.assertFalse(self.state.exists())

    def test_initial_skip_takes_a_baseline(self):
        self.run_sync([Source("letterboxd", "me", initial="skip")])
        self.assertEqual(self.seerr_http.posts, [])
        self.run_sync([Source("letterboxd", "me", initial="skip")])
        self.assertEqual(self.seerr_http.posts, [])

    def test_budget(self):
        self.run_sync([Source("letterboxd", "me")], max_requests=1)
        self.assertEqual(len(self.seerr_http.posts), 1)

    def test_unknown_user_fails_the_source_only(self):
        r = self.run_sync([Source("letterboxd", "me", seerr_user="nobody"),
                           Source("serializd", "me")])
        self.assertTrue(r["letterboxd:me"].failed)
        self.assertEqual(len(r["serializd:me"].requested), 2)


if __name__ == "__main__":
    unittest.main()
