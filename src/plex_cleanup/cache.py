"""Local JSON cache of media metadata, keyed by library."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .models import MediaRecord

CACHE_VERSION = 1


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME", "")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "plex-cleanup" / "cache.json"


class Cache:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict = {"version": CACHE_VERSION, "libraries": {}}

    @classmethod
    def load(cls, path: Path) -> "Cache":
        cache = cls(path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("version") == CACHE_VERSION:
                cache._data = data
        return cache

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def library_names(self) -> list[str]:
        return list(self._data["libraries"].keys())

    def has_library(self, name: str) -> bool:
        return name in self._data["libraries"]

    def get_records(self, library: str) -> list[MediaRecord]:
        entry = self._data["libraries"].get(library)
        if not entry:
            return []
        return [MediaRecord.from_dict(d) for d in entry["records"]]

    def set_records(self, library: str, records: list[MediaRecord]) -> None:
        self._data["libraries"][library] = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "records": [r.to_dict() for r in records],
        }

    def all_records(self) -> list[MediaRecord]:
        records: list[MediaRecord] = []
        for name in self.library_names:
            records.extend(self.get_records(name))
        return records

    def replace_item_records(
        self, library: str, rating_key: int, new_records: list[MediaRecord]
    ) -> None:
        """Replace all records for one Plex item within a library."""
        entry = self._data["libraries"].get(library)
        if not entry:
            return
        kept = [d for d in entry["records"] if d.get("rating_key") != rating_key]
        kept.extend(r.to_dict() for r in new_records)
        entry["records"] = kept
