from plex_cleanup.models import MediaRecord
from plex_cleanup.server import apply_play_counts, fetch_play_counts, records_for_item

from .conftest import make_record


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

    def __init__(self, rating_key, show, season, episode_title, file, index=None):
        self.ratingKey = rating_key
        self.grandparentTitle = show
        self.parentIndex = season
        self.index = index
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


def test_string_parent_index_coerced_to_int():
    item = FakeEpisode(12, "Example Show", 3, "Pilot", "/tv/show/s03e01.mkv")
    item.parentIndex = "3"
    (record,) = list(records_for_item(item, "TV"))
    assert record.season == 3


class FakeHistoryEntry:
    def __init__(self, type=None, rating_key=None, account_id=1, title=None,
                 grandparent=None, parent_index=None, index=None):
        if type is not None:
            self.type = type
        if rating_key is not None:
            self.ratingKey = rating_key
        if title is not None:
            self.title = title
        if grandparent is not None:
            self.grandparentTitle = grandparent
        if parent_index is not None:
            self.parentIndex = parent_index
        if index is not None:
            self.index = index
        self.accountID = account_id


class FakeHistoryServer:
    def __init__(self, entries):
        self._entries = entries

    def history(self, maxresults=None):
        return self._entries


def test_fetch_play_counts_keys_episodes_by_identity_not_rating_key():
    # After a delete/re-add Plex can point every old history row's ratingKey
    # at one arbitrary surviving episode; the stored show/season/index fields
    # keep the true identity.
    server = FakeHistoryServer(
        [
            FakeHistoryEntry("episode", rating_key=163277, grandparent="Elementary",
                             parent_index=6, index=20, title="Fit to Be Tied"),
            FakeHistoryEntry("episode", rating_key=163277, grandparent="Elementary",
                             parent_index="6", index="21", account_id=42),
        ]
    )
    counts = fetch_play_counts(server)
    assert counts == {
        ("episode", "elementary", 6, 20): 1,
        ("episode", "elementary", 6, 21): 1,
    }


def test_fetch_play_counts_movies_by_title_and_fallback_by_key():
    server = FakeHistoryServer(
        [
            FakeHistoryEntry("movie", rating_key=1, title="Heat"),
            FakeHistoryEntry("movie", rating_key=2, title="heat "),  # same movie
            FakeHistoryEntry(rating_key="7"),  # no type/identity: key fallback
            FakeHistoryEntry(),  # nothing usable: skipped
        ]
    )
    assert fetch_play_counts(server) == {("movie", "heat"): 2, ("key", 7): 1}


def test_apply_play_counts_matches_episodes_by_identity():
    watched = make_record(rating_key=163400, show="Elementary", season=6, episode=20,
                          plays=0)
    relinked_to = make_record(rating_key=163277, show="Elementary", season=4, episode=1,
                              plays=0)
    counts = {("episode", "elementary", 6, 20): 3}
    apply_play_counts([watched, relinked_to], counts)
    assert watched.plays == 3
    # the episode the stale ratingKey points at must NOT inherit those plays
    assert relinked_to.plays == 0


def test_apply_play_counts_movies_by_title_and_key_fallback():
    records = [
        make_record(rating_key=1, title="Heat", plays=0),
        make_record(rating_key=2, title="Alien", plays=5),  # owner plays kept (max)
        make_record(rating_key=7, title="Keyed Only", plays=None),
        make_record(rating_key=9, title="Unwatched", plays=0),
    ]
    counts = {("movie", "heat"): 2, ("movie", "alien"): 1, ("key", 7): 4}
    apply_play_counts(records, counts)
    assert [r.plays for r in records] == [2, 5, 4, 0]


def test_episode_records_carry_episode_number():
    item = FakeEpisode(10, "Example Show", 2, "Pilot", "/tv/show/s02e01.mkv", index="5")
    (record,) = list(records_for_item(item, "TV"))
    assert record.episode == 5


def test_old_cache_dict_without_new_fields_loads_with_none():
    data = dict(
        library="TV", title="T", rating_key=1, file="/f.mkv",
        size_bytes=1, bitrate_kbps=1, resolution="1080", plays=0, added_at=None,
    )
    record = MediaRecord.from_dict(data)
    assert record.show is None
    assert record.season is None
