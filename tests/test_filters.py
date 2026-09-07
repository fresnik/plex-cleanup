from plex_cleanup.filters import SearchFilters, apply_filters, matches
from plex_cleanup.models import resolution_ordinal

from .conftest import make_record


def test_no_filters_matches_everything():
    assert matches(make_record(), SearchFilters())


def test_plays_range():
    record = make_record(plays=3)
    assert matches(record, SearchFilters(min_plays=3))
    assert not matches(record, SearchFilters(min_plays=4))
    assert matches(record, SearchFilters(max_plays=3))
    assert not matches(record, SearchFilters(max_plays=2))


def test_zero_plays_and_none_plays():
    assert matches(make_record(plays=0), SearchFilters(max_plays=0))
    assert matches(make_record(plays=None), SearchFilters(max_plays=0))


def test_bitrate_range():
    record = make_record(bitrate_kbps=5000)
    assert matches(record, SearchFilters(min_bitrate=5000, max_bitrate=5000))
    assert not matches(record, SearchFilters(min_bitrate=5001))
    assert not matches(record, SearchFilters(max_bitrate=4999))


def test_unknown_value_excluded_when_filter_active():
    record = make_record(bitrate_kbps=None, size_bytes=None, resolution=None)
    assert matches(record, SearchFilters())
    assert not matches(record, SearchFilters(min_bitrate=1))
    assert not matches(record, SearchFilters(max_size=10**9))
    assert not matches(record, SearchFilters(min_resolution="sd"))


def test_size_range():
    record = make_record(size_bytes=1024**3)
    assert matches(record, SearchFilters(min_size=1024**3, max_size=1024**3))
    assert not matches(record, SearchFilters(min_size=1024**3 + 1))


def test_resolution_ladder_ordering():
    order = [resolution_ordinal(v) for v in ["sd", "480", "576", "720", "1080", "4k"]]
    assert order == sorted(order)
    assert resolution_ordinal("4K") == resolution_ordinal("4k")
    assert resolution_ordinal("weird") is None


def test_resolution_range():
    sd = make_record(resolution="sd")
    hd = make_record(resolution="1080")
    uhd = make_record(resolution="4k")
    filters = SearchFilters(min_resolution="720", max_resolution="1080")
    assert not matches(sd, filters)
    assert matches(hd, filters)
    assert not matches(uhd, filters)
    # 576 sits between 480 and 720
    assert matches(make_record(resolution="576"), SearchFilters(max_resolution="720"))
    assert not matches(make_record(resolution="576"), SearchFilters(min_resolution="720"))


def test_apply_filters():
    records = [make_record(plays=0), make_record(plays=5)]
    assert len(apply_filters(records, SearchFilters(max_plays=0))) == 1
