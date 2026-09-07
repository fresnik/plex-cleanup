from plex_cleanup.filters import SearchFilters, aggregate, apply_filters, matches
from plex_cleanup.models import resolution_ordinal

from .conftest import make_episode, make_record


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
