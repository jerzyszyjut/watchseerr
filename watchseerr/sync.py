"""One pass over every source: read the watchlist, ask Seerr what it lacks,
request that, remember it.

The state file is what makes a decision stick. Anything watchseerr has
requested once is never requested again, so declining it in Seerr (or
deleting it) is final until it is taken off the watchlist and put back.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .config import Config, Source
from .http import HTTPError
from .letterboxd import Letterboxd
from .models import Item
from .seerr import Seerr, SeerrError
from .serializd import Serializd

log = logging.getLogger(__name__)


class State:
    VERSION = 1

    def __init__(self, path: Path):
        self.path = path
        data: dict[str, Any] = {}
        if path.exists():
            data = json.loads(path.read_text() or "{}")
        # key ("movie:603" / "tv:1399") -> true, or the season numbers asked for
        self.requested: dict[str, Any] = data.get("requested", {})
        # letterboxd slug -> [media_type, tmdb_id, title]
        self.letterboxd: dict[str, list] = data.get("letterboxd", {})
        # source ids already seen once, and the items that were on a list
        # with initial = "skip" when it was first seen
        self.sources: list[str] = data.get("sources", [])
        self.baseline: set[str] = set(data.get("baseline", []))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": self.VERSION, "requested": self.requested,
                                   "letterboxd": self.letterboxd, "sources": self.sources,
                                   "baseline": sorted(self.baseline)},
                                  indent=1, sort_keys=True))
        os.replace(tmp, self.path)

    def asked_seasons(self, key: str) -> set[int]:
        v = self.requested.get(key)
        return set(v) if isinstance(v, list) else set()

    def asked(self, item: Item) -> bool:
        return item.media_type == "movie" and item.key in self.requested

    def record(self, item: Item, seasons: list[int] | None) -> None:
        if item.media_type == "movie":
            self.requested[item.key] = True
        else:
            self.requested[item.key] = sorted(self.asked_seasons(item.key) | set(seasons or []))


@dataclass
class Report:
    requested: list[str] = field(default_factory=list)
    skipped: int = 0
    failed: list[str] = field(default_factory=list)


class Syncer:
    def __init__(self, cfg: Config, dry_run: bool = False,
                 seerr: Seerr | None = None, letterboxd: Letterboxd | None = None,
                 serializd: Serializd | None = None):
        self.cfg = cfg
        self.dry_run = dry_run
        self.state = State(cfg.state_file)
        self.seerr = seerr or Seerr(cfg.seerr_url, cfg.seerr_api_key)
        self.letterboxd = letterboxd or Letterboxd(self.state.letterboxd)
        self.letterboxd.cache = self.state.letterboxd
        self.serializd = serializd or Serializd()
        self.budget = cfg.max_requests
        self._users: dict[Any, int | None] = {}

    def user_id(self, who: str | int | None) -> int | None:
        if who is None:
            return None
        if who not in self._users:
            self._users[who] = self.seerr.find_user(who)
        return self._users[who]

    def items(self, src: Source) -> Iterable[Item]:
        if src.type == "letterboxd":
            return self.letterboxd.items(src.user, src.list)
        items = self.serializd.items(src.user)
        if src.seasons == "all":
            return (Item(i.media_type, i.tmdb_id, i.title) for i in items)
        return items

    def run(self) -> dict[str, Report]:
        reports = {}
        for src in self.cfg.sources:
            report = reports[src.id] = Report()
            try:
                self.sync_source(src, report)
            except (HTTPError, SeerrError, OSError, ValueError, KeyError) as e:
                log.error("%s: %s", src.id, e)
                report.failed.append(str(e))
            finally:
                if not self.dry_run:
                    self.state.save()
        return reports

    def sync_source(self, src: Source, report: Report) -> None:
        user_id = self.user_id(src.seerr_user)
        first = src.id not in self.state.sources
        baseline = first and src.initial == "skip"
        for item in self.items(src):
            if self.state.asked(item):
                report.skipped += 1
                continue
            if baseline:
                # Remember everything on the list today without asking for it.
                if not self.dry_run:
                    self.state.baseline.add(item.key)
                report.skipped += 1
                continue
            if item.key in self.state.baseline:
                report.skipped += 1
                continue
            plan = self.seerr.plan(item.media_type, item.tmdb_id, item.season_ids)
            seasons = plan.seasons
            if plan.wanted and item.media_type == "tv":
                seasons = [n for n in plan.seasons or [] if n not in self.state.asked_seasons(item.key)]
                if not seasons:
                    plan.wanted, plan.reason = False, "those seasons were requested before"
            if not plan.wanted:
                log.debug("%s: %s — %s", src.id, plan.title, plan.reason)
                report.skipped += 1
                continue
            label = plan.title + (f" (seasons {', '.join(map(str, seasons))})" if seasons else "")
            if self.budget <= 0:
                log.info("%s: %s — over max_requests_per_run, next run", src.id, label)
                continue
            if self.dry_run:
                log.info("%s: would request %s", src.id, label)
            else:
                try:
                    self.seerr.request(item.media_type, item.tmdb_id, seasons, user_id)
                except HTTPError as e:
                    # 409: someone requested it between plan() and now; 403:
                    # quota or permissions. Neither should stop the run.
                    if e.status in (403, 409):
                        log.warning("%s: %s — Seerr said %s: %s", src.id, label, e.status,
                                    e.body[:160])
                        report.failed.append(f"{label}: HTTP {e.status}")
                        if e.status == 409:
                            self.state.record(item, seasons)
                        continue
                    raise
                log.info("%s: requested %s", src.id, label)
                self.state.record(item, seasons)
            self.budget -= 1
            report.requested.append(label)
        if first and not self.dry_run:
            self.state.sources.append(src.id)
