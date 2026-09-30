import json

from typer.testing import CliRunner

import mcpmaker.cli.doctor as doctor_mod
from mcpmaker import mount_mcp
from mcpmaker.cli.main import app
from mcpmaker.clients.cursor import CursorAdapter
from mcpmaker.engine import probe
from tests.helpers import free_port, run_server
from tests.sample_app import make_app

runner = CliRunner()


def served_app():
    a = make_app()
    mount_mcp(a)
    return a


async def test_probe_live_server():
    with run_server(served_app()) as base:
        result = await probe(f"{base}/mcp", {}, call_tool="list_items")
    assert result.connected
    assert result.server_name == "Sample API"
    assert "list_items" in result.tools
    assert result.call_ok is True


async def test_probe_dead_url():
    result = await probe(f"http://127.0.0.1:{free_port()}/mcp", {}, timeout=3)
    assert not result.connected
    assert result.error


def test_doctor_ok_against_live_server(fake_home, monkeypatch):
    monkeypatch.setattr(doctor_mod, "all_adapters", lambda: [CursorAdapter()])
    with run_server(served_app()) as base:
        result = runner.invoke(app, ["doctor", "--url", f"{base}/mcp"])
    assert result.exit_code == 0, result.output
    assert "OK   MCP server reachable" in result.output
    assert "--   Cursor configured: not installed" in result.output
    result.output.encode("ascii")


def test_doctor_fails_on_dead_url(fake_home, monkeypatch):
    monkeypatch.setattr(doctor_mod, "all_adapters", lambda: [])
    result = runner.invoke(app, ["doctor", "--url", f"http://127.0.0.1:{free_port()}/mcp"])
    assert result.exit_code == 1
    assert "FAIL MCP server reachable" in result.output
    assert "is the app running" in result.output
    result.output.encode("ascii")


def test_doctor_flags_client_pointing_elsewhere(fake_home, monkeypatch):
    monkeypatch.setattr(doctor_mod, "all_adapters", lambda: [CursorAdapter()])
    cfg = CursorAdapter().config_path()
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"mcpServers": {"x": {"url": "http://elsewhere/mcp"}}}), encoding="utf-8")
    with run_server(served_app()) as base:
        result = runner.invoke(app, ["doctor", "--url", f"{base}/mcp"])
    assert result.exit_code == 1
    assert "FAIL Cursor configured" in result.output
    assert "mcpmaker connect" in result.output


def test_doctor_rejects_bad_header():
    result = runner.invoke(app, ["doctor", "--url", "http://x/mcp", "--header", "nocolon"])
    assert result.exit_code == 2
    assert "Name: value" in result.output


def test_doctor_never_prints_header_values(fake_home, monkeypatch):
    monkeypatch.setattr(doctor_mod, "all_adapters", lambda: [])
    monkeypatch.setattr(
        doctor_mod, "probe", _leaky_probe
    )
    result = runner.invoke(
        app,
        ["doctor", "--url", f"http://127.0.0.1:{free_port()}/mcp", "-H", "Authorization: Bearer leak-me-123"],
    )
    assert result.exit_code == 1
    assert "FAIL MCP server reachable" in result.output
    assert "leak-me-123" not in result.output
    assert "<redacted>" in result.output


def test_doctor_dead_url_with_header_does_not_leak(fake_home, monkeypatch):
    monkeypatch.setattr(doctor_mod, "all_adapters", lambda: [])
    result = runner.invoke(
        app,
        ["doctor", "--url", f"http://127.0.0.1:{free_port()}/mcp", "-H", "Authorization: Bearer leak-me-123"],
    )
    assert result.exit_code == 1
    assert "leak-me-123" not in result.output


async def _leaky_probe(url, headers, call_tool=None, timeout=10.0):
    from mcpmaker.engine import ProbeResult

    return ProbeResult(connected=False, error=f"RuntimeError: server echoed {headers['Authorization']}")
