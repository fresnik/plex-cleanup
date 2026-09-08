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
    is_episode = item.type == "episode"
    show = getattr(item, "grandparentTitle", None) if is_episode else None
    season = getattr(item, "parentIndex", None) if is_episode else None
    episode = getattr(item, "index", None) if is_episode else None
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
                show=show,
                season=int(season) if season is not None else None,
                episode=int(episode) if episode is not None else None,
            )


def records_for_items(items: Iterable, library: str) -> Iterator[MediaRecord]:
    for item in items:
        yield from records_for_item(item, library)


def _normalize_title(value) -> str:
    return " ".join(str(value).split()).lower()


def _entry_identity(entry) -> tuple | None:
    """Grouping key for a history entry.

    History rows are keyed by what they say they are (show/season/episode, or
    movie title), not by ratingKey: when an item is deleted and re-added,
    Plex re-points old rows' ratingKey at an arbitrary surviving item, while
    the stored display fields keep the true identity. ratingKey is only used
    for entries carrying no identity at all (e.g. tracks, stripped rows).
    """
    etype = getattr(entry, "type", None)
    if etype == "episode":
        show = getattr(entry, "grandparentTitle", None)
        season = getattr(entry, "parentIndex", None)
        index = getattr(entry, "index", None)
        if show is not None and season is not None and index is not None:
            return ("episode", _normalize_title(show), int(season), int(index))
    if etype == "movie":
        title = getattr(entry, "title", None)
        if title:
            return ("movie", _normalize_title(title))
    key = getattr(entry, "ratingKey", None)
    return ("key", int(key)) if key is not None else None


def fetch_play_counts(server) -> dict[tuple, int]:
    """Play counts across ALL server accounts, keyed by media identity.

    An item's viewCount is scoped to the token's account, so plays by other
    home/shared users are invisible to it. The watch-history endpoint (which
    an admin token sees for every account) also records partial plays that
    never crossed Plex's watched threshold.
    """
    counts: dict[tuple, int] = {}
    for entry in server.history():
        identity = _entry_identity(entry)
        if identity is None:
            continue
        counts[identity] = counts.get(identity, 0) + 1
    return counts


def apply_play_counts(records: Iterable[MediaRecord], counts: dict[tuple, int]) -> None:
    """Raise each record's plays to its all-accounts history count.

    max() rather than a sum: the owner's completed plays appear in both
    viewCount and the history, while plays older than the server's history
    retention exist only in viewCount.
    """
    for record in records:
        history = counts.get(("key", record.rating_key), 0)
        if record.show is not None and record.season is not None and record.episode is not None:
            identity = ("episode", _normalize_title(record.show), record.season, record.episode)
        else:
            # Movie titles are stored as-is; composite episode/track titles
            # simply never match a movie entry.
            identity = ("movie", _normalize_title(record.title))
        history = max(history, counts.get(identity, 0))
        record.plays = max(record.plays or 0, history)
