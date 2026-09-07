"""Parsing and formatting of human-readable sizes."""

from __future__ import annotations

import re

_UNIT_FACTORS = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "m": 1024**2,
    "mb": 1024**2,
    "g": 1024**3,
    "gb": 1024**3,
    "t": 1024**4,
    "tb": 1024**4,
}

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)\s*$")


def parse_size(text: str) -> int:
    """Parse a human size like '500MB', '1.5GB', or '1048576' into bytes."""
    match = _SIZE_RE.match(text)
    if not match:
        raise ValueError(f"invalid size: {text!r}")
    number, unit = match.groups()
    factor = _UNIT_FACTORS.get(unit.lower())
    if factor is None:
        raise ValueError(f"invalid size unit: {unit!r} (use B, KB, MB, GB, or TB)")
    return int(float(number) * factor)


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "-"
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_bitrate(bitrate_kbps: int | None) -> str:
    if bitrate_kbps is None:
        return "-"
    if bitrate_kbps >= 1000:
        return f"{bitrate_kbps / 1000:.1f} Mbps"
    return f"{bitrate_kbps} kbps"
