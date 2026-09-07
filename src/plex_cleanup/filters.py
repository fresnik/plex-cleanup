"""Filtering of cached media records."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AggregateRecord, MediaRecord, resolution_ordinal


@dataclass
class SearchFilters:
    min_plays: int | None = None
    max_plays: int | None = None
    min_bitrate: int | None = None
    max_bitrate: int | None = None
    min_size: int | None = None
    max_size: int | None = None
    min_resolution: str | None = None
    max_resolution: str | None = None


def matches(record: MediaRecord, filters: SearchFilters) -> bool:
    """True if the record passes every active filter.

    A record with an unknown value (None) is excluded when a filter on that
    field is active, since the constraint cannot be verified.
    """
    plays = record.plays or 0
    if filters.min_plays is not None and plays < filters.min_plays:
        return False
    if filters.max_plays is not None and plays > filters.max_plays:
        return False

    if filters.min_bitrate is not None and (
        record.bitrate_kbps is None or record.bitrate_kbps < filters.min_bitrate
    ):
        return False
    if filters.max_bitrate is not None and (
        record.bitrate_kbps is None or record.bitrate_kbps > filters.max_bitrate
    ):
        return False

    if filters.min_size is not None and (
        record.size_bytes is None or record.size_bytes < filters.min_size
    ):
        return False
    if filters.max_size is not None and (
        record.size_bytes is None or record.size_bytes > filters.max_size
    ):
        return False

    ordinal = resolution_ordinal(record.resolution)
    if filters.min_resolution is not None:
        minimum = resolution_ordinal(filters.min_resolution)
        if ordinal is None or ordinal < minimum:
            return False
    if filters.max_resolution is not None:
        maximum = resolution_ordinal(filters.max_resolution)
        if ordinal is None or ordinal > maximum:
            return False

    return True


def apply_filters(records: list[MediaRecord], filters: SearchFilters) -> list[MediaRecord]:
    return [r for r in records if matches(r, filters)]


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
