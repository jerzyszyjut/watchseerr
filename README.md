# watchseerr

Put a film on your **Letterboxd** watchlist, or a series on your **Serializd**
watchlist, and it shows up as a request in **Seerr** (the merged
Jellyseerr/Overseerr). Seerr then sends it to Radarr or Sonarr as usual,
with its approval rules, quotas and notifications.

- **Letterboxd:** watchlists and ordinary lists. Each film is matched by its
  TMDB id, taken from the film's own Letterboxd page, never by title.
  Miniseries that Letterboxd files as films (e.g. *Chernobyl*) are requested
  as series.
- **Serializd:** watchlists, season by season. If you watchlist season 3,
  you get season 3, not the whole show.
- **Several people:** each list can be requested as a different Seerr user.
- **Polite:** it skips anything Seerr already has, has requested, or has
  blocklisted. A declined request is never asked for again.
- **Small:** a single Python package using only the standard library. No
  browser, no database, no web UI.

## How it works

Each pass does this for every source:

1. Read the watchlist.
   - Letterboxd has no public API, so watchseerr reads the same HTML pages a
     browser would.
   - Serializd is read through the JSON API its web app uses. Public profiles
     need no login.
2. Look the title up in Seerr (`GET /api/v1/movie/{id}` or `/tv/{id}`) and
   work out what is missing: the film, or the wanted seasons that are neither
   available nor already requested.
3. Request what is missing (`POST /api/v1/request`), optionally on behalf of
   a Seerr user.
4. Remember the request in a state file, so the next pass, or a decision made
   in Seerr, sticks.

Letterboxd serves its film pages slowly, taking 5–10 seconds each. Every film
is therefore resolved once and cached for good. The first pass over a long
watchlist can take a while, and later passes take seconds.

## Install

### NixOS

```nix
# flake.nix
inputs.watchseerr.url = "github:jerzyszyjut/watchseerr";

# configuration.nix
{ inputs, ... }: {
  imports = [ inputs.watchseerr.nixosModules.default ];
  services.watchseerr = {
    enable = true;
    seerrUrl = "http://127.0.0.1:5055";
    apiKeyFile = "/run/secrets/seerr-api-key";   # sops-nix, agenix, or a root-only file
    interval = "hourly";
    settings.sources = [
      { type = "letterboxd"; user = "alice"; seerr_user = "alice"; }
      { type = "serializd";  user = "alice"; seerr_user = "alice"; }
    ];
  };
}
```

The service runs as a `DynamicUser`, keeps its state in
`/var/lib/watchseerr`, and reads the key as a systemd credential.

### Docker

```sh
docker build -t watchseerr .
docker run -d --name watchseerr \
  -v ./watchseerr.toml:/config/watchseerr.toml:ro \
  -v watchseerr-data:/data \
  -e WATCHSEERR_SEERR_API_KEY=... \
  watchseerr
```

### pip

```sh
pip install git+https://github.com/jerzyszyjut/watchseerr
watchseerr -c watchseerr.toml --dry-run
```

## Configure

Copy [`watchseerr.example.toml`](watchseerr.example.toml). It documents every
key.

| key | meaning |
| --- | --- |
| `seerr.url` | Seerr's address, e.g. `http://localhost:5055` |
| `seerr.api_key_file` | file with the API key. You can also use `$WATCHSEERR_SEERR_API_KEY`, or a systemd credential called `seerr-api-key` |
| `sources[].type` | `letterboxd` or `serializd` |
| `sources[].user` | the profile name as it appears in the site's URL |
| `sources[].list` | Letterboxd only: a list slug, used instead of the watchlist |
| `sources[].seasons` | Serializd only: `watchlisted` (default) or `all` |
| `sources[].seerr_user` | request as this Seerr user (id, username, display name, or email). Default: the API key's owner |
| `sources[].initial` | `request` (default), or `skip`. With `skip`, the first pass only records what is on the list, and only later additions are requested |
| `max_requests_per_run` | at most this many requests per pass (default 25) |
| `interval` | time between passes with `--daemon` (default `6h`) |

Requesting on behalf of another user needs an API key with the *Manage
Requests* permission. The admin's key has it.

## Run

```sh
watchseerr --dry-run -v   # what would be requested, and why everything else was skipped
watchseerr                # one pass
watchseerr --daemon       # a pass every `interval`
```

The exit status is 1 if any source had a problem, for example an unknown
user, a private profile, or a site that is down. The other sources still run.

## Caveats

- Both sites are read through unofficial interfaces. If Letterboxd changes
  its HTML or Serializd changes its API, a source will fail loudly rather
  than request the wrong things. Please open an issue when that happens.
- Profiles must be public.
- Taking a film off your watchlist does not cancel its request. Requests are
  only ever added.

## Related projects

- [ListSync](https://github.com/Woahai321/list-sync): many list sources
  (IMDb, Trakt, Letterboxd, …) to Seerr, with a web UI. It reads Letterboxd
  with a headless browser.
- [letterboxd-list-radarr](https://github.com/screeny05/letterboxd-list-radarr):
  serves Letterboxd lists as a Radarr import list.

I found no tool that brings Serializd watchlists into Seerr or Sonarr, which
is why this one exists.

## License

MIT
