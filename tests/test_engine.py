import httpx
import pytest
from fastmcp import Client

from mcpmaker.auth import PassThroughAuth
from mcpmaker.engine import AUTH_HINT, GENERIC_ERROR, build_server, build_with_fallback, make_api_client
from mcpmaker.introspect import endpoint_names
from mcpmaker.policy import operations_from_spec, select_operations
from tests.sample_app import make_app

EXPECTED_TOOLS = {"list_items", "get_item", "star_item", "me", "boom", "admin_stats"}


@pytest.fixture
def server():
    app = make_app()
    spec = app.openapi()
    selection = select_operations(operations_from_spec(spec, endpoint_names(app)))
    client = make_api_client(
        base_url="http://mcpmaker.internal",
        auth=PassThroughAuth(),
        transport=httpx.ASGITransport(app=app),
    )
    srv, skipped = build_server(spec, name="Sample API", selection=selection, client=client)
    assert skipped == []
    return srv


def text_of(result):
    return "\n".join(getattr(c, "text", "") for c in result.content)


def test_endpoint_names_maps_method_and_path_to_function():
    names = endpoint_names(make_app())
    assert names[("GET", "/items/{item_id}")] == "get_item"
    assert names[("POST", "/items")] == "create_item"


async def test_lists_selected_tools_named_after_functions(server):
    async with Client(server) as c:
        names = {t.name for t in await c.list_tools()}
    assert names == EXPECTED_TOOLS


async def test_successful_call_returns_route_body(server):
    async with Client(server) as c:
        result = await c.call_tool("get_item", {"item_id": 1}, raise_on_error=False)
    assert not result.is_error
    assert "apple" in text_of(result)


async def test_http_error_becomes_error_result_with_status_and_body(server):
    async with Client(server) as c:
        result = await c.call_tool("get_item", {"item_id": 999}, raise_on_error=False)
    assert result.is_error
    assert "HTTP 404" in text_of(result)
    assert "item not found" in text_of(result)


async def test_401_adds_auth_hint(server):
    async with Client(server) as c:
        result = await c.call_tool("me", {}, raise_on_error=False)
    assert result.is_error
    assert "HTTP 401" in text_of(result)
    assert AUTH_HINT in text_of(result)


async def test_route_exception_is_generic_and_hides_details(server):
    async with Client(server) as c:
        result = await c.call_tool("boom", {}, raise_on_error=False)
    assert result.is_error
    assert text_of(result).strip() == GENERIC_ERROR
    assert "secret internal detail" not in text_of(result)


async def test_argument_errors_are_not_masked(server):
    async with Client(server) as c:
        result = await c.call_tool("get_item", {}, raise_on_error=False)
    assert result.is_error
    assert GENERIC_ERROR not in text_of(result)


def test_build_with_fallback_skips_only_the_broken_operation():
    def attempt(names):
        if "bad" in names:
            raise ValueError("unsupported schema")
        return sorted(names)

    built, skipped = build_with_fallback({"good": "g", "bad": "b"}, attempt)
    assert built == ["good"]
    assert skipped == [("bad", "ValueError: unsupported schema")]


def test_build_with_fallback_happy_path_skips_nothing():
    built, skipped = build_with_fallback({"a": "x"}, lambda names: dict(names))
    assert built == {"a": "x"} and skipped == []


async def test_transport_error_says_api_unreachable():
    app = make_app()
    spec = app.openapi()
    selection = select_operations(operations_from_spec(spec, endpoint_names(app)))

    def handler(request):
        raise httpx.ConnectError("connection refused")

    client = make_api_client(
        base_url="http://mcpmaker.internal",
        auth=PassThroughAuth(),
        transport=httpx.MockTransport(handler),
    )
    srv, _ = build_server(spec, name="Sample API", selection=selection, client=client)
    async with Client(srv) as c:
        result = await c.call_tool("get_item", {"item_id": 1}, raise_on_error=False)
    assert result.is_error
    assert "could not reach the API" in text_of(result)
    assert "ConnectError" in text_of(result)
    assert text_of(result) != GENERIC_ERROR
