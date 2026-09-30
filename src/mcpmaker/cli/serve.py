"""`mcpmaker serve`: expose any OpenAPI-described API as an MCP server."""

from typing import List, Optional

import typer
import uvicorn

from mcpmaker.cli.doctor import echo_ascii
from mcpmaker.standalone import build_standalone_app, load_spec


def serve(
    spec: str = typer.Argument(..., help="OpenAPI JSON/YAML file path or URL"),
    base_url: str = typer.Option(..., "--base-url", help="Where the real API lives, e.g. https://api.example.com"),
    include_writes: bool = typer.Option(False, "--include-writes", help="Also expose POST/PUT/PATCH/DELETE"),
    exclude: Optional[List[str]] = typer.Option(None, "--exclude", help="Path glob to hide, e.g. '/admin/*'"),
    forward_header: Optional[List[str]] = typer.Option(None, "--forward-header", help="Extra header name to pass through"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    path: str = typer.Option("/mcp", "--path"),
) -> None:
    """Run a standalone MCP server that proxies tool calls to an existing HTTP API."""
    try:
        document = load_spec(spec)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="SPEC")
    app, report = build_standalone_app(
        document,
        base_url=base_url,
        include_writes=include_writes,
        exclude=exclude or [],
        forward_headers=forward_header or [],
        path=path,
    )
    for line in report.format().splitlines():
        echo_ascii(line)
    echo_ascii(f"MCP endpoint: http://{host}:{port}{path}")
    uvicorn.run(app, host=host, port=port)
