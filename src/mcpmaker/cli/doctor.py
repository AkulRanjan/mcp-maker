"""`mcpmaker doctor`: check the whole chain, from the /mcp endpoint to each client's config."""

import asyncio
from dataclasses import dataclass
from typing import List, Optional

import typer

from mcpmaker.auth import parse_header
from mcpmaker.clients import all_adapters
from mcpmaker.configio import ConfigError, render_value
from mcpmaker.engine import probe


@dataclass
class Check:
    name: str
    status: str  # "OK" | "FAIL" | "--"
    detail: str = ""


def resolve_headers(raw: List[str]) -> dict:
    headers = {}
    for item in raw:
        try:
            name, value = parse_header(item)
            headers[name], _ = render_value(value, "literal")
        except ValueError:
            # Fixed text: the raw item may be a mis-typed secret, and a short line survives Rich's wrapping.
            raise typer.BadParameter("expected 'Name: value'", param_hint="--header")
        except ConfigError as exc:
            raise typer.BadParameter(str(exc), param_hint="--header")
    return headers


def run_checks(url: str, headers: dict, call: Optional[str]) -> List[Check]:
    checks: List[Check] = []
    result = asyncio.run(probe(url, headers, call_tool=call))
    if not result.connected:
        if result.status_code in (401, 403):
            fix = f"the endpoint answered HTTP {result.status_code}; check --header and any auth middleware in front of /mcp"
        else:
            fix = "is the app running? Check the URL - it should end with the mount path, e.g. /mcp"
        checks.append(Check("MCP server reachable", "FAIL", f"{result.error}. Fix: {fix}"))
    else:
        checks.append(Check("MCP server reachable", "OK", f"server '{result.server_name}'"))
        if result.tools:
            checks.append(Check("Tools exposed", "OK", f"{len(result.tools)} tools"))
        else:
            checks.append(Check(
                "Tools exposed", "FAIL",
                "0 tools. Fix: read the mcpmaker startup log - write routes are hidden unless "
                "include_writes=True or openapi_extra={'x-mcp': True}",
            ))
        if call:
            if result.call_ok:
                checks.append(Check(f"Call {call}", "OK"))
            else:
                checks.append(Check(
                    f"Call {call}", "FAIL",
                    f"{result.error or 'tool returned an error'}. Fix: check the tool name (see the tool list above / "
                    "mcpmaker startup log), that it takes no required arguments, and that --header is accepted by the route",
                ))

    for adapter in all_adapters():
        label = f"{adapter.display_name} configured"
        if not adapter.detect():
            checks.append(Check(label, "--", "not installed"))
            continue
        matches = {n: b for n, b in adapter.list_entries().items() if adapter.url_of(b) == url}
        if not matches:
            checks.append(Check(
                label, "FAIL", f"no entry points to {url}. Fix: mcpmaker connect --url {url} --client {adapter.name}"
            ))
            continue
        problems = [p for p in (adapter.check_entry(b) for b in matches.values()) if p]
        if problems:
            checks.append(Check(label, "FAIL", "; ".join(problems)))
        else:
            checks.append(Check(label, "OK", f"entry '{', '.join(matches)}'"))

    # Never let a header value reach the output (error text can echo request details).
    secrets = sorted({v for v in headers.values() if v}, key=len, reverse=True)
    for check in checks:
        for secret in secrets:
            check.detail = check.detail.replace(secret, "<redacted>")
    return checks


def echo_ascii(line: str) -> None:
    """Print a line that is safe for any console encoding (server-supplied text may be non-ASCII)."""
    typer.echo(line.encode("ascii", "replace").decode("ascii"))


def print_checks(checks: List[Check]) -> bool:
    for check in checks:
        line = f"{check.status:<4} {check.name}" + (f": {check.detail}" if check.detail else "")
        echo_ascii(line)
    return any(c.status == "FAIL" for c in checks)


def doctor(
    url: str = typer.Option(..., "--url", help="The MCP endpoint, e.g. http://localhost:8000/mcp"),
    header: Optional[List[str]] = typer.Option(None, "--header", "-H", help="'Name: value'; ${VAR} is read from the environment"),
    call: Optional[str] = typer.Option(None, "--call", help="Also call this no-argument tool"),
) -> None:
    """Check that the MCP server is reachable, exposes tools, and is wired into each AI client."""
    failed = print_checks(run_checks(url, resolve_headers(header or []), call))
    if failed:
        raise typer.Exit(1)
