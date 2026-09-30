"""`mcpmaker connect`: register the MCP server with every installed AI client."""

import asyncio
import re
from typing import List, Optional

import typer

from mcpmaker.auth import parse_header
from mcpmaker.cli.doctor import echo_ascii, print_checks, run_checks
from mcpmaker.clients import all_adapters
from mcpmaker.clients.base import ServerEntry
from mcpmaker.configio import ConfigError, render_value
from mcpmaker.engine import probe

DEFAULT_NAME = "api"
MARKERS = {"installed": "OK", "replaced": "OK", "skipped": "--", "failed": "FAIL"}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or DEFAULT_NAME


def _resolved(raw_headers: dict) -> dict:
    """Header values with ${VAR} expanded, for talking to the server now. Unset vars are dropped."""
    out = {}
    for name, value in raw_headers.items():
        try:
            out[name], _ = render_value(value, "literal")
        except ConfigError:
            pass
    return out


def connect(
    url: str = typer.Option(..., "--url", help="The MCP endpoint, e.g. http://localhost:8000/mcp"),
    header: Optional[List[str]] = typer.Option(None, "--header", "-H", help="'Name: value'; use ${VAR} to keep secrets in env vars"),
    name: Optional[str] = typer.Option(None, "--name", help="Server name in client configs (default: from the server)"),
    client: Optional[List[str]] = typer.Option(None, "--client", help="Only these clients (repeatable)"),
    all_: bool = typer.Option(False, "--all", help="Set up every detected client without asking"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't prompt; replace existing entries"),
    force: bool = typer.Option(False, "--force", help="Overwrite config files that aren't valid JSON (a .bak is kept)"),
) -> None:
    """Add this MCP server to Claude Code, Cursor, VS Code, Windsurf, and Claude Desktop."""
    raw_headers = {}
    for item in header or []:
        try:
            key, value = parse_header(item)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--header")
        raw_headers[key] = value

    if name is None:
        found = asyncio.run(probe(url, _resolved(raw_headers)))
        if found.connected and found.server_name:
            name = slugify(found.server_name)
        else:
            name = DEFAULT_NAME
            echo_ascii(f"note: {url} is not reachable right now; using server name '{name}' (pass --name to choose)")
    entry = ServerEntry(name=name, url=url, headers=raw_headers)

    adapters = all_adapters()
    if client:
        by_name = {a.name: a for a in adapters}
        unknown = [c for c in client if c not in by_name]
        if unknown:
            raise typer.BadParameter(
                f"unknown client(s): {', '.join(unknown)}. Known: {', '.join(by_name)}", param_hint="--client"
            )
        chosen = [by_name[c] for c in client]
    else:
        echo_ascii("Detected AI clients:")
        detected = []
        for adapter in adapters:
            found_client = adapter.detect()
            echo_ascii(f"  {'OK' if found_client else '--':<4} {adapter.display_name}" + ("" if found_client else " (not installed)"))
            if found_client:
                detected.append(adapter)
        if not detected:
            echo_ascii("No supported AI clients found. Use --client <name> to write a config anyway.")
            raise typer.Exit(1)
        if all_ or yes:
            chosen = detected
        else:
            chosen = [a for a in detected if typer.confirm(f"Set up {a.display_name}?", default=True)]

    failed = False
    for adapter in chosen:
        replace = yes
        if not yes and name in adapter.list_entries():
            replace = typer.confirm(f"{adapter.display_name} already has a server named '{name}'. Replace it?", default=False)
        result = adapter.install(entry, replace=replace, force=force)
        echo_ascii(f"{MARKERS[result.status]:<4} {adapter.display_name}: {result.status}" + (f" ({result.path})" if result.path else ""))
        if result.message:
            echo_ascii(f"     {result.message}")
        if result.status in ("installed", "replaced"):
            echo_ascii(f"     next: {adapter.reload_hint}")
        failed = failed or result.status == "failed"

    if not yes and typer.confirm("Run mcpmaker doctor now?", default=True):
        print_checks(run_checks(url, _resolved(raw_headers), None))
    if failed:
        raise typer.Exit(1)
