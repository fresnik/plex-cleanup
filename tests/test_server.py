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


def test_string_parent_index_coerced_to_int():
    item = FakeEpisode(12, "Example Show", 3, "Pilot", "/tv/show/s03e01.mkv")
    item.parentIndex = "3"
    (record,) = list(records_for_item(item, "TV"))
    assert record.season == 3


def test_old_cache_dict_without_new_fields_loads_with_none():
    data = dict(
        library="TV", title="T", rating_key=1, file="/f.mkv",
        size_bytes=1, bitrate_kbps=1, resolution="1080", plays=0, added_at=None,
    )
    record = MediaRecord.from_dict(data)
    assert record.show is None
    assert record.season is None
