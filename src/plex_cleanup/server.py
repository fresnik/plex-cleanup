"""Plex server access and metadata extraction."""

from __future__ import annotations

from typing import Iterable, Iterator

from .models import MediaRecord

# Section types we can extract file metadata from, and the item type to
# enumerate within each (movie sections are enumerated directly).
SUPPORTED_SECTION_LIBTYPES = {"movie": None, "show": "episode", "artist": "track"}


def connect(url: str, token: str):
    from plexapi.server import PlexServer

    return PlexServer(url, token)


def supported_sections(server) -> list:
    return [
        s for s in server.library.sections() if s.type in SUPPORTED_SECTION_LIBTYPES
    ]


def fetch_items(section) -> list:
    """All file-bearing items in a section (movies, episodes, or tracks)."""
    libtype = SUPPORTED_SECTION_LIBTYPES[section.type]
    if libtype is None:
        return section.all()
    return section.search(libtype=libtype)


def display_title(item) -> str:
    if item.type == "episode":
        code = getattr(item, "seasonEpisode", "") or ""
        return f"{item.grandparentTitle} - {code.upper()} - {item.title}".strip(" -")
    if item.type == "track":
        return f"{item.grandparentTitle} - {item.title}"
    return item.title


def records_for_item(item, library: str) -> Iterator[MediaRecord]:
    """One record per media file (part) of a Plex item."""
    plays = getattr(item, "viewCount", 0) or 0
    added_at = getattr(item, "addedAt", None)
    title = display_title(item)
    for media in item.media or []:
        for part in media.parts or []:
            if not part.file:
                continue
            yield MediaRecord(
                library=library,
                title=title,
                rating_key=int(item.ratingKey),
                file=part.file,
                size_bytes=part.size,
                bitrate_kbps=media.bitrate,
                resolution=getattr(media, "videoResolution", None),
                plays=plays,
                added_at=added_at.isoformat() if added_at else None,
            )


def records_for_items(items: Iterable, library: str) -> Iterator[MediaRecord]:
    for item in items:
        yield from records_for_item(item, library)
