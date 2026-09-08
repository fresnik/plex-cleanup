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
        plays_total=0,
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
    agg = make_aggregate(season=2, plays_max=3, plays_total=7)
    text = render_to_file([agg], "season", OutputFormat.csv, tmp_path)
    (row,) = list(csv.DictReader(io.StringIO(text)))
    assert row["show"] == "Example Show"
    assert row["season"] == "2"
    assert row["plays_min"] == "0"
    assert row["plays_max"] == "3"
    assert row["plays_total"] == "7"
    assert row["total_size_bytes"] == str(20 * 1024**3)


def test_render_aggregates_tabular_total_plays(tmp_path):
    agg = make_aggregate(plays_min=1, plays_max=4, plays_total=23)
    text = render_to_file([agg], "show", OutputFormat.tabular, tmp_path)
    assert "23" in text
    assert "1–4" not in text  # the min–max range column is gone
    assert "1 show(s) found" in text


def test_render_aggregates_tabular_season_column_and_noun(tmp_path):
    agg = make_aggregate(season=1)
    text = render_to_file([agg], "season", OutputFormat.tabular, tmp_path)
    assert "Season" in text
    assert "1 season(s) found" in text
