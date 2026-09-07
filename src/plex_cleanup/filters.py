"""Filtering of cached media records."""

from __future__ import annotations

from dataclasses import dataclass

from .models import MediaRecord, resolution_ordinal


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
