import json
import subprocess

import pytest

import mcpmaker.clients.claude_code as cc
from mcpmaker.clients import all_adapters
from mcpmaker.clients.base import ServerEntry

URL = "http://localhost:8000/mcp"
ENTRY = ServerEntry(name="sample-api", url=URL, headers={"Authorization": "Bearer ${API_TOKEN}"})


class FakeRunner:
    def __init__(self, returncode=0, stderr=""):
        self.calls, self.returncode, self.stderr = [], returncode, stderr

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, self.returncode, "", self.stderr)


@pytest.fixture
def on_path(monkeypatch):
    monkeypatch.setattr(cc.shutil, "which", lambda name: "/bin/claude" if name == "claude" else None)


def write_claude_json(home, servers):
    (home / ".claude.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def test_install_runs_claude_mcp_add(fake_home, on_path):
    runner = FakeRunner()
    result = cc.ClaudeCodeAdapter(runner=runner).install(ENTRY)
    assert result.status == "installed"
    assert runner.calls == [
        ["/bin/claude", "mcp", "add", "--transport", "http", "--scope", "user", "sample-api", URL,
         "--header", "Authorization: Bearer ${API_TOKEN}"]
    ]


def test_existing_entry_skipped_without_replace(fake_home, on_path):
    write_claude_json(fake_home, {"sample-api": {"type": "http", "url": "http://old"}})
    runner = FakeRunner()
    result = cc.ClaudeCodeAdapter(runner=runner).install(ENTRY)
    assert result.status == "skipped"
    assert runner.calls == []


def test_replace_removes_then_adds(fake_home, on_path):
    write_claude_json(fake_home, {"sample-api": {"type": "http", "url": "http://old"}})
    runner = FakeRunner()
    result = cc.ClaudeCodeAdapter(runner=runner).install(ENTRY, replace=True)
    assert result.status == "replaced"
    assert runner.calls[0] == ["/bin/claude", "mcp", "remove", "--scope", "user", "sample-api"]
    assert runner.calls[1][:3] == ["/bin/claude", "mcp", "add"]


def test_cli_failure_is_reported(fake_home, on_path):
    result = cc.ClaudeCodeAdapter(runner=FakeRunner(returncode=1, stderr="boom\n")).install(ENTRY)
    assert result.status == "failed"
    assert "boom" in result.message


def test_not_on_path(fake_home, monkeypatch):
    monkeypatch.setattr(cc.shutil, "which", lambda name: None)
    adapter = cc.ClaudeCodeAdapter(runner=FakeRunner())
    assert adapter.detect() is False
    result = adapter.install(ENTRY)
    assert result.status == "failed"
    assert "claude mcp add" in result.message


def test_not_on_path_message_masks_header_values(fake_home, monkeypatch):
    monkeypatch.setattr(cc.shutil, "which", lambda name: None)
    entry = ServerEntry(name="sample-api", url=URL, headers={"Authorization": "Bearer s3cr3t-token"})
    message = cc.ClaudeCodeAdapter(runner=FakeRunner()).install(entry).message
    assert "s3cr3t-token" not in message
    assert "Authorization: <your Authorization value>" in message


def test_failure_stderr_redacts_header_values(fake_home, on_path):
    entry = ServerEntry(name="sample-api", url=URL, headers={"Authorization": "Bearer s3cr3t-token"})
    runner = FakeRunner(returncode=1, stderr="error: bad arg Authorization: Bearer s3cr3t-token\n")
    result = cc.ClaudeCodeAdapter(runner=runner).install(entry)
    assert result.status == "failed"
    assert "s3cr3t-token" not in result.message
    assert "bad arg" in result.message


def test_list_entries_and_url_of(fake_home, on_path):
    write_claude_json(fake_home, {"sample-api": {"type": "http", "url": URL}})
    adapter = cc.ClaudeCodeAdapter()
    entries = adapter.list_entries()
    assert adapter.url_of(entries["sample-api"]) == URL
    assert adapter.check_entry(entries["sample-api"]) is None


def test_registered_first():
    assert all_adapters()[0].name == "claude-code"
