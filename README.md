# plex-cleanup

CLI to find cleanup candidates in a Plex media library so disk space can be
recovered with minimal disruption. Scans library metadata once, caches it
locally, and lets you filter on plays, bitrate, file size, and resolution.

## Installation

```sh
uv sync
```

## Configuration

Set the Plex connection via environment variables (or `--url` / `--token`).
Variables are loaded from a `.env` file in the working directory if present
(real environment variables take precedence):

```sh
cp .env.example .env  # then fill in your values
```

```ini
PLEX_URL=http://plex.local:32400
PLEX_TOKEN=your-plex-token
```

Metadata is cached in `~/.cache/plex-cleanup/cache.json` (override with
`--cache-file` or `PLEX_CLEANUP_CACHE`). Searches run from the cache; a
library is only scanned from the server the first time it is requested.

## Usage

### search

Find files matching filters. `--library`/`-l` is required and repeatable;
use `-l all` for every library.

```sh
# Big, unwatched 4K movies
uv run plex-cleanup search -l Movies --max-plays 0 --min-size 15GB --min-resolution 4K

# Low-bitrate files across all libraries, as JSON written to a file
uv run plex-cleanup search -l all --max-bitrate 1500 --format json --output report.json
```

Filters (all optional): `--min-plays` / `--max-plays`, `--min-bitrate` /
`--max-bitrate` (kbps), `--min-size` / `--max-size` (e.g. `500MB`, `1.5GB`),
`--min-resolution` / `--max-resolution` (`sd`, `480`, `720`, `1080`, `4K`).

Play counts cover **every account** on the server, not just the token's:
scans combine the item's view count with the server-wide watch history
(which also captures partial plays), taking the higher of the two. This
needs an admin token; with a restricted token a warning is printed and
counts fall back to the token's own plays. History rows are matched by what
they name (show/season/episode, or movie title) rather than by rating key,
so plays survive an item being deleted and re-added later. Plays older than
the server's history retention only register if the token's account made
them. Caches written before this existed undercount plays — run
`refresh-metadata` once to update them.

Aggregate mode: `--group-by show` or `--group-by season` returns whole TV
shows or seasons instead of files. Play filters compare the group's
**total plays**, summed per episode (`--max-plays 0` still means nothing
in the show was watched); size and bitrate filters compare the **group
average** (per file — a multi-part episode counts per part); resolution
filters are not supported with `--group-by`. With `--group-by season`,
`--show NAME` narrows the results to the seasons of one show
(case-insensitive exact name match). Results include episode/file counts,
total plays (the JSON/CSV output also carries the informational
per-episode `plays_min`/`plays_max`), average size/bitrate, and total
size (the sort key). Non-TV libraries are
skipped with a warning. Caches written before this option existed lack
show/season info — run `refresh-metadata` once for TV libraries cached
earlier.

```sh
# Completely unwatched shows, biggest first
uv run plex-cleanup search -l TV --group-by show --max-plays 0

# Seasons whose average episode file is over 3GB
uv run plex-cleanup search -l TV --group-by season --min-size 3GB

# Unwatched seasons of one show
uv run plex-cleanup search -l TV --group-by season --show "The Wire" --max-plays 0
```

Output: `--format tabular` (default), `json`, or `csv`; `--output FILE`
writes to a file instead of stdout. Files with an unknown value for a field
are excluded when a filter on that field is active.

### refresh-metadata

Re-fetch metadata from the server for cached files (all of them, or just the
paths given). Each file is reported as `updated` (metadata differs from the
cache), `unchanged`, or `removed` (the item no longer exists on the server
and is dropped from the cache). Tabular output lists only updated/removed
files; unchanged files are just counted in the summary.

```sh
uv run plex-cleanup refresh-metadata
uv run plex-cleanup refresh-metadata "/media/movies/example.mkv"
```

## Development

```sh
uv run pytest        # tests
uv run pyrefly check # type check
```

### Git hooks

`hooks/pre-commit` runs the type check and aborts the commit if it reports an
error. Hooks are not enabled automatically by a clone, so enable them once per
working copy:

```sh
git config core.hooksPath hooks
```

Warnings are reported but do not block. To bypass the hook for a single commit,
use `git commit --no-verify`.
