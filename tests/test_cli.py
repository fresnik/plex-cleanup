import csv
import io
import json

from typer.testing import CliRunner

from plex_cleanup.cache import Cache
from plex_cleanup.cli import app

from .conftest import make_episode, make_record

runner = CliRunner()


def seed_cache(tmp_path):
    path = tmp_path / "cache.json"
    cache = Cache(path)
    cache.set_records(
        "Movies",
        [
            make_record(title="Big Unwatched", file="/m/big.mkv", plays=0,
                        size_bytes=20 * 1024**3, resolution="4k", rating_key=1),
            make_record(title="Small Watched", file="/m/small.mkv", plays=7,
                        size_bytes=1024**3, resolution="720", rating_key=2),
        ],
    )
    cache.save()
    return path


def test_search_from_cache_json(tmp_path):
    cache_path = seed_cache(tmp_path)
    result = runner.invoke(
        app,
        ["search", "-l", "Movies", "--max-plays", "0", "--format", "json",
         "--cache-file", str(cache_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["summary"]["count"] == 1
    assert payload["results"][0]["file"] == "/m/big.mkv"


def test_search_resolution_filter_csv(tmp_path):
    cache_path = seed_cache(tmp_path)
    result = runner.invoke(
        app,
        ["search", "-l", "Movies", "--min-resolution", "1080", "--format", "csv",
         "--cache-file", str(cache_path)],
    )
    assert result.exit_code == 0, result.output
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    assert [r["file"] for r in rows] == ["/m/big.mkv"]


def test_search_tabular_summary(tmp_path):
    cache_path = seed_cache(tmp_path)
    result = runner.invoke(
        app, ["search", "-l", "Movies", "--cache-file", str(cache_path)]
    )
    assert result.exit_code == 0, result.output
    assert "2 file(s) found" in result.output


def test_search_output_file(tmp_path):
    cache_path = seed_cache(tmp_path)
    out = tmp_path / "out.json"
    result = runner.invoke(
        app,
        ["search", "-l", "Movies", "--format", "json", "--output", str(out),
         "--cache-file", str(cache_path)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text())["summary"]["count"] == 2


def test_search_uncached_library_without_credentials_fails(tmp_path):
    cache_path = seed_cache(tmp_path)
    result = runner.invoke(
        app,
        ["search", "-l", "Nope", "--cache-file", str(cache_path)],
        env={"PLEX_URL": "", "PLEX_TOKEN": ""},
    )
    assert result.exit_code == 1
    assert "Plex connection required" in result.output


def test_search_invalid_size_errors(tmp_path):
    cache_path = seed_cache(tmp_path)
    result = runner.invoke(
        app,
        ["search", "-l", "Movies", "--min-size", "10xb", "--cache-file", str(cache_path)],
    )
    assert result.exit_code != 0


class FakePart:
    def __init__(self, file, size):
        self.file = file
        self.size = size


class FakeMedia:
    def __init__(self, bitrate, resolution, parts):
        self.bitrate = bitrate
        self.videoResolution = resolution
        self.parts = parts


class FakeItem:
    type = "movie"

    def __init__(self, rating_key, title, plays, media):
        self.ratingKey = rating_key
        self.title = title
        self.viewCount = plays
        self.addedAt = None
        self.media = media


class FakeServer:
    def __init__(self, items):
        self._items = {item.ratingKey: item for item in items}

    def fetchItem(self, rating_key):
        from plexapi.exceptions import NotFound

        if rating_key not in self._items:
            raise NotFound(str(rating_key))
        return self._items[rating_key]


def test_refresh_reports_unchanged_updated_and_removed(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.json"
    cache = Cache(cache_path)
    cache.set_records(
        "Movies",
        [
            make_record(rating_key=1, title="Same", file="/m/same.mkv", plays=2,
                        added_at=None),
            make_record(rating_key=2, title="Changed", file="/m/changed.mkv", plays=2,
                        added_at=None),
            make_record(rating_key=3, title="Gone", file="/m/gone.mkv", added_at=None),
        ],
    )
    cache.save()

    base = make_record()  # for the shared default field values
    server = FakeServer(
        [
            FakeItem(1, "Same", plays=2, media=[FakeMedia(
                base.bitrate_kbps, base.resolution, [FakePart("/m/same.mkv", base.size_bytes)])]),
            FakeItem(2, "Changed", plays=9, media=[FakeMedia(
                base.bitrate_kbps, base.resolution, [FakePart("/m/changed.mkv", base.size_bytes)])]),
        ]
    )
    monkeypatch.setattr("plex_cleanup.cli._connect", lambda url, token: server)

    result = runner.invoke(
        app, ["refresh-metadata", "--format", "json", "--cache-file", str(cache_path)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["summary"] == {"updated": 1, "unchanged": 1, "removed": 1}
    statuses = {r["file"]: r["status"] for r in payload["results"]}
    assert statuses == {
        "/m/same.mkv": "unchanged",
        "/m/changed.mkv": "updated",
        "/m/gone.mkv": "removed",
    }

    # cache reflects the refresh: play count updated, deleted item gone
    refreshed = {r.file: r for r in Cache.load(cache_path).get_records("Movies")}
    assert refreshed["/m/changed.mkv"].plays == 9
    assert "/m/gone.mkv" not in refreshed


def test_refresh_tabular_hides_unchanged(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.json"
    cache = Cache(cache_path)
    cache.set_records(
        "Movies", [make_record(rating_key=1, title="Same", file="/m/same.mkv",
                               plays=2, added_at=None)]
    )
    cache.save()
    base = make_record()
    server = FakeServer(
        [FakeItem(1, "Same", plays=2, media=[FakeMedia(
            base.bitrate_kbps, base.resolution, [FakePart("/m/same.mkv", base.size_bytes)])])]
    )
    monkeypatch.setattr("plex_cleanup.cli._connect", lambda url, token: server)

    result = runner.invoke(
        app, ["refresh-metadata", "--cache-file", str(cache_path)]
    )
    assert result.exit_code == 0, result.output
    assert "0 file(s) updated, 1 unchanged" in result.output
    assert "unchanged" not in result.output.split("updated,")[0]  # no table row for it


def test_refresh_empty_cache_errors(tmp_path):
    result = runner.invoke(
        app, ["refresh-metadata", "--cache-file", str(tmp_path / "cache.json")]
    )
    assert result.exit_code == 1
    assert "Cache is empty" in result.output


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
