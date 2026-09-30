"""Build a standalone MCP server from an OpenAPI document (for APIs whose code you don't control)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx
import yaml

from mcpmaker.auth import PassThroughAuth
from mcpmaker.engine import build_server, make_api_client
from mcpmaker.policy import ensure_operation_ids, operations_from_spec, select_operations
from mcpmaker.report import MountReport


def load_spec(source: str) -> dict[str, Any]:
    try:
        if source.startswith(("http://", "https://")):
            response = httpx.get(source, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            text = response.text
        else:
            text = Path(source).read_text(encoding="utf-8-sig")
    except (OSError, httpx.HTTPError, httpx.InvalidURL) as exc:
        raise ValueError(f"cannot read {source}: {type(exc).__name__}: {exc}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            raise ValueError(f"{source} is not valid JSON or YAML") from None
    if not isinstance(data, dict) or not isinstance(data.get("paths"), dict):
        raise ValueError(f"{source} does not look like an OpenAPI document (no 'paths' object)")
    return data


def build_standalone_app(
    spec: Mapping[str, Any],
    *,
    base_url: str,
    name: str | None = None,
    include_writes: bool = False,
    exclude: Sequence[str] = (),
    forward_headers: Sequence[str] = (),
    path: str = "/mcp",
):
    spec = ensure_operation_ids(spec)
    selection = select_operations(
        operations_from_spec(spec), include_writes=include_writes, exclude=exclude, mount_path=path
    )
    client = make_api_client(base_url=base_url, auth=PassThroughAuth(forward_headers))
    title = name or (spec.get("info") or {}).get("title") or "API"
    server, skipped = build_server(spec, name=title, selection=selection, client=client)
    report = MountReport.from_selection(selection, path=path, skipped=skipped)
    return server.http_app(path=path), report
