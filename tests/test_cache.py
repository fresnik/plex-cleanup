from plex_cleanup.cache import Cache

from .conftest import make_record


def test_round_trip(tmp_path):
    path = tmp_path / "cache.json"
    cache = Cache(path)
    records = [make_record(), make_record(file="/media/movies/other.mkv", rating_key=102)]
    cache.set_records("Movies", records)
    cache.save()

    loaded = Cache.load(path)
    assert loaded.library_names == ["Movies"]
    assert loaded.get_records("Movies") == records


def test_missing_file_gives_empty_cache(tmp_path):
    cache = Cache.load(tmp_path / "nope.json")
    assert cache.library_names == []
    assert cache.all_records() == []


def test_replace_item_records(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    keep = make_record(rating_key=1, file="/a.mkv")
    old = make_record(rating_key=2, file="/b.mkv", plays=0)
    cache.set_records("Movies", [keep, old])

    new = make_record(rating_key=2, file="/b.mkv", plays=9)
    cache.replace_item_records("Movies", 2, [new])
    records = {r.file: r for r in cache.get_records("Movies")}
    assert records["/a.mkv"] == keep
    assert records["/b.mkv"].plays == 9


def test_replace_item_records_removal(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    cache.set_records("Movies", [make_record(rating_key=2)])
    cache.replace_item_records("Movies", 2, [])
    assert cache.get_records("Movies") == []
