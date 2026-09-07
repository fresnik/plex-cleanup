"""Rendering of results as a Rich table, JSON, or CSV."""

from __future__ import annotations

import csv
import io
import json
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .models import AggregateRecord, MediaRecord
from .units import format_bitrate, format_size


class OutputFormat(str, Enum):
    tabular = "tabular"
    json = "json"
    csv = "csv"


CSV_FIELDS = [
    "library",
    "title",
    "file",
    "resolution",
    "bitrate_kbps",
    "size_bytes",
    "plays",
    "added_at",
    "rating_key",
]


def _records_table(records: list[MediaRecord], title: str) -> Table:
    table = Table(title=title, show_lines=False)
    table.add_column("Library", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Resolution", justify="center")
    table.add_column("Bitrate", justify="right")
    table.add_column("Size", justify="right", style="magenta")
    table.add_column("Plays", justify="right", style="green")
    table.add_column("File", style="dim", overflow="fold")
    for r in records:
        table.add_row(
            r.library,
            r.title,
            r.resolution or "-",
            format_bitrate(r.bitrate_kbps),
            format_size(r.size_bytes),
            str(r.plays),
            r.file,
        )
    return table


def _write(text: str, output: Path | None, console: Console) -> None:
    if output is None:
        # print() keeps raw formats byte-exact; console handles width for tables
        print(text)
    else:
        output.write_text(text + "\n", encoding="utf-8")
        console.print(f"[dim]Wrote output to {output}[/dim]")


def render_records(
    records: list[MediaRecord],
    fmt: OutputFormat,
    output: Path | None,
    console: Console,
    summary_verb: str = "found",
) -> None:
    total_size = sum(r.size_bytes or 0 for r in records)
    summary = f"{len(records)} file(s) {summary_verb}, {format_size(total_size)} total"

    if fmt is OutputFormat.json:
        payload = {
            "summary": {"count": len(records), "total_size_bytes": total_size},
            "results": [r.to_dict() for r in records],
        }
        _write(json.dumps(payload, indent=2), output, console)
        return

    if fmt is OutputFormat.csv:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in records:
            writer.writerow({k: v for k, v in r.to_dict().items() if k in CSV_FIELDS})
        _write(buf.getvalue().rstrip("\n"), output, console)
        return

    table = _records_table(records, title=f"Matches ({len(records)})")
    if output is None:
        out_console = Console()
        out_console.print(table)
        out_console.print(f"[bold]{summary}[/bold]")
    else:
        file_console = Console(file=io.StringIO(), width=200)
        file_console.print(table)
        file_console.print(summary)
        output.write_text(file_console.file.getvalue(), encoding="utf-8")
        console.print(f"[dim]Wrote output to {output}[/dim]")


AGGREGATE_CSV_FIELDS = [
    "library",
    "show",
    "season",
    "episodes",
    "files",
    "plays_min",
    "plays_max",
    "avg_bitrate_kbps",
    "avg_size_bytes",
    "total_size_bytes",
]


def _format_plays_range(agg: AggregateRecord) -> str:
    if agg.plays_min == agg.plays_max:
        return str(agg.plays_min)
    return f"{agg.plays_min}–{agg.plays_max}"


def _aggregates_table(aggs: list[AggregateRecord], level: str, title: str) -> Table:
    table = Table(title=title, show_lines=False)
    table.add_column("Library", style="cyan", no_wrap=True)
    table.add_column("Show", style="bold")
    if level == "season":
        table.add_column("Season", justify="right")
    table.add_column("Episodes", justify="right")
    table.add_column("Plays", justify="right", style="green")
    table.add_column("Avg Bitrate", justify="right")
    table.add_column("Avg Size", justify="right")
    table.add_column("Total Size", justify="right", style="magenta")
    for a in aggs:
        row = [a.library, a.show]
        if level == "season":
            row.append(str(a.season) if a.season is not None else "-")
        row.extend(
            [
                str(a.episodes),
                _format_plays_range(a),
                format_bitrate(a.avg_bitrate_kbps),
                format_size(a.avg_size_bytes),
                format_size(a.total_size_bytes),
            ]
        )
        table.add_row(*row)
    return table


def render_aggregates(
    aggs: list[AggregateRecord],
    level: str,
    fmt: OutputFormat,
    output: Path | None,
    console: Console,
) -> None:
    total_size = sum(a.total_size_bytes for a in aggs)
    noun = "show(s)" if level == "show" else "season(s)"
    summary = f"{len(aggs)} {noun} found, {format_size(total_size)} total"

    if fmt is OutputFormat.json:
        payload = {
            "summary": {"count": len(aggs), "total_size_bytes": total_size},
            "results": [a.to_dict() for a in aggs],
        }
        _write(json.dumps(payload, indent=2), output, console)
        return

    if fmt is OutputFormat.csv:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=AGGREGATE_CSV_FIELDS)
        writer.writeheader()
        for a in aggs:
            writer.writerow(a.to_dict())
        _write(buf.getvalue().rstrip("\n"), output, console)
        return

    table = _aggregates_table(aggs, level, title=f"Matches ({len(aggs)})")
    if output is None:
        out_console = Console()
        out_console.print(table)
        out_console.print(f"[bold]{summary}[/bold]")
    else:
        file_console = Console(file=io.StringIO(), width=200)
        file_console.print(table)
        file_console.print(summary)
        output.write_text(file_console.file.getvalue(), encoding="utf-8")
        console.print(f"[dim]Wrote output to {output}[/dim]")


def render_refresh_summary(
    results: list[dict],
    fmt: OutputFormat,
    output: Path | None,
    console: Console,
) -> None:
    """results: [{"file": ..., "status": "updated"|"unchanged"|"removed"}, ...]"""
    updated = sum(1 for r in results if r["status"] == "updated")
    unchanged = sum(1 for r in results if r["status"] == "unchanged")
    removed = sum(1 for r in results if r["status"] == "removed")
    summary = f"{updated} file(s) updated, {unchanged} unchanged, {removed} removed from cache"

    if fmt is OutputFormat.json:
        payload = {
            "summary": {"updated": updated, "unchanged": unchanged, "removed": removed},
            "results": results,
        }
        _write(json.dumps(payload, indent=2), output, console)
        return

    if fmt is OutputFormat.csv:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["file", "status"])
        writer.writeheader()
        writer.writerows(results)
        _write(buf.getvalue().rstrip("\n"), output, console)
        return

    # Unchanged files would drown out the interesting rows; they are only
    # counted in the summary line.
    changed = [r for r in results if r["status"] != "unchanged"]
    table = Table(title=f"Refreshed metadata ({len(results)} checked)")
    table.add_column("File", style="dim", overflow="fold")
    table.add_column("Status", justify="center")
    for r in changed:
        style = "green" if r["status"] == "updated" else "red"
        table.add_row(r["file"], f"[{style}]{r['status']}[/{style}]")
    if output is None:
        out_console = Console()
        out_console.print(table)
        out_console.print(f"[bold]{summary}[/bold]")
    else:
        file_console = Console(file=io.StringIO(), width=200)
        file_console.print(table)
        file_console.print(summary)
        output.write_text(file_console.file.getvalue(), encoding="utf-8")
        console.print(f"[dim]Wrote output to {output}[/dim]")
