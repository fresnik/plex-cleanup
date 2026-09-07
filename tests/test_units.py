import pytest

from plex_cleanup.units import format_bitrate, format_size, parse_size


def test_parse_plain_bytes():
    assert parse_size("1048576") == 1048576


def test_parse_units():
    assert parse_size("500MB") == 500 * 1024**2
    assert parse_size("1.5GB") == int(1.5 * 1024**3)
    assert parse_size("2 tb") == 2 * 1024**4
    assert parse_size("10kb") == 10 * 1024


@pytest.mark.parametrize("bad", ["", "abc", "10XB", "-5GB"])
def test_parse_invalid(bad):
    with pytest.raises(ValueError):
        parse_size(bad)


def test_format_size():
    assert format_size(None) == "-"
    assert format_size(512) == "512 B"
    assert format_size(4 * 1024**3) == "4.0 GB"


def test_format_bitrate():
    assert format_bitrate(None) == "-"
    assert format_bitrate(800) == "800 kbps"
    assert format_bitrate(8000) == "8.0 Mbps"
