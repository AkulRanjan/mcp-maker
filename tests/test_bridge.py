import os
import sys

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from mcpmaker import mount_mcp
from mcpmaker.cli.bridge import headers_from_env
from tests.helpers import free_port, run_server
from tests.sample_app import make_app


def bridge_client(url, extra_env=None):
    env = {**os.environ, **(extra_env or {})}
    return Client(StdioTransport(command=sys.executable, args=["-m", "mcpmaker", "bridge", "--url", url], env=env))


def test_headers_from_env_reads_numbered_vars_in_order():
    env = {"MCPMAKER_HEADER_2": "X-Key: k", "MCPMAKER_HEADER_1": "Authorization: Bearer t", "OTHER": "x"}
    assert headers_from_env(env) == {"Authorization": "Bearer t", "X-Key": "k"}


async def test_bridge_relays_tools_and_headers():
    app = make_app()
    mount_mcp(app)
    with run_server(app) as base:
        async with bridge_client(f"{base}/mcp", {"MCPMAKER_HEADER_1": "Authorization: Bearer good-token"}) as c:
            names = {t.name for t in await c.list_tools()}
            result = await c.call_tool("me", {}, raise_on_error=False)
    assert "list_items" in names
    assert not result.is_error
    assert "alice" in "".join(getattr(x, "text", "") for x in result.content)


async def test_bridge_stays_alive_when_upstream_is_down():
    url = f"http://127.0.0.1:{free_port()}/mcp"
    async with bridge_client(url) as c:
        with pytest.raises(Exception, match=url):
            await c.list_tools()
        assert await c.ping()
