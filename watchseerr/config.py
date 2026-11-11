from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    pass


@dataclass
class Source:
    type: str  # "letterboxd" | "serializd"
    user: str
    list: str | None = None  # letterboxd: a list slug instead of the watchlist
    seasons: str = "watchlisted"  # serializd: "watchlisted" | "all"
    seerr_user: str | int | None = None  # request as this Seerr user
    initial: str = "request"  # first sight of a source: "request" | "skip"

    @property
    def id(self) -> str:
        return f"{self.type}:{self.user}" + (f"/{self.list}" if self.list else "")


@dataclass
class Config:
    seerr_url: str
    seerr_api_key: str
    sources: list[Source]
    state_file: Path
    interval: int = 6 * 3600
    max_requests: int = 25
    extra: dict[str, Any] = field(default_factory=dict)


def parse_duration(value: str | int) -> int:
    if isinstance(value, int):
        return value
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", value)
    if not m:
        raise ConfigError(f"bad duration {value!r} (use e.g. 90s, 30m, 6h, 1d)")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def default_state_file() -> Path:
    # systemd's StateDirectory= first, then XDG.
    if d := os.environ.get("STATE_DIRECTORY"):
        return Path(d.split(":")[0]) / "state.json"
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state"
    return Path(base) / "watchseerr/state.json"


def read_api_key(seerr: dict[str, Any]) -> str:
    """Order: WATCHSEERR_SEERR_API_KEY, api_key_file, a systemd credential
    called seerr-api-key, api_key in the file (discouraged)."""
    if key := os.environ.get("WATCHSEERR_SEERR_API_KEY"):
        return key.strip()
    if path := seerr.get("api_key_file"):
        return Path(path).read_text().strip()
    if creds := os.environ.get("CREDENTIALS_DIRECTORY"):
        p = Path(creds) / "seerr-api-key"
        if p.exists():
            return p.read_text().strip()
    if key := seerr.get("api_key"):
        return str(key).strip()
    raise ConfigError("no Seerr API key: set WATCHSEERR_SEERR_API_KEY or seerr.api_key_file")


def load(path: str | Path) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    seerr = raw.get("seerr") or {}
    url = os.environ.get("WATCHSEERR_SEERR_URL") or seerr.get("url")
    if not url:
        raise ConfigError("seerr.url is required")
    sources = []
    for i, s in enumerate(raw.get("sources") or []):
        s = dict(s)
        if s.pop("enabled", True) is False:
            continue
        t = s.get("type")
        if t not in ("letterboxd", "serializd"):
            raise ConfigError(f"sources[{i}]: type must be letterboxd or serializd, not {t!r}")
        if not s.get("user"):
            raise ConfigError(f"sources[{i}]: user is required")
        if s.get("seasons", "watchlisted") not in ("watchlisted", "all"):
            raise ConfigError(f"sources[{i}]: seasons must be watchlisted or all")
        if s.get("initial", "request") not in ("request", "skip"):
            raise ConfigError(f"sources[{i}]: initial must be request or skip")
        unknown = set(s) - set(Source.__dataclass_fields__)
        if unknown:
            raise ConfigError(f"sources[{i}]: unknown keys {sorted(unknown)}")
        sources.append(Source(**s))
    if not sources:
        raise ConfigError("no [[sources]] configured")
    return Config(
        seerr_url=url,
        seerr_api_key=read_api_key(seerr),
        sources=sources,
        state_file=Path(raw["state_file"]) if raw.get("state_file") else default_state_file(),
        interval=parse_duration(raw.get("interval", "6h")),
        max_requests=int(raw.get("max_requests_per_run", 25)),
    )
