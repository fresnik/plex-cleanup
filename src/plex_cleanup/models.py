"""Data model for cached media file metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields

# Ordinal ladder used for resolution comparisons. 576 is not offered as a CLI
# choice but Plex reports it, so it needs a slot between 480 and 720.
_RESOLUTION_ORDER = {"sd": 0, "480": 1, "576": 2, "720": 3, "1080": 4, "4k": 5}

# User-facing choices, smallest to largest.
RESOLUTION_CHOICES = ["sd", "480", "720", "1080", "4K"]


def resolution_ordinal(value: str | None) -> int | None:
    """Map a Plex videoResolution string to a comparable ordinal."""
    if value is None:
        return None
    return _RESOLUTION_ORDER.get(str(value).strip().lower())


@dataclass
class MediaRecord:
    """Metadata for a single media file (one Plex media part)."""

    library: str
    title: str
    rating_key: int
    file: str
    size_bytes: int | None
    bitrate_kbps: int | None
    resolution: str | None
    plays: int
    added_at: str | None
    # Structured show/season info for episodes; None for movies and tracks.
    # Defaulted so records cached before these fields existed still load.
    show: str | None = None
    season: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MediaRecord":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})
