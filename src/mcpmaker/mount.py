"""`mount_mcp(app)`: serve the app's own routes as MCP tools at /mcp."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Sequence

import httpx
from fastapi import FastAPI
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from mcpmaker.auth import AuthProvider, PassThroughAuth
from mcpmaker.engine import build_server, make_api_client
from mcpmaker.introspect import endpoint_names
from mcpmaker.policy import operations_from_spec, select_operations
from mcpmaker.report import MountReport

INTERNAL_BASE_URL = "http://mcpmaker.internal"


@dataclass
class MountHandle:
    path: str
    report: MountReport | None = None  # set when the app starts


class _LazyMCPApp:
    """ASGI app registered at `path`; forwards to the real MCP app once startup has built it."""

    def __init__(self) -> None:
        self.inner = None

    async def __call__(self, scope, receive, send) -> None:
        if self.inner is not None:
            await self.inner(scope, receive, send)
        elif scope["type"] == "http":
            response = PlainTextResponse(
                "mcpmaker: MCP server not started yet (the app's lifespan has not run)", status_code=503
            )
            await response(scope, receive, send)


def mount_mcp(
    app: FastAPI,
    *,
    path: str = "/mcp",
    name: str | None = None,
    include_writes: bool = False,
    exclude: Sequence[str] = (),
    forward_headers: Sequence[str] = (),
    auth: AuthProvider | None = None,
    max_tools_warning: int = 40,
) -> MountHandle:
    if not path.startswith("/") or path.endswith("/"):
        raise ValueError(f"path must start with '/' and not end with '/': {path!r}")
    auth = auth or PassThroughAuth(forward_headers)
    handle = MountHandle(path=path)
    lazy = _LazyMCPApp()
    # An exact-path Route (not a Mount) so clients never see a /mcp -> /mcp/ redirect.
    app.router.routes.insert(0, Route(path, endpoint=lazy, include_in_schema=False))

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(asgi_app):
        async with original_lifespan(asgi_app) as state:
            # Built at startup so routes registered after mount_mcp() are included.
            spec = app.openapi()
            selection = select_operations(
                operations_from_spec(spec, endpoint_names(app)),
                include_writes=include_writes,
                exclude=exclude,
                mount_path=path,
                max_tools_warning=max_tools_warning,
            )
            client = make_api_client(
                base_url=INTERNAL_BASE_URL, auth=auth, transport=httpx.ASGITransport(app=app)
            )
            server, skipped = build_server(spec, name=name or app.title, selection=selection, client=client)
            mcp_app = server.http_app(path=path)
            handle.report = MountReport.from_selection(selection, path=path, skipped=skipped)
            _logger().info("%s", handle.report.format())
            async with mcp_app.lifespan(mcp_app):
                lazy.inner = mcp_app
                try:
                    yield state
                finally:
                    lazy.inner = None
                    await client.aclose()

    app.router.lifespan_context = lifespan
    return handle


def _logger() -> logging.Logger:
    log = logging.getLogger("mcpmaker")
    # Make the startup report visible under uvicorn, which doesn't configure the root logger.
    if not log.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return log
