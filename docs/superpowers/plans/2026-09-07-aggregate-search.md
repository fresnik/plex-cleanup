# Aggregate Search by Show/Season Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--group-by show|season` to the `search` command so whole TV shows or seasons can be found by play count, average size, and average bitrate.

**Architecture:** Two new structured fields (`show`, `season`) on `MediaRecord` feed a new aggregation step in `filters.py` that folds file records into `AggregateRecord` groups; a new renderer in `output.py` displays them. The CLI inserts the aggregation between record collection and rendering — the per-file path is untouched.

**Tech Stack:** Python 3.14, Typer, Rich, dataclasses, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-09-07-aggregate-search-design.md`

## File Structure

- `src/plex_cleanup/models.py` — add `show`/`season` fields to `MediaRecord`; new `AggregateRecord` dataclass
- `src/plex_cleanup/server.py` — populate `show`/`season` for episodes in `records_for_item`
- `src/plex_cleanup/filters.py` — `aggregate()`, `matches_aggregate()`, `apply_aggregate_filters()`
- `src/plex_cleanup/output.py` — `render_aggregates()`, `AGGREGATE_CSV_FIELDS`
- `src/plex_cleanup/cli.py` — `GroupBy` enum, `--group-by` option, validation, warning/error logic, dispatch
- `tests/conftest.py` — `make_episode` helper
- `tests/test_server.py` — new: episode field extraction
- `tests/test_filters.py` — aggregation and aggregate-filter tests
- `tests/test_output.py` — new: aggregate renderer tests
- `tests/test_cli.py` — end-to-end `--group-by` tests
- `README.md` — document the new option

All commands below run from the repo root. The full test suite is `uv run pytest`.

---

### Task 1: `show`/`season` fields on MediaRecord + server extraction

**Files:**
- Modify: `src/plex_cleanup/models.py` (MediaRecord, ~line 22)
- Modify: `src/plex_cleanup/server.py` (`records_for_item`, ~line 43)
- Create: `tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_server.py`:

```python
from plex_cleanup.models import MediaRecord
from plex_cleanup.server import records_for_item


class FakePart:
    def __init__(self, file, size=1024**3):
        self.file = file
        self.size = size


class FakeMedia:
    def __init__(self, parts, bitrate=5000, resolution="1080"):
        self.parts = parts
        self.bitrate = bitrate
        self.videoResolution = resolution


class FakeEpisode:
    type = "episode"

    def __init__(self, rating_key, show, season, episode_title, file):
        self.ratingKey = rating_key
        self.grandparentTitle = show
        self.parentIndex = season
        self.seasonEpisode = f"s{season:02d}e01"
        self.title = episode_title
        self.viewCount = 0
        self.addedAt = None
        self.media = [FakeMedia([FakePart(file)])]


class FakeMovie:
    type = "movie"

    def __init__(self, rating_key, title, file):
        self.ratingKey = rating_key
        self.title = title
        self.viewCount = 0
        self.addedAt = None
        self.media = [FakeMedia([FakePart(file)])]


def test_episode_records_carry_show_and_season():
    item = FakeEpisode(10, "Example Show", 2, "Pilot", "/tv/show/s02e01.mkv")
    (record,) = list(records_for_item(item, "TV"))
    assert record.show == "Example Show"
    assert record.season == 2


def test_movie_records_have_no_show_or_season():
    item = FakeMovie(11, "Example Movie", "/m/movie.mkv")
    (record,) = list(records_for_item(item, "Movies"))
    assert record.show is None
    assert record.season is None


def test_old_cache_dict_without_new_fields_loads_with_none():
    data = dict(
        library="TV", title="T", rating_key=1, file="/f.mkv",
        size_bytes=1, bitrate_kbps=1, resolution="1080", plays=0, added_at=None,
    )
    record = MediaRecord.from_dict(data)
    assert record.show is None
    assert record.season is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL — `MediaRecord` has no attribute `show` (or unexpected keyword / TypeError from `from_dict` missing defaults).

- [ ] **Step 3: Add the fields to MediaRecord**

In `src/plex_cleanup/models.py`, add two defaulted fields at the end of `MediaRecord` (after `added_at`), with a comment explaining them:

```python
@dataclass
class MediaRecord:
    """Metadata for a single media file (one Plex media part)."""

    library: str
    title: str
    rating_key: int
    file: str
    size_bytes: int | None
    bitrate_kbps: int | None
    resolution: str | None
    plays: int
    added_at: str | None
    # Structured show/season info for episodes; None for movies and tracks.
    # Defaulted so records cached before these fields existed still load.
    show: str | None = None
    season: int | None = None
```

- [ ] **Step 4: Populate the fields in records_for_item**

In `src/plex_cleanup/server.py`, modify `records_for_item`:

```python
def records_for_item(item, library: str) -> Iterator[MediaRecord]:
    """One record per media file (part) of a Plex item."""
    plays = getattr(item, "viewCount", 0) or 0
    added_at = getattr(item, "addedAt", None)
    title = display_title(item)
    show = getattr(item, "grandparentTitle", None) if item.type == "episode" else None
    season = getattr(item, "parentIndex", None) if item.type == "episode" else None
    for media in item.media or []:
        for part in media.parts or []:
            if not part.file:
                continue
            yield MediaRecord(
                library=library,
                title=title,
                rating_key=int(item.ratingKey),
                file=part.file,
                size_bytes=part.size,
                bitrate_kbps=media.bitrate,
                resolution=getattr(media, "videoResolution", None),
                plays=plays,
                added_at=added_at.isoformat() if added_at else None,
                show=show,
                season=int(season) if season is not None else None,
            )
```

- [ ] **Step 5: Run the full suite to verify everything passes**

Run: `uv run pytest -v`
Expected: all tests PASS (existing tests must not break — the new fields are defaulted).

- [ ] **Step 6: Commit**

```bash
git add src/plex_cleanup/models.py src/plex_cleanup/server.py tests/test_server.py
git commit -m "feat: add structured show/season fields to MediaRecord"
```

---

### Task 2: AggregateRecord and aggregate()

**Files:**
- Modify: `src/plex_cleanup/models.py` (append after `MediaRecord`)
- Modify: `src/plex_cleanup/filters.py`
- Modify: `tests/conftest.py` (add `make_episode`)
- Modify: `tests/test_filters.py`

- [ ] **Step 1: Add the episode factory to conftest**

Append to `tests/conftest.py`:

```python
def make_episode(**overrides) -> MediaRecord:
    defaults = dict(
        library="TV",
        title="Example Show - S01E01 - Pilot",
        rating_key=201,
        file="/media/tv/example/s01e01.mkv",
        show="Example Show",
        season=1,
    )
    defaults.update(overrides)
    return make_record(**defaults)
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_filters.py` (also add `make_episode` to the conftest import and `aggregate` to the filters import at the top of the file):

```python
def test_aggregate_by_show_groups_across_seasons():
    records = [
        make_episode(rating_key=1, season=1, file="/tv/a/s01e01.mkv", plays=0),
        make_episode(rating_key=2, season=2, file="/tv/a/s02e01.mkv", plays=3),
        make_episode(rating_key=3, show="Other Show", file="/tv/b/s01e01.mkv"),
    ]
    aggs = aggregate(records, "show")
    assert {a.show for a in aggs} == {"Example Show", "Other Show"}
    example = next(a for a in aggs if a.show == "Example Show")
    assert example.season is None
    assert example.episodes == 2
    assert example.plays_min == 0
    assert example.plays_max == 3


def test_aggregate_by_season_splits_seasons():
    records = [
        make_episode(rating_key=1, season=1, file="/tv/a/s01e01.mkv"),
        make_episode(rating_key=2, season=2, file="/tv/a/s02e01.mkv"),
    ]
    aggs = aggregate(records, "season")
    assert sorted(a.season for a in aggs) == [1, 2]
    assert all(a.show == "Example Show" and a.episodes == 1 for a in aggs)


def test_aggregate_skips_records_without_show():
    records = [make_record(), make_episode(rating_key=1)]
    aggs = aggregate(records, "show")
    assert len(aggs) == 1


def test_aggregate_multi_file_episode_counted_once():
    records = [
        make_episode(rating_key=1, file="/tv/a/e1-part1.mkv", plays=2,
                     size_bytes=1024**3),
        make_episode(rating_key=1, file="/tv/a/e1-part2.mkv", plays=2,
                     size_bytes=3 * 1024**3),
    ]
    (agg,) = aggregate(records, "show")
    assert agg.episodes == 1
    assert agg.files == 2
    assert agg.plays_min == agg.plays_max == 2
    assert agg.total_size_bytes == 4 * 1024**3
    assert agg.avg_size_bytes == 2 * 1024**3


def test_aggregate_averages_ignore_unknown_values():
    records = [
        make_episode(rating_key=1, file="/tv/a/e1.mkv", size_bytes=2 * 1024**3,
                     bitrate_kbps=4000),
        make_episode(rating_key=2, file="/tv/a/e2.mkv", size_bytes=None,
                     bitrate_kbps=None),
    ]
    (agg,) = aggregate(records, "show")
    assert agg.avg_size_bytes == 2 * 1024**3
    assert agg.avg_bitrate_kbps == 4000
    assert agg.total_size_bytes == 2 * 1024**3


def test_aggregate_all_unknown_averages_are_none():
    records = [make_episode(rating_key=1, size_bytes=None, bitrate_kbps=None)]
    (agg,) = aggregate(records, "show")
    assert agg.avg_size_bytes is None
    assert agg.avg_bitrate_kbps is None
    assert agg.total_size_bytes == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_filters.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'aggregate'`.

- [ ] **Step 4: Add AggregateRecord to models.py**

Append to `src/plex_cleanup/models.py`:

```python
@dataclass
class AggregateRecord:
    """Aggregated metadata for a whole TV show or one season of it."""

    library: str
    show: str
    season: int | None  # set at season level, None at show level
    episodes: int  # distinct Plex items (rating keys)
    files: int  # media file records
    plays_min: int
    plays_max: int
    avg_bitrate_kbps: int | None
    avg_size_bytes: int | None
    total_size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 5: Implement aggregate() in filters.py**

In `src/plex_cleanup/filters.py`, extend the models import and append:

```python
from .models import AggregateRecord, MediaRecord, resolution_ordinal
```

```python
def aggregate(records: list[MediaRecord], level: str) -> list[AggregateRecord]:
    """Fold file records into per-show or per-season aggregates.

    Records without show info (movies, tracks, stale caches) are ignored.
    Averages are over files with a known value; None when no file has one.
    """
    groups: dict[tuple, list[MediaRecord]] = {}
    for record in records:
        if record.show is None:
            continue
        key = (record.library, record.show)
        if level == "season":
            key += (record.season,)
        groups.setdefault(key, []).append(record)

    aggregates = []
    for key, group in groups.items():
        # Plays are per episode, not per file: a multi-part episode counts once.
        plays_by_episode: dict[int, int] = {}
        for record in group:
            plays_by_episode[record.rating_key] = record.plays or 0
        sizes = [r.size_bytes for r in group if r.size_bytes is not None]
        bitrates = [r.bitrate_kbps for r in group if r.bitrate_kbps is not None]
        aggregates.append(
            AggregateRecord(
                library=key[0],
                show=key[1],
                season=key[2] if level == "season" else None,
                episodes=len(plays_by_episode),
                files=len(group),
                plays_min=min(plays_by_episode.values()),
                plays_max=max(plays_by_episode.values()),
                avg_bitrate_kbps=round(sum(bitrates) / len(bitrates)) if bitrates else None,
                avg_size_bytes=round(sum(sizes) / len(sizes)) if sizes else None,
                total_size_bytes=sum(sizes),
            )
        )
    return aggregates
```

- [ ] **Step 6: Run the full suite to verify everything passes**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/plex_cleanup/models.py src/plex_cleanup/filters.py tests/conftest.py tests/test_filters.py
git commit -m "feat: aggregate media records by show or season"
```

---

### Task 3: Aggregate filter matching

**Files:**
- Modify: `src/plex_cleanup/filters.py`
- Modify: `tests/test_filters.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_filters.py` (add `apply_aggregate_filters`, `matches_aggregate` to the filters import):

```python
def _agg(**overrides):
    records = [
        make_episode(rating_key=1, file="/tv/a/e1.mkv", plays=0,
                     size_bytes=2 * 1024**3, bitrate_kbps=4000),
        make_episode(rating_key=2, file="/tv/a/e2.mkv", plays=3,
                     size_bytes=4 * 1024**3, bitrate_kbps=6000),
    ]
    (agg,) = aggregate(records, "show")
    for name, value in overrides.items():
        setattr(agg, name, value)
    return agg


def test_aggregate_plays_every_episode_must_satisfy():
    agg = _agg()  # plays 0 and 3
    assert matches_aggregate(agg, SearchFilters())
    # max_plays: the most-played episode (3) must be within the bound
    assert matches_aggregate(agg, SearchFilters(max_plays=3))
    assert not matches_aggregate(agg, SearchFilters(max_plays=2))
    assert not matches_aggregate(agg, SearchFilters(max_plays=0))
    # min_plays: the least-played episode (0) must be within the bound
    assert matches_aggregate(agg, SearchFilters(min_plays=0))
    assert not matches_aggregate(agg, SearchFilters(min_plays=1))


def test_aggregate_size_and_bitrate_compare_average():
    agg = _agg()  # avg size 3GB, avg bitrate 5000
    assert matches_aggregate(
        agg, SearchFilters(min_size=3 * 1024**3, max_size=3 * 1024**3)
    )
    assert not matches_aggregate(agg, SearchFilters(min_size=3 * 1024**3 + 1))
    assert not matches_aggregate(agg, SearchFilters(max_size=3 * 1024**3 - 1))
    assert matches_aggregate(agg, SearchFilters(min_bitrate=5000, max_bitrate=5000))
    assert not matches_aggregate(agg, SearchFilters(min_bitrate=5001))
    assert not matches_aggregate(agg, SearchFilters(max_bitrate=4999))


def test_aggregate_unknown_average_excluded_when_filter_active():
    agg = _agg(avg_size_bytes=None, avg_bitrate_kbps=None)
    assert matches_aggregate(agg, SearchFilters())
    assert not matches_aggregate(agg, SearchFilters(min_size=1))
    assert not matches_aggregate(agg, SearchFilters(max_size=10**12))
    assert not matches_aggregate(agg, SearchFilters(min_bitrate=1))
    assert not matches_aggregate(agg, SearchFilters(max_bitrate=10**6))


def test_apply_aggregate_filters():
    watched = _agg(plays_min=5, plays_max=9)
    unwatched = _agg(plays_min=0, plays_max=0)
    result = apply_aggregate_filters([watched, unwatched], SearchFilters(max_plays=0))
    assert result == [unwatched]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_filters.py -v`
Expected: FAIL with `ImportError: cannot import name 'matches_aggregate'`.

- [ ] **Step 3: Implement matching in filters.py**

Append to `src/plex_cleanup/filters.py`:

```python
def matches_aggregate(agg: AggregateRecord, filters: SearchFilters) -> bool:
    """True if the aggregate passes every active filter.

    Plays: every episode must satisfy the range, i.e. the least-played
    episode meets min_plays and the most-played meets max_plays.
    Size/bitrate: compared against the group average; a group whose average
    is unknown is excluded when a filter on that field is active.
    Resolution filters are rejected at the CLI level and ignored here.
    """
    if filters.min_plays is not None and agg.plays_min < filters.min_plays:
        return False
    if filters.max_plays is not None and agg.plays_max > filters.max_plays:
        return False

    if filters.min_bitrate is not None and (
        agg.avg_bitrate_kbps is None or agg.avg_bitrate_kbps < filters.min_bitrate
    ):
        return False
    if filters.max_bitrate is not None and (
        agg.avg_bitrate_kbps is None or agg.avg_bitrate_kbps > filters.max_bitrate
    ):
        return False

    if filters.min_size is not None and (
        agg.avg_size_bytes is None or agg.avg_size_bytes < filters.min_size
    ):
        return False
    if filters.max_size is not None and (
        agg.avg_size_bytes is None or agg.avg_size_bytes > filters.max_size
    ):
        return False

    return True


def apply_aggregate_filters(
    aggregates: list[AggregateRecord], filters: SearchFilters
) -> list[AggregateRecord]:
    return [a for a in aggregates if matches_aggregate(a, filters)]
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/plex_cleanup/filters.py tests/test_filters.py
git commit -m "feat: filter aggregates on plays range and group averages"
```

---

### Task 4: Aggregate renderer

**Files:**
- Modify: `src/plex_cleanup/output.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_output.py`:

```python
import csv
import io
import json

from rich.console import Console

from plex_cleanup.models import AggregateRecord
from plex_cleanup.output import OutputFormat, render_aggregates


def make_aggregate(**overrides) -> AggregateRecord:
    defaults = dict(
        library="TV",
        show="Example Show",
        season=None,
        episodes=10,
        files=10,
        plays_min=0,
        plays_max=0,
        avg_bitrate_kbps=5000,
        avg_size_bytes=2 * 1024**3,
        total_size_bytes=20 * 1024**3,
    )
    defaults.update(overrides)
    return AggregateRecord(**defaults)


def render_to_file(aggs, level, fmt, tmp_path):
    out = tmp_path / "out.txt"
    render_aggregates(aggs, level, fmt, out, Console(file=io.StringIO()))
    return out.read_text(encoding="utf-8")


def test_render_aggregates_json(tmp_path):
    text = render_to_file([make_aggregate()], "show", OutputFormat.json, tmp_path)
    payload = json.loads(text)
    assert payload["summary"] == {"count": 1, "total_size_bytes": 20 * 1024**3}
    assert payload["results"][0]["show"] == "Example Show"
    assert payload["results"][0]["plays_max"] == 0


def test_render_aggregates_csv(tmp_path):
    agg = make_aggregate(season=2, plays_max=3)
    text = render_to_file([agg], "season", OutputFormat.csv, tmp_path)
    (row,) = list(csv.DictReader(io.StringIO(text)))
    assert row["show"] == "Example Show"
    assert row["season"] == "2"
    assert row["plays_min"] == "0"
    assert row["plays_max"] == "3"
    assert row["total_size_bytes"] == str(20 * 1024**3)


def test_render_aggregates_tabular_plays_range(tmp_path):
    uniform = make_aggregate()
    mixed = make_aggregate(show="Mixed Show", plays_min=1, plays_max=4)
    text = render_to_file([uniform, mixed], "show", OutputFormat.tabular, tmp_path)
    assert "1–4" in text  # range rendered with an en dash
    assert "2 show(s) found" in text


def test_render_aggregates_tabular_season_column_and_noun(tmp_path):
    agg = make_aggregate(season=1)
    text = render_to_file([agg], "season", OutputFormat.tabular, tmp_path)
    assert "Season" in text
    assert "1 season(s) found" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_output.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_aggregates'`.

- [ ] **Step 3: Implement render_aggregates in output.py**

In `src/plex_cleanup/output.py`, extend the models import to `from .models import AggregateRecord, MediaRecord`, then append:

```python
AGGREGATE_CSV_FIELDS = [
    "library",
    "show",
    "season",
    "episodes",
    "files",
    "plays_min",
    "plays_max",
    "avg_bitrate_kbps",
    "avg_size_bytes",
    "total_size_bytes",
]


def _format_plays_range(agg: AggregateRecord) -> str:
    if agg.plays_min == agg.plays_max:
        return str(agg.plays_min)
    return f"{agg.plays_min}–{agg.plays_max}"


def _aggregates_table(aggs: list[AggregateRecord], level: str, title: str) -> Table:
    table = Table(title=title, show_lines=False)
    table.add_column("Library", style="cyan", no_wrap=True)
    table.add_column("Show", style="bold")
    if level == "season":
        table.add_column("Season", justify="right")
    table.add_column("Episodes", justify="right")
    table.add_column("Plays", justify="right", style="green")
    table.add_column("Avg Bitrate", justify="right")
    table.add_column("Avg Size", justify="right")
    table.add_column("Total Size", justify="right", style="magenta")
    for a in aggs:
        row = [a.library, a.show]
        if level == "season":
            row.append(str(a.season) if a.season is not None else "-")
        row.extend(
            [
                str(a.episodes),
                _format_plays_range(a),
                format_bitrate(a.avg_bitrate_kbps),
                format_size(a.avg_size_bytes),
                format_size(a.total_size_bytes),
            ]
        )
        table.add_row(*row)
    return table


def render_aggregates(
    aggs: list[AggregateRecord],
    level: str,
    fmt: OutputFormat,
    output: Path | None,
    console: Console,
) -> None:
    total_size = sum(a.total_size_bytes for a in aggs)
    noun = "show(s)" if level == "show" else "season(s)"
    summary = f"{len(aggs)} {noun} found, {format_size(total_size)} total"

    if fmt is OutputFormat.json:
        payload = {
            "summary": {"count": len(aggs), "total_size_bytes": total_size},
            "results": [a.to_dict() for a in aggs],
        }
        _write(json.dumps(payload, indent=2), output, console)
        return

    if fmt is OutputFormat.csv:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=AGGREGATE_CSV_FIELDS)
        writer.writeheader()
        for a in aggs:
            writer.writerow(a.to_dict())
        _write(buf.getvalue().rstrip("\n"), output, console)
        return

    table = _aggregates_table(aggs, level, title=f"Matches ({len(aggs)})")
    if output is None:
        out_console = Console()
        out_console.print(table)
        out_console.print(f"[bold]{summary}[/bold]")
    else:
        file_console = Console(file=io.StringIO(), width=200)
        file_console.print(table)
        file_console.print(summary)
        output.write_text(file_console.file.getvalue(), encoding="utf-8")
        console.print(f"[dim]Wrote output to {output}[/dim]")
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/plex_cleanup/output.py tests/test_output.py
git commit -m "feat: render show/season aggregates in all output formats"
```

---

### Task 5: CLI wiring for --group-by

**Files:**
- Modify: `src/plex_cleanup/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` (add `make_episode` to the conftest import at the top):

```python
def seed_tv_cache(tmp_path):
    path = tmp_path / "cache.json"
    cache = Cache(path)
    cache.set_records(
        "TV",
        [
            make_episode(rating_key=10, show="Unwatched Show", season=1,
                         file="/tv/u/s01e01.mkv", plays=0, size_bytes=2 * 1024**3),
            make_episode(rating_key=11, show="Unwatched Show", season=2,
                         file="/tv/u/s02e01.mkv", plays=0, size_bytes=4 * 1024**3),
            make_episode(rating_key=12, show="Watched Show", season=1,
                         file="/tv/w/s01e01.mkv", plays=5, size_bytes=1024**3),
        ],
    )
    cache.save()
    return path


def test_group_by_show_json(tmp_path):
    cache_path = seed_tv_cache(tmp_path)
    result = runner.invoke(
        app,
        ["search", "-l", "TV", "--group-by", "show", "--max-plays", "0",
         "--format", "json", "--cache-file", str(cache_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["summary"]["count"] == 1
    (row,) = payload["results"]
    assert row["show"] == "Unwatched Show"
    assert row["episodes"] == 2
    assert row["total_size_bytes"] == 6 * 1024**3
    assert row["avg_size_bytes"] == 3 * 1024**3


def test_group_by_season_json(tmp_path):
    cache_path = seed_tv_cache(tmp_path)
    result = runner.invoke(
        app,
        ["search", "-l", "TV", "--group-by", "season", "--format", "json",
         "--cache-file", str(cache_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["summary"]["count"] == 3
    # sorted by total size descending
    assert [r["total_size_bytes"] for r in payload["results"]] == [
        4 * 1024**3, 2 * 1024**3, 1024**3,
    ]


def test_group_by_rejects_resolution_filters(tmp_path):
    cache_path = seed_tv_cache(tmp_path)
    result = runner.invoke(
        app,
        ["search", "-l", "TV", "--group-by", "show", "--min-resolution", "1080",
         "--cache-file", str(cache_path)],
    )
    assert result.exit_code != 0
    assert "resolution" in result.output.lower()


def test_group_by_skips_non_tv_library_with_warning(tmp_path):
    cache_path = seed_tv_cache(tmp_path)
    cache = Cache.load(cache_path)
    cache.set_records("Movies", [make_record(rating_key=1, file="/m/movie.mkv")])
    cache.save()
    result = runner.invoke(
        app,
        ["search", "-l", "TV", "-l", "Movies", "--group-by", "show",
         "--format", "json", "--cache-file", str(cache_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Skipping 'Movies'" in result.output
    payload = json.loads(result.stdout)
    assert {r["show"] for r in payload["results"]} == {"Unwatched Show", "Watched Show"}


def test_group_by_with_no_groupable_records_errors(tmp_path):
    cache_path = seed_cache(tmp_path)  # movies only
    result = runner.invoke(
        app,
        ["search", "-l", "Movies", "--group-by", "show",
         "--cache-file", str(cache_path)],
    )
    assert result.exit_code == 1
    assert "refresh-metadata" in result.output


def test_search_without_group_by_unchanged(tmp_path):
    cache_path = seed_tv_cache(tmp_path)
    result = runner.invoke(
        app,
        ["search", "-l", "TV", "--format", "json", "--cache-file", str(cache_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["summary"]["count"] == 3
    assert all("file" in r for r in payload["results"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: new tests FAIL — `--group-by` is an unknown option (exit code 2, no such option).

- [ ] **Step 3: Implement --group-by in cli.py**

In `src/plex_cleanup/cli.py`:

Extend the filters/output imports:

```python
from .filters import SearchFilters, aggregate, apply_aggregate_filters, apply_filters
from .output import (
    OutputFormat,
    render_aggregates,
    render_records,
    render_refresh_summary,
)
```

Add a `GroupBy` enum next to `Resolution`:

```python
class GroupBy(str, Enum):
    show = "show"
    season = "season"
```

Add the option to the `search` signature (after `max_resolution`):

```python
    group_by: Optional[GroupBy] = typer.Option(
        None,
        "--group-by",
        case_sensitive=False,
        help="Aggregate results per TV show or per season. "
        "Size/bitrate filters compare the group average; play filters must "
        "hold for every episode. Resolution filters are not supported.",
    ),
```

At the top of the `search` body (before the cache is loaded), reject the invalid combination:

```python
    if group_by is not None and (min_resolution or max_resolution):
        raise typer.BadParameter(
            "--min-resolution/--max-resolution cannot be combined with --group-by; "
            "resolution does not aggregate meaningfully."
        )
```

Replace the final three lines of `search` (the `matched = apply_filters(...)` block) with:

```python
    if group_by is not None:
        # Only records with structured show info can be grouped. A library
        # with none is either not a TV library or was cached before the
        # show/season fields existed.
        libraries_seen = {r.library for r in records}
        libraries_groupable = {r.library for r in records if r.show is not None}
        for name in sorted(libraries_seen - libraries_groupable):
            err_console.print(
                f"[yellow]Skipping {name!r}: no show/season info in cached "
                "records (not a TV library, or the cache predates grouping — "
                "run 'plex-cleanup refresh-metadata').[/yellow]"
            )
        groupable = [r for r in records if r.show is not None]
        if not groupable:
            err_console.print(
                "[red]Error:[/red] no records with show/season info in the "
                "selected libraries. --group-by needs TV libraries; if these "
                "are TV libraries, update the cache with "
                "'plex-cleanup refresh-metadata'."
            )
            raise typer.Exit(code=1)
        aggs = apply_aggregate_filters(aggregate(groupable, group_by.value), filters)
        aggs.sort(key=lambda a: a.total_size_bytes, reverse=True)
        render_aggregates(aggs, group_by.value, format, output, err_console)
        return

    matched = apply_filters(records, filters)
    matched.sort(key=lambda r: r.size_bytes or 0, reverse=True)
    render_records(matched, format, output, err_console, summary_verb="found")
```

(The `filters = SearchFilters(...)` construction stays where it is, above this block.)

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/plex_cleanup/cli.py tests/test_cli.py
git commit -m "feat: add --group-by show|season to search"
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md` (search section, after the filter list ~line 49)

- [ ] **Step 1: Document the option in README.md**

In the `### search` section, after the "Filters (all optional): ..." paragraph, add:

````markdown
Aggregate mode: `--group-by show` or `--group-by season` returns whole TV
shows or seasons instead of files. Play filters must hold for **every**
episode in the group (`--max-plays 0` = nothing in the show was watched);
size and bitrate filters compare the **group average**; resolution filters
are not supported with `--group-by`. Results include episode/file counts,
a plays range, average size/bitrate, and total size (the sort key).
Non-TV libraries are skipped with a warning. Caches written before this
option existed lack show/season info — run `refresh-metadata` once for TV
libraries cached earlier.

```sh
# Completely unwatched shows, biggest first
uv run plex-cleanup search -l TV --group-by show --max-plays 0

# Seasons whose average episode file is over 3GB
uv run plex-cleanup search -l TV --group-by season --min-size 3GB
```
````

- [ ] **Step 2: Run the full suite one final time**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document search --group-by aggregate mode"
```
