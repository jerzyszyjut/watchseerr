from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Item:
    """One thing a watchlist wants.

    `season_ids` are TMDB *season* ids (Serializd watchlists individual
    seasons); None means "every regular season".
    """

    media_type: str  # "movie" | "tv"
    tmdb_id: int
    title: str
    season_ids: list[int] | None = field(default=None)

    @property
    def key(self) -> str:
        return f"{self.media_type}:{self.tmdb_id}"
