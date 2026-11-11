from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from . import __version__
from .config import ConfigError, load
from .sync import Syncer


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="watchseerr",
        description="Request the films and series on Letterboxd and Serializd watchlists in Seerr.")
    p.add_argument("-c", "--config", default=os.environ.get("WATCHSEERR_CONFIG", "watchseerr.toml"),
                   help="TOML config (default: $WATCHSEERR_CONFIG or ./watchseerr.toml)")
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="show what would be requested; change nothing")
    p.add_argument("--daemon", action="store_true",
                   help="keep running, one pass every `interval` (default: one pass and exit)")
    p.add_argument("-v", "--verbose", action="store_true", help="also log what was skipped and why")
    p.add_argument("--version", action="version", version=f"watchseerr {__version__}")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s" if os.environ.get("INVOCATION_ID")
                        else "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        cfg = load(args.config)
    except (ConfigError, OSError) as e:
        logging.error("config: %s", e)
        return 2

    while True:
        reports = Syncer(cfg, dry_run=args.dry_run).run()
        failed = False
        for sid, r in reports.items():
            verb = "would request" if args.dry_run else "requested"
            logging.info("%s: %s %d, skipped %d%s", sid, verb, len(r.requested), r.skipped,
                         f", {len(r.failed)} problem(s)" if r.failed else "")
            failed |= bool(r.failed)
        if not args.daemon:
            return 1 if failed else 0
        time.sleep(cfg.interval)


if __name__ == "__main__":
    sys.exit(main())
