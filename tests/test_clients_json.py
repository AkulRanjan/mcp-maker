import json
import sys

import pytest

from mcpmaker.clients import all_adapters
from mcpmaker.clients.base import ServerEntry
from mcpmaker.clients.claude_desktop import ClaudeDesktopAdapter
from mcpmaker.clients.cursor import CursorAdapter
from mcpmaker.clients.vscode import VSCodeAdapter
from mcpmaker.clients.windsurf import WindsurfAdapter

URL = "http://localhost:8000/mcp"
ENTRY = ServerEntry(name="sample-api", url=URL, headers={"Authorization": "Bearer ${API_TOKEN}"})
ENV_HEADERS = {"Authorization": "Bearer ${env:API_TOKEN}"}
LITERAL_HEADERS = {"Authorization": "Bearer t0k"}  # VS Code does not reliably expand ${env:} in headers


@pytest.fixture(autouse=True)
def api_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "t0k")


JSON_CASES = [
    (CursorAdapter, "mcpServers", {"url": URL, "headers": ENV_HEADERS}),
    (VSCodeAdapter, "servers", {"type": "http", "url": URL, "headers": LITERAL_HEADERS}),
    (WindsurfAdapter, "mcpServers", {"serverUrl": URL, "headers": ENV_HEADERS}),
]
IDS = ["cursor", "vscode", "windsurf"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("cls,key,expected", JSON_CASES, ids=IDS)
def test_writes_expected_block_into_new_file(fake_home, cls, key, expected):
    adapter = cls()
    result = adapter.install(ENTRY)
    assert result.status == "installed"
    assert read(adapter.config_path()) == {key: {"sample-api": expected}}


@pytest.mark.parametrize("cls,key,expected", JSON_CASES, ids=IDS)
def test_preserves_other_servers_and_top_level_keys(fake_home, cls, key, expected):
    adapter = cls()
    path = adapter.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"theme": "dark", key: {"other": {"url": "http://x"}}}), encoding="utf-8")
    adapter.install(ENTRY)
    data = read(path)
    assert data["theme"] == "dark"
    assert data[key]["other"] == {"url": "http://x"}
    assert data[key]["sample-api"] == expected


@pytest.mark.parametrize("cls,key,expected", JSON_CASES, ids=IDS)
def test_existing_name_is_skipped_without_replace(fake_home, cls, key, expected):
    adapter = cls()
    path = adapter.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    original = json.dumps({key: {"sample-api": {"url": "http://old"}}})
    path.write_text(original, encoding="utf-8")
    result = adapter.install(ENTRY)
    assert result.status == "skipped"
    assert "--yes" in result.message
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("cls,key,expected", JSON_CASES, ids=IDS)
def test_replace_overwrites_and_keeps_backup(fake_home, cls, key, expected):
    adapter = cls()
    adapter.install(ENTRY)
    newer = ServerEntry(name="sample-api", url="http://localhost:9000/mcp", headers={})
    result = adapter.install(newer, replace=True)
    assert result.status == "replaced"
    assert adapter.url_of(read(adapter.config_path())[key]["sample-api"]) == "http://localhost:9000/mcp"
    backup = adapter.config_path().with_name(adapter.config_path().name + ".bak")
    assert read(backup)[key]["sample-api"] == expected


@pytest.mark.parametrize("cls,key,expected", JSON_CASES, ids=IDS)
def test_malformed_file_is_left_untouched_without_force(fake_home, cls, key, expected):
    adapter = cls()
    path = adapter.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    result = adapter.install(ENTRY)
    assert result.status == "failed"
    assert "line 1" in result.message and "--force" in result.message
    assert '"sample-api"' in result.message  # copy-paste snippet
    assert path.read_text(encoding="utf-8") == "{ not json"


@pytest.mark.parametrize("cls,key,expected", JSON_CASES, ids=IDS)
def test_malformed_file_with_force_is_rewritten_and_backed_up(fake_home, cls, key, expected):
    adapter = cls()
    path = adapter.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    result = adapter.install(ENTRY, force=True)
    assert result.status == "installed"
    assert read(path) == {key: {"sample-api": expected}}
    assert path.with_name(path.name + ".bak").read_text(encoding="utf-8") == "{ not json"


def test_vscode_jsonc_comments_are_never_clobbered(fake_home):
    adapter = VSCodeAdapter()
    path = adapter.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    original = '{\n  // my servers\n  "servers": {}\n}\n'
    path.write_text(original, encoding="utf-8")
    result = adapter.install(ENTRY)
    assert result.status == "failed"
    assert '"servers"' in result.message
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("cls,key,expected", JSON_CASES, ids=IDS)
def test_list_entries_and_url_of(fake_home, cls, key, expected):
    adapter = cls()
    assert adapter.list_entries() == {}
    adapter.install(ENTRY)
    entries = adapter.list_entries()
    assert list(entries) == ["sample-api"]
    assert adapter.url_of(entries["sample-api"]) == URL
    assert adapter.check_entry(entries["sample-api"]) is None


@pytest.mark.parametrize("cls", [CursorAdapter, VSCodeAdapter, WindsurfAdapter, ClaudeDesktopAdapter])
def test_detect_follows_client_directory(fake_home, cls):
    adapter = cls()
    assert adapter.detect() is False
    adapter.config_path().parent.mkdir(parents=True, exist_ok=True)
    assert adapter.detect() is True


def test_claude_desktop_uses_bridge_with_literal_header(fake_home):
    adapter = ClaudeDesktopAdapter()
    result = adapter.install(ENTRY)
    assert result.status == "installed"
    assert "plain text" in result.message
    block = read(adapter.config_path())["mcpServers"]["sample-api"]
    assert block == {
        "command": sys.executable,
        "args": ["-m", "mcpmaker", "bridge", "--url", URL],
        "env": {"MCPMAKER_HEADER_1": "Authorization: Bearer t0k"},
    }
    assert adapter.url_of(block) == URL
    assert adapter.check_entry(block) is None


def test_claude_desktop_missing_env_var_fails_cleanly(fake_home, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    result = ClaudeDesktopAdapter().install(ENTRY)
    assert result.status == "failed"
    assert "API_TOKEN" in result.message


def test_claude_desktop_check_entry_flags_missing_command(fake_home):
    problem = ClaudeDesktopAdapter().check_entry({"command": "/nope/python", "args": ["--url", URL]})
    assert problem is not None and "/nope/python" in problem


def test_registry_lists_all_json_adapters():
    names = [a.name for a in all_adapters()]
    assert {"cursor", "vscode", "windsurf", "claude-desktop"} <= set(names)


def test_vscode_warns_that_header_is_plain_text(fake_home):
    result = VSCodeAdapter().install(ENTRY)
    assert result.status == "installed"
    assert "plain text" in result.message


def test_vscode_missing_env_var_fails_cleanly(fake_home, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    result = VSCodeAdapter().install(ENTRY)
    assert result.status == "failed"
    assert "API_TOKEN" in result.message


@pytest.mark.parametrize("cls", [VSCodeAdapter, ClaudeDesktopAdapter, CursorAdapter, WindsurfAdapter])
def test_failure_snippet_masks_header_values(fake_home, cls):
    adapter = cls()
    path = adapter.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    result = adapter.install(ENTRY)
    assert result.status == "failed"
    assert "t0k" not in result.message
    assert "<your Authorization value>" in result.message
    assert '"sample-api"' in result.message
