"""`mcpmaker bridge`: stdio <-> HTTP relay for clients that only launch local processes."""

import os
import re
from typing import List, Mapping, Optional

import typer

from mcpmaker.auth import parse_header
from mcpmaker.engine import run_stdio_bridge

_HEADER_VAR = re.compile(r"^MCPMAKER_HEADER_(\d+)$")


def headers_from_env(environ: Mapping[str, str]) -> dict:
    numbered = sorted(
        (int(m.group(1)), value) for key, value in environ.items() if (m := _HEADER_VAR.match(key))
    )
    return dict(parse_header(value) for _, value in numbered)


def bridge(
    url: str = typer.Option(..., "--url", help="The MCP endpoint to relay to"),
    header: Optional[List[str]] = typer.Option(None, "--header", "-H", help="'Name: value' (also read from MCPMAKER_HEADER_<N>)"),
) -> None:
    """Relay MCP over stdio to an HTTP endpoint (used by Claude Desktop)."""
    headers = headers_from_env(os.environ)
    for item in header or []:
        try:
            key, value = parse_header(item)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--header")
        headers[key] = value
    run_stdio_bridge(url, headers)
