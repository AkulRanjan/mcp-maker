import logging
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from mcpmaker import MountHandle, mount_mcp
from mcpmaker.engine import AUTH_HINT, GENERIC_ERROR
from tests.helpers import run_server
from tests.sample_app import make_app


def mcp_client(base_url, headers=None):
    return Client(StreamableHttpTransport(f"{base_url}/mcp", headers=headers or {}))


def text_of(result):
    return "\n".join(getattr(c, "text", "") for c in result.content)


async def test_tools_listed_over_http_with_safe_defaults():
    app = make_app()
    handle = mount_mcp(app, exclude=["/admin/*"])
    with run_server(app) as url:
        async with mcp_client(url) as c:
            names = {t.name for t in await c.list_tools()}
    assert names == {"list_items", "get_item", "star_item", "me", "boom"}
    assert "create_item" not in names
    assert isinstance(handle, MountHandle)
    assert {t[0] for t in handle.report.tools} == names


async def test_auth_header_is_passed_through_to_route():
    app = make_app()
    mount_mcp(app)
    with run_server(app) as url:
        async with mcp_client(url, {"Authorization": "Bearer good-token"}) as c:
            result = await c.call_tool("me", {}, raise_on_error=False)
    assert not result.is_error
    assert "alice" in text_of(result)


async def test_bad_token_returns_401_with_hint():
    app = make_app()
    mount_mcp(app)
    with run_server(app) as url:
        async with mcp_client(url, {"Authorization": "Bearer wrong"}) as c:
            result = await c.call_tool("me", {}, raise_on_error=False)
    assert result.is_error
    assert "HTTP 401" in text_of(result)
    assert AUTH_HINT in text_of(result)


async def test_route_exception_does_not_leak_to_model():
    app = make_app()
    mount_mcp(app)
    with run_server(app) as url:
        async with mcp_client(url) as c:
            result = await c.call_tool("boom", {}, raise_on_error=False)
    assert result.is_error
    assert text_of(result).strip() == GENERIC_ERROR


async def test_token_never_logged(caplog):
    caplog.set_level(logging.DEBUG, logger="mcpmaker")
    app = make_app()
    handle = mount_mcp(app)
    with run_server(app) as url:
        async with mcp_client(url, {"Authorization": "Bearer leak-me-123"}) as c:
            await c.call_tool("me", {}, raise_on_error=False)
            await c.call_tool("boom", {}, raise_on_error=False)
    assert "leak-me-123" not in caplog.text
    assert "leak-me-123" not in handle.report.format()


async def test_user_lifespan_still_runs():
    events = []

    @asynccontextmanager
    async def lifespan(app):
        events.append("start")
        yield
        events.append("stop")

    app = make_app(lifespan=lifespan)
    mount_mcp(app)
    with run_server(app) as url:
        async with mcp_client(url) as c:
            assert await c.list_tools()
    assert events == ["start", "stop"]


async def test_routes_added_after_mount_are_exposed():
    app = make_app()
    mount_mcp(app)

    @app.get("/late", summary="Registered after mount_mcp")
    def late_route():
        return {"late": True}

    with run_server(app) as url:
        async with mcp_client(url) as c:
            names = {t.name for t in await c.list_tools()}
    assert "late_route" in names


def test_mcp_returns_503_before_startup():
    app = make_app()
    mount_mcp(app)
    client = TestClient(app)  # no `with`: lifespan never runs
    assert client.post("/mcp", json={}).status_code == 503


def test_startup_report_is_logged(caplog):
    caplog.set_level(logging.INFO, logger="mcpmaker")
    app = make_app()
    mount_mcp(app)
    with TestClient(app):
        pass
    assert "tools exposed at /mcp" in caplog.text
