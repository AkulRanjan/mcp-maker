"""The only module that imports FastMCP. Everything FastMCP-specific lives here."""

from __future__ import annotations

import contextvars
import logging
from typing import Any, Callable, Mapping, TypeVar

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware
from fastmcp.server.providers.openapi import MCPType

from mcpmaker.auth import AuthProvider
from mcpmaker.policy import Selection

log = logging.getLogger("mcpmaker")

AUTH_HINT = "auth failed - check the header configured in your client; run `mcpmaker doctor`"
GENERIC_ERROR = "internal error while calling the API route (details are in the server log)"
MAX_BODY = 4096

T = TypeVar("T")

# Per-tool-call scratch space shared between the error middleware and the httpx hooks.
_call_state: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "mcpmaker_call_state", default=None
)


def make_api_client(
    *,
    base_url: str,
    auth: AuthProvider,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 30.0,
) -> httpx.AsyncClient:
    async def forward_auth(request: httpx.Request) -> None:
        state = _call_state.get()
        if state is not None:
            state["sent"] = True
        try:
            incoming = get_http_headers(include_all=True)
        except Exception:  # no active MCP HTTP request, e.g. the in-memory transport
            incoming = {}
        for name, value in auth.headers_for(incoming).items():
            request.headers[name] = value

    async def record_response(response: httpx.Response) -> None:
        state = _call_state.get()
        if state is None:
            return
        state["status"] = response.status_code
        if response.status_code >= 400:
            await response.aread()
            state["body"] = response.text[:MAX_BODY]

    return httpx.AsyncClient(
        base_url=base_url,
        transport=transport,
        timeout=timeout,
        event_hooks={"request": [forward_auth], "response": [record_response]},
    )


class _ErrorShaping(Middleware):
    async def on_call_tool(self, context, call_next):
        state: dict[str, Any] = {}
        token = _call_state.set(state)
        try:
            return await call_next(context)
        except Exception as exc:
            raise ToolError(_error_message(context.message.name, state, exc)) from None
        finally:
            _call_state.reset(token)


def _error_message(tool: str, state: Mapping[str, Any], exc: BaseException) -> str:
    status = state.get("status")
    if status is not None and status >= 400:
        message = f"HTTP {status}: {state.get('body', '')}".rstrip()
        if status in (401, 403):
            message += f"\n{AUTH_HINT}"
        return message
    if state.get("sent"):
        # The request reached the route and it blew up: log everything, tell the model nothing internal.
        log.error("mcpmaker: tool %r failed inside the API route", tool, exc_info=exc)
        return GENERIC_ERROR
    # Failed before any HTTP request (e.g. bad arguments): the message is safe and useful to the model.
    return str(exc) or GENERIC_ERROR


def build_with_fallback(
    names: Mapping[str, str], attempt: Callable[[Mapping[str, str]], T]
) -> tuple[T, list[tuple[str, str]]]:
    """Build with all operations; if that fails, find and drop the ones that can't be built."""
    try:
        return attempt(names), []
    except Exception:
        pass
    kept = dict(names)
    skipped: list[tuple[str, str]] = []
    for op_id, tool in names.items():
        try:
            attempt({op_id: tool})
        except Exception as exc:
            skipped.append((op_id, f"{type(exc).__name__}: {exc}"))
            del kept[op_id]
    try:
        return attempt(kept), skipped
    except Exception as exc:
        skipped += [(op_id, f"{type(exc).__name__}: {exc}") for op_id in kept]
        return attempt({}), skipped


def build_server(
    spec: Mapping[str, Any],
    *,
    name: str,
    selection: Selection,
    client: httpx.AsyncClient,
) -> tuple[FastMCP, list[tuple[str, str]]]:
    def attempt(names: Mapping[str, str]) -> FastMCP:
        allowed = dict(names)

        def route_map_fn(route, mcp_type):
            return MCPType.TOOL if route.operation_id in allowed else MCPType.EXCLUDE

        server = FastMCP.from_openapi(
            openapi_spec=dict(spec),
            client=client,
            name=name,
            route_map_fn=route_map_fn,
            mcp_names=allowed,
        )
        server.add_middleware(_ErrorShaping())
        return server

    return build_with_fallback(selection.exposed, attempt)
