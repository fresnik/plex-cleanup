"""plex-cleanup CLI: search for cleanup candidates and refresh cached metadata."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from . import server as plex
from .cache import Cache, default_cache_path
from .filters import SearchFilters, apply_filters
from .output import OutputFormat, render_records, render_refresh_summary
from .units import parse_size

# Populate PLEX_URL/PLEX_TOKEN/PLEX_CLEANUP_CACHE from a .env file before
# Typer resolves envvar-backed options. The file is searched from the working
# directory upward; real environment variables win over .env values.
load_dotenv(find_dotenv(usecwd=True))

app = typer.Typer(
    help="Find cleanup candidates in a Plex media library.",
    no_args_is_help=True,
)

# Status/progress goes to stderr so stdout stays clean for json/csv piping.
err_console = Console(stderr=True)


class Resolution(str, Enum):
    sd = "sd"
    p480 = "480"
    p720 = "720"
    p1080 = "1080"
    uhd = "4K"


def _parse_size_option(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return parse_size(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


URL_OPTION = typer.Option(
    None, "--url", envvar="PLEX_URL", help="Plex server URL, e.g. http://plex:32400."
)
TOKEN_OPTION = typer.Option(
    None, "--token", envvar="PLEX_TOKEN", help="Plex authentication token."
)
CACHE_OPTION = typer.Option(
    None,
    "--cache-file",
    envvar="PLEX_CLEANUP_CACHE",
    help="Metadata cache file (default: ~/.cache/plex-cleanup/cache.json).",
)
FORMAT_OPTION = typer.Option(
    OutputFormat.tabular, "--format", "-f", case_sensitive=False, help="Output format."
)
OUTPUT_OPTION = typer.Option(
    None, "--output", "-o", help="Write output to this file instead of stdout."
)


def _connect(url: Optional[str], token: Optional[str]):
    if not url or not token:
        err_console.print(
            "[red]Error:[/red] Plex connection required. "
            "Set --url/--token or the PLEX_URL/PLEX_TOKEN environment variables."
        )
        raise typer.Exit(code=1)
    try:
        return plex.connect(url, token)
    except Exception as exc:
        err_console.print(f"[red]Error:[/red] could not connect to Plex at {url}: {exc}")
        raise typer.Exit(code=1)


def _progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=err_console,
    )


def _scan_section(section, progress: Progress) -> list:
    listing = progress.add_task(f"Listing items in [cyan]{section.title}[/cyan]", total=None)
    items = plex.fetch_items(section)
    progress.remove_task(listing)

    task = progress.add_task(f"Scanning [cyan]{section.title}[/cyan]", total=len(items))
    records = []
    for item in items:
        records.extend(plex.records_for_item(item, section.title))
        progress.advance(task)
    return records


@app.command()
def search(
    library: list[str] = typer.Option(
        ...,
        "--library",
        "-l",
        help="Library to search (repeat for several), or 'all' for every library.",
    ),
    min_plays: Optional[int] = typer.Option(None, min=0, help="Minimum number of plays."),
    max_plays: Optional[int] = typer.Option(None, min=0, help="Maximum number of plays."),
    min_bitrate: Optional[int] = typer.Option(None, min=0, help="Minimum bitrate in kbps."),
    max_bitrate: Optional[int] = typer.Option(None, min=0, help="Maximum bitrate in kbps."),
    min_size: Optional[str] = typer.Option(None, help="Minimum file size, e.g. 500MB or 1.5GB."),
    max_size: Optional[str] = typer.Option(None, help="Maximum file size, e.g. 4GB."),
    min_resolution: Optional[Resolution] = typer.Option(
        None, case_sensitive=False, help="Minimum resolution."
    ),
    max_resolution: Optional[Resolution] = typer.Option(
        None, case_sensitive=False, help="Maximum resolution."
    ),
    format: OutputFormat = FORMAT_OPTION,
    output: Optional[Path] = OUTPUT_OPTION,
    url: Optional[str] = URL_OPTION,
    token: Optional[str] = TOKEN_OPTION,
    cache_file: Optional[Path] = CACHE_OPTION,
):
    """Search cached library metadata for files matching the given filters.

    Libraries not yet in the local cache are scanned from the Plex server
    first; subsequent searches run entirely from the cache.
    """
    cache = Cache.load(cache_file or default_cache_path())
    server = None

    def get_server():
        nonlocal server
        if server is None:
            server = _connect(url, token)
        return server

    # Resolve requested library names ('all' needs the server to enumerate).
    if any(name.lower() == "all" for name in library):
        wanted = [s.title for s in plex.supported_sections(get_server())]
    else:
        wanted = library

    records = []
    to_scan = []
    for name in wanted:
        if cache.has_library(name):
            records.extend(cache.get_records(name))
        else:
            to_scan.append(name)

    if to_scan:
        srv = get_server()
        sections = []
        for name in to_scan:
            try:
                section = srv.library.section(name)
            except Exception:
                available = ", ".join(s.title for s in plex.supported_sections(srv))
                err_console.print(
                    f"[red]Error:[/red] library {name!r} not found on server. "
                    f"Available: {available}"
                )
                raise typer.Exit(code=1)
            if section.type not in plex.SUPPORTED_SECTION_LIBTYPES:
                err_console.print(
                    f"[yellow]Skipping {name!r}: unsupported library type "
                    f"{section.type!r}.[/yellow]"
                )
                continue
            sections.append(section)

        with _progress() as progress:
            for section in sections:
                scanned = _scan_section(section, progress)
                cache.set_records(section.title, scanned)
                # Persist after each library so an interrupted run keeps
                # everything that finished scanning.
                cache.save()
                records.extend(scanned)

    filters = SearchFilters(
        min_plays=min_plays,
        max_plays=max_plays,
        min_bitrate=min_bitrate,
        max_bitrate=max_bitrate,
        min_size=_parse_size_option(min_size),
        max_size=_parse_size_option(max_size),
        min_resolution=min_resolution.value if min_resolution else None,
        max_resolution=max_resolution.value if max_resolution else None,
    )
    matched = apply_filters(records, filters)
    matched.sort(key=lambda r: r.size_bytes or 0, reverse=True)
    render_records(matched, format, output, err_console, summary_verb="found")


@app.command("refresh-metadata")
def refresh_metadata(
    files: Optional[list[str]] = typer.Argument(
        None, help="File paths to refresh. Omit to refresh every cached file."
    ),
    format: OutputFormat = FORMAT_OPTION,
    output: Optional[Path] = OUTPUT_OPTION,
    url: Optional[str] = URL_OPTION,
    token: Optional[str] = TOKEN_OPTION,
    cache_file: Optional[Path] = CACHE_OPTION,
):
    """Re-fetch metadata from the Plex server and update the local cache.

    Items that no longer exist on the server are removed from the cache.
    """
    from plexapi.exceptions import NotFound

    cache = Cache.load(cache_file or default_cache_path())
    records = cache.all_records()
    if not records:
        err_console.print(
            "[yellow]Cache is empty — run 'plex-cleanup search' first.[/yellow]"
        )
        raise typer.Exit(code=1)

    if files:
        wanted_files = set(files)
        selected = [r for r in records if r.file in wanted_files]
        missing = wanted_files - {r.file for r in selected}
        for path in sorted(missing):
            err_console.print(f"[yellow]Not in cache, skipping:[/yellow] {path}")
        if not selected:
            err_console.print("[red]Error:[/red] none of the given files are in the cache.")
            raise typer.Exit(code=1)
    else:
        selected = records

    # One fetch per Plex item, even when an item has several files.
    groups: dict[tuple[str, int], list] = {}
    for record in selected:
        groups.setdefault((record.library, record.rating_key), []).append(record)

    # All cached records per item, for change detection. Refreshing an item
    # replaces every file it has cached, not just the ones selected.
    item_files: dict[tuple[str, int], dict] = {}
    for record in cache.all_records():
        item_files.setdefault((record.library, record.rating_key), {})[record.file] = record

    server = _connect(url, token)
    results: list[dict] = []
    with _progress() as progress:
        task = progress.add_task("Refreshing metadata", total=len(groups))
        for (library, rating_key) in groups:
            cached = item_files.get((library, rating_key), {})
            try:
                item = server.fetchItem(rating_key)
            except NotFound:
                cache.replace_item_records(library, rating_key, [])
                results.extend({"file": f, "status": "removed"} for f in cached)
            else:
                new_records = list(plex.records_for_item(item, library))
                cache.replace_item_records(library, rating_key, new_records)
                new_files = set()
                for record in new_records:
                    new_files.add(record.file)
                    status = "unchanged" if cached.get(record.file) == record else "updated"
                    results.append({"file": record.file, "status": status})
                results.extend(
                    {"file": f, "status": "removed"} for f in cached if f not in new_files
                )
            progress.advance(task)
    cache.save()

    render_refresh_summary(results, format, output, err_console)


if __name__ == "__main__":
    app()
