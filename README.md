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
uv run pytest
```
