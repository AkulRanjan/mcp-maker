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


def test_headers_from_env_malformed_names_var_not_value():
    with pytest.raises(ValueError) as info:
        headers_from_env({"MCPMAKER_HEADER_1": "supersecretvalue"})
    assert "MCPMAKER_HEADER_1" in str(info.value)
    assert "supersecretvalue" not in str(info.value)


def test_bridge_command_reports_malformed_env_header_without_value():
    import subprocess

    env = {**os.environ, "MCPMAKER_HEADER_1": "supersecretvalue"}
    proc = subprocess.run(
        [sys.executable, "-m", "mcpmaker", "bridge", "--url", "http://127.0.0.1:1/mcp"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "MCPMAKER_HEADER_1" in out
    assert "supersecretvalue" not in out


async def test_bridge_tool_call_names_url_when_upstream_goes_down_then_recovers():
    port = free_port()
    url = f"http://127.0.0.1:{port}/mcp"
    headers = {"MCPMAKER_HEADER_1": "Authorization: Bearer good-token"}
    app = make_app()
    mount_mcp(app)
    async with bridge_client(url, headers) as c:
        with run_server(app, port=port):
            assert "me" in {t.name for t in await c.list_tools()}
        result = await c.call_tool("me", {}, raise_on_error=False)
        assert result.is_error
        assert url in "".join(getattr(x, "text", "") for x in result.content)
        app2 = make_app()
        mount_mcp(app2)
        with run_server(app2, port=port):
            again = await c.call_tool("me", {}, raise_on_error=False)
            assert not again.is_error
