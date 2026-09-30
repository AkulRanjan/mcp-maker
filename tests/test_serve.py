import json

import pytest
import yaml
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from typer.testing import CliRunner

from mcpmaker.cli.main import app as cli_app
from mcpmaker.standalone import build_standalone_app, load_spec
from tests.helpers import run_server
from tests.sample_app import make_app


@pytest.fixture
def spec():
    return make_app().openapi()


def test_load_spec_json_and_yaml(tmp_path, spec):
    (tmp_path / "s.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "s.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    assert load_spec(str(tmp_path / "s.json"))["paths"] == spec["paths"]
    assert load_spec(str(tmp_path / "s.yaml"))["paths"] == spec["paths"]


def test_load_spec_rejects_non_openapi(tmp_path):
    (tmp_path / "x.json").write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="OpenAPI"):
        load_spec(str(tmp_path / "x.json"))


def test_load_spec_missing_file_is_clear_error(tmp_path):
    with pytest.raises(ValueError, match="cannot read"):
        load_spec(str(tmp_path / "nope.json"))


def test_load_spec_rejects_garbage(tmp_path):
    (tmp_path / "g.txt").write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON or YAML"):
        load_spec(str(tmp_path / "g.txt"))


def test_serve_cli_missing_spec_exits_2(tmp_path):
    result = CliRunner().invoke(cli_app, ["serve", str(tmp_path / "nope.json"), "--base-url", "http://x"])
    assert result.exit_code == 2


def test_report_uses_policy(spec):
    _, report = build_standalone_app(spec, base_url="http://unused")
    methods = {m for _, m, _ in report.tools}
    assert methods == {"GET", "POST"}  # GETs plus the x-mcp opted-in POST
    assert any(p == "/items" and m == "POST" for m, p, _ in report.hidden)


async def test_serve_proxies_calls_and_forwards_auth(spec):
    with run_server(make_app()) as upstream:
        mcp_app, report = build_standalone_app(spec, base_url=upstream)
        tool = {path: name for name, method, path in report.tools if method == "GET"}
        with run_server(mcp_app) as base:
            transport = StreamableHttpTransport(f"{base}/mcp", headers={"Authorization": "Bearer good-token"})
            async with Client(transport) as c:
                item = await c.call_tool(tool["/items/{item_id}"], {"item_id": 1}, raise_on_error=False)
                me = await c.call_tool(tool["/me"], {}, raise_on_error=False)
    assert "apple" in item.content[0].text
    assert not me.is_error and "alice" in me.content[0].text


def _spec_file(tmp_path, doc):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p)


def test_serve_rejects_bad_path(tmp_path, spec):
    for bad in ("/", "mcp", "/mcp/"):
        result = CliRunner().invoke(cli_app, ["serve", _spec_file(tmp_path, spec), "--base-url", "http://x", "--path", bad])
        assert result.exit_code == 2, bad


def test_serve_unsupported_spec_exits_2_without_traceback(tmp_path):
    doc = {"swagger": "2.0", "paths": {"/x": {"get": {}}}}
    result = CliRunner().invoke(cli_app, ["serve", _spec_file(tmp_path, doc), "--base-url", "http://x"])
    assert result.exit_code == 2, result.output
    assert "OpenAPI 3.x required" in result.output
    assert "Traceback" not in result.output


def test_load_spec_invalid_url_is_value_error():
    with pytest.raises(ValueError, match="cannot read"):
        load_spec("https://[::1")
