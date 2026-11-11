"""The part of the Seerr API this needs: who, what is already there, request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .http import Client, HTTPError

# server/constants/media.ts
MEDIA_PENDING, MEDIA_PROCESSING, MEDIA_PARTIAL, MEDIA_AVAILABLE, MEDIA_BLOCKLISTED = 2, 3, 4, 5, 6
REQ_PENDING, REQ_APPROVED, REQ_DECLINED, REQ_FAILED, REQ_COMPLETED = 1, 2, 3, 4, 5

# Present, on its way, or deliberately blocked: nothing to ask for.
TAKEN_MEDIA = {MEDIA_PENDING, MEDIA_PROCESSING, MEDIA_PARTIAL, MEDIA_AVAILABLE, MEDIA_BLOCKLISTED}
# A declined or failed request is not a live one; whether to ask again after
# a decline is decided by the sync state, not here.
LIVE_REQUESTS = {REQ_PENDING, REQ_APPROVED, REQ_COMPLETED}


class SeerrError(Exception):
    pass


@dataclass
class Plan:
    """What Seerr still lacks for one item: nothing, the film, or these seasons."""

    title: str
    wanted: bool
    seasons: list[int] | None = None  # tv only
    reason: str = ""


class Seerr:
    def __init__(self, url: str, api_key: str, client: Client | None = None):
        self.http = client or Client(url.rstrip("/") + "/api/v1",
                                     {"X-Api-Key": api_key, "Accept": "application/json"},
                                     timeout=30)

    def status(self) -> dict[str, Any]:
        return self.http.get_json("/status")

    def find_user(self, who: str | int) -> int:
        """A Seerr user id from an id, username, display name, email or
        Jellyfin/Plex name, compared case-insensitively."""
        if isinstance(who, int) or str(who).isdigit():
            return int(who)
        data = self.http.get_json("/user", {"take": 1000})
        want = str(who).casefold()
        for u in data.get("results", []):
            names = [u.get(k) for k in ("username", "displayName", "email",
                                        "jellyfinUsername", "plexUsername")]
            if want in {str(n).casefold() for n in names if n}:
                return int(u["id"])
        raise SeerrError(f"no Seerr user called {who!r}")

    def plan(self, media_type: str, tmdb_id: int, season_ids: list[int] | None = None) -> Plan:
        try:
            d = self.http.get_json(f"/{media_type}/{tmdb_id}")
        except HTTPError as e:
            if e.status == 404:
                return Plan(str(tmdb_id), False, reason="not on TMDB")
            raise
        title = d.get("title") or d.get("name") or str(tmdb_id)
        info = d.get("mediaInfo") or {}
        status = info.get("status")
        requests = [r for r in info.get("requests") or [] if r.get("status") in LIVE_REQUESTS]

        if media_type == "movie":
            if status in TAKEN_MEDIA:
                return Plan(title, False, reason=f"media status {status}")
            if requests:
                return Plan(title, False, reason="already requested")
            # Unreleased films are requested too: Radarr waits for a
            # release on its own.
            return Plan(title, True)

        if status == MEDIA_BLOCKLISTED:
            return Plan(title, False, reason="blocklisted")
        seasons = [s for s in d.get("seasons") or [] if s.get("seasonNumber") is not None]
        if season_ids:
            by_id = {s.get("id"): s["seasonNumber"] for s in seasons}
            numbers = sorted({by_id[i] for i in season_ids if i in by_id})
            if not numbers:
                # A season Serializd knows and TMDB no longer lists (merged,
                # renumbered): fall back to the whole show.
                numbers = sorted(s["seasonNumber"] for s in seasons if s["seasonNumber"] > 0)
        else:
            numbers = sorted(s["seasonNumber"] for s in seasons if s["seasonNumber"] > 0)
        have = {s["seasonNumber"] for s in info.get("seasons") or []
                if s.get("status") in TAKEN_MEDIA}
        for r in requests:
            have |= {s["seasonNumber"] for s in r.get("seasons") or []}
        missing = [n for n in numbers if n not in have]
        if not missing:
            return Plan(title, False, reason="every wanted season present or requested")
        return Plan(title, True, seasons=missing)

    def request(self, media_type: str, tmdb_id: int, seasons: list[int] | None,
                user_id: int | None) -> dict[str, Any]:
        body: dict[str, Any] = {"mediaType": media_type, "mediaId": tmdb_id}
        if media_type == "tv":
            body["seasons"] = seasons or "all"
        if user_id is not None:
            body["userId"] = user_id
        return self.http.post_json("/request", body)
