import pytest

from plex_cleanup.models import MediaRecord


def make_record(**overrides) -> MediaRecord:
    defaults = dict(
        library="Movies",
        title="Example Movie",
        rating_key=101,
        file="/media/movies/example.mkv",
        size_bytes=4 * 1024**3,
        bitrate_kbps=8000,
        resolution="1080",
        plays=2,
        added_at="2024-01-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    return MediaRecord(**defaults)


@pytest.fixture
def record_factory():
    return make_record
