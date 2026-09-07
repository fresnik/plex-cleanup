# Aggregate search by show/season — design

**Date:** 2026-09-07
**Status:** Approved

## Purpose

Let `search` find whole TV shows or whole seasons matching play-count,
size, and bitrate filters, instead of only individual files. For cleanup,
shows and seasons are the natural deletion unit; an aggregate view
("shows nobody has watched, biggest first") is more actionable for TV
libraries than per-episode rows.

## CLI surface

Extend the existing `search` command with one option:

```
--group-by [show|season]    Aggregate results per TV show or per season.
```

- Absent: current per-file behavior, unchanged.
- `--min-resolution` / `--max-resolution` combined with `--group-by` is a
  `typer.BadParameter` error: resolution does not aggregate meaningfully
  (a mixed-resolution show has no single value).
- Non-show libraries in the selection (movies, music) are skipped with a
  stderr warning. `-l all --group-by show` works and aggregates only the
  TV libraries.

Examples:

```sh
# Completely unwatched shows, biggest first
plex-cleanup search -l TV --group-by show --max-plays 0

# Seasons whose average episode file is over 3GB
plex-cleanup search -l TV --group-by season --min-size 3GB
```

No new subcommand: a separate command would duplicate nearly the entire
`search` signature (library selection, cache handling, connection, filter,
format/output options) and drift over time. Grouping is the same pipeline
(load cache → scan missing libraries → filter → render) with an
aggregation step inserted and a second renderer.

## Data model & cache

Add two fields to `MediaRecord` (`models.py`):

- `show: str | None` — episode's `grandparentTitle`; `None` for movies
  and tracks.
- `season: int | None` — episode's `parentIndex`; `None` for movies and
  tracks.

`server.records_for_item` populates them for episodes.

Cache compatibility:

- `MediaRecord.from_dict` ignores unknown keys, so old caches keep
  loading for per-file search. New fields default to `None` when absent
  in cached data.
- Records cached before this change lack the fields. When `--group-by`
  finds such records, the user gets an actionable message pointing at
  `refresh-metadata` (see decision rule below). No silent empty groups.

Grouping rule: aggregate the records that have `show` set. The cache
does not store the library's section type, so a library whose records
all lack `show` is indistinguishable between "movie/music library" and
"TV library cached before this change" — the messaging covers both.
Decision rule:

1. Partition selected records into groupable (`show` set) and ungroupable.
2. If a selected library has only ungroupable records, print one stderr
   warning naming it (covers movie/music and stale TV caches; the warning
   text mentions `refresh-metadata` as the fix for TV libraries).
3. If no groupable records remain at all, exit with code 1 and an error
   explaining both causes (non-TV libraries / stale cache).

## Aggregation & filter semantics

New function in `filters.py`:

```python
def aggregate(records: list[MediaRecord], level: str) -> list[AggregateRecord]
```

Group key: `(library, show)` for `show`, `(library, show, season)` for
`season`.

New dataclass `AggregateRecord` (in `models.py`):

- `library: str`
- `show: str`
- `season: int | None` (set for season level)
- `episodes: int` — distinct rating keys in the group
- `files: int` — file records in the group
- `plays_min: int`, `plays_max: int`
- `avg_size_bytes: int | None`
- `avg_bitrate_kbps: int | None`
- `total_size_bytes: int`

Filter semantics (applied to aggregates when `--group-by` is active):

- **Plays**: the group matches only if **every episode** satisfies
  `min_plays <= plays <= max_plays` (for the bounds given). Equivalent
  check: `plays_min >= min_plays` and `plays_max <= max_plays`.
  Play counts are per episode (per rating key), not per file.
- **Size / bitrate**: `--min/max-size` and `--min/max-bitrate` compare
  the **group average**. The average is computed over files with a known
  value. A group where every file's value is unknown is excluded when a
  filter on that field is active (matches the existing per-file `None`
  semantics).
- **Resolution**: not applicable; rejected at the CLI level.

Total size is a display/sort column only; no `--min/max-total-size`
filters in this iteration.

## Output

New renderer `render_aggregates` in `output.py`, supporting the same
three formats:

- **tabular**: columns Library | Show | Season (season level only) |
  Episodes | Plays | Avg Bitrate | Avg Size | Total Size. Sorted by
  total size descending. Plays renders as a single number when
  `plays_min == plays_max`, otherwise as a range `min–max`. Summary
  line: `N show(s) found, X total` / `N season(s) found, X total`
  where X is the sum of total sizes.
- **json**: `{"summary": {"count": N, "total_size_bytes": X},
  "results": [<AggregateRecord dicts>]}` with raw numeric fields.
- **csv**: one row per group with the `AggregateRecord` fields
  (`library, show, season, episodes, files, plays_min, plays_max,
  avg_bitrate_kbps, avg_size_bytes, total_size_bytes`).

## Testing

- `test_filters.py`: grouping correctness at both levels; every-episode
  play semantics including boundary values; multi-file episodes counted
  once for plays; averages ignoring `None` values; all-`None` group
  excluded when that filter is active; total size summation.
- `test_cli.py`: `--group-by` with resolution filters → error; mixed
  libraries → warning and only TV groups in output; records without
  `show` (old cache) → actionable error; happy path per level.
- `test_units`/output tests: aggregate rendering in tabular, json, csv,
  including the plays range formatting.

## Out of scope

- Grouping music libraries by artist/album.
- `--min/max-total-size` filters.
- Resolution aggregation.
- Last-watched-date filters.
