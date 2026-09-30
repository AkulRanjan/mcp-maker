import json

from typer.testing import CliRunner

import mcpmaker.cli.connect as connect_mod
from mcpmaker.cli.main import app
from mcpmaker.clients.cursor import CursorAdapter
from mcpmaker.clients.vscode import VSCodeAdapter
from mcpmaker.clients.windsurf import WindsurfAdapter
from mcpmaker.engine import ProbeResult

runner = CliRunner()
URL = "http://localhost:8000/mcp"


def setup(monkeypatch, *, reachable=True, detected=(CursorAdapter, VSCodeAdapter)):
    adapters = [CursorAdapter(), VSCodeAdapter(), WindsurfAdapter()]
    monkeypatch.setattr(connect_mod, "all_adapters", lambda: adapters)

    async def fake_probe(url, headers, call_tool=None, timeout=10.0):
        if reachable:
            return ProbeResult(connected=True, server_name="Sample API", tools=["list_items"])
        return ProbeResult(connected=False, error="ConnectError")

    monkeypatch.setattr(connect_mod, "probe", fake_probe)
    for adapter in adapters:
        if type(adapter) in detected:
            adapter.config_path().parent.mkdir(parents=True, exist_ok=True)
    return adapters


def servers(adapter, key="mcpServers"):
    return json.loads(adapter.config_path().read_text(encoding="utf-8"))[key]


def test_all_writes_every_detected_client(fake_home, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "t0k")
    cursor, vscode, windsurf = setup(monkeypatch)
    result = runner.invoke(app, ["connect", "--url", URL, "-H", "Authorization: Bearer ${API_TOKEN}", "--all", "--yes"])
    assert result.exit_code == 0, result.output
    assert servers(cursor)["sample-api"]["url"] == URL
    assert servers(vscode, "servers")["sample-api"]["url"] == URL
    assert not windsurf.config_path().exists()
    assert "OK   Cursor: installed" in result.output
    assert "next: Cursor" in result.output
    result.output.encode("ascii")


def test_explicit_client_is_written_even_if_not_detected(fake_home, monkeypatch):
    _, _, windsurf = setup(monkeypatch)
    result = runner.invoke(app, ["connect", "--url", URL, "--client", "windsurf", "--yes"])
    assert result.exit_code == 0, result.output
    assert servers(windsurf)["sample-api"]["serverUrl"] == URL


def test_unknown_client_is_a_usage_error(fake_home, monkeypatch):
    setup(monkeypatch)
    result = runner.invoke(app, ["connect", "--url", URL, "--client", "emacs"])
    assert result.exit_code == 2
    assert "cursor" in result.output


def test_connect_twice_is_idempotent(fake_home, monkeypatch):
    cursor, _, _ = setup(monkeypatch)
    runner.invoke(app, ["connect", "--url", URL, "--client", "cursor", "--yes"])
    result = runner.invoke(app, ["connect", "--url", URL, "--client", "cursor", "--yes"])
    assert result.exit_code == 0, result.output
    assert "replaced" in result.output
    assert list(servers(cursor)) == ["sample-api"]
    assert cursor.config_path().with_name("mcp.json.bak").exists()


def test_interactive_prompts_choose_clients(fake_home, monkeypatch):
    cursor, vscode, _ = setup(monkeypatch)
    # Set up Cursor? y / Set up VS Code? n / Run doctor? n
    result = runner.invoke(app, ["connect", "--url", URL], input="y\nn\nn\n")
    assert result.exit_code == 0, result.output
    assert "sample-api" in servers(cursor)
    assert not vscode.config_path().exists()


def test_unreachable_server_falls_back_to_default_name(fake_home, monkeypatch):
    cursor, _, _ = setup(monkeypatch, reachable=False)
    result = runner.invoke(app, ["connect", "--url", URL, "--client", "cursor", "--yes"])
    assert result.exit_code == 0, result.output
    assert "api" in servers(cursor)
    assert "--name" in result.output


def test_failed_install_exits_nonzero(fake_home, monkeypatch):
    cursor, _, _ = setup(monkeypatch)
    cursor.config_path().write_text("{ broken", encoding="utf-8")
    result = runner.invoke(app, ["connect", "--url", URL, "--client", "cursor", "--yes"])
    assert result.exit_code == 1
    assert "FAIL Cursor: failed" in result.output


def test_no_clients_detected(fake_home, monkeypatch):
    setup(monkeypatch, detected=())
    result = runner.invoke(app, ["connect", "--url", URL, "--all"])
    assert result.exit_code == 1
    assert "--client" in result.output


def test_slugify():
    assert connect_mod.slugify("Sample API!") == "sample-api"
    assert connect_mod.slugify("***") == "api"


def test_header_value_is_written_but_never_printed(fake_home, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret-xyz")
    _, vscode, _ = setup(monkeypatch)
    result = runner.invoke(
        app, ["connect", "--url", URL, "--client", "vscode", "--yes", "-H", "Authorization: Bearer ${API_TOKEN}"]
    )
    assert result.exit_code == 0, result.output
    assert "secret-xyz" in vscode.config_path().read_text(encoding="utf-8")
    assert "secret-xyz" not in result.output


def test_mistyped_header_does_not_echo_the_secret(fake_home, monkeypatch):
    setup(monkeypatch)
    result = runner.invoke(app, ["connect", "--url", URL, "-H", "Bearer leakme123", "--all", "--yes"])
    assert result.exit_code == 2
    assert "leakme123" not in result.output


def test_utf16_config_fails_cleanly(fake_home, monkeypatch):
    cursor, _, _ = setup(monkeypatch)
    cursor.config_path().write_bytes("{}".encode("utf-16"))
    result = runner.invoke(app, ["connect", "--url", URL, "--client", "cursor", "--yes"])
    assert result.exit_code == 1, result.output
    assert "FAIL Cursor: failed" in result.output
    assert "Traceback" not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_auth_rejection_note_is_not_reachability(fake_home, monkeypatch):
    setup(monkeypatch)

    async def rejected(url, headers, call_tool=None, timeout=10.0):
        return ProbeResult(connected=False, status_code=401)

    monkeypatch.setattr(connect_mod, "probe", rejected)
    result = runner.invoke(app, ["connect", "--url", URL, "--client", "cursor", "--yes"])
    assert "rejected the request (HTTP 401)" in result.output
    assert "not reachable" not in result.output
    assert "check --header / API_TOKEN" in result.output
