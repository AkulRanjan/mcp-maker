"""Claude Code: registered through its own `claude mcp add` CLI rather than by editing ~/.claude.json."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import replace as dc_replace
from pathlib import Path

from mcpmaker.clients.base import InstallResult, ServerEntry
from mcpmaker.configio import ConfigError, load_json


class ClaudeCodeAdapter:
    name = "claude-code"
    display_name = "Claude Code"
    reload_hint = "Claude Code: start a new session (or run /mcp) to pick up the server"

    def __init__(self, runner=subprocess.run) -> None:
        self._run = runner

    def _exe(self) -> str | None:
        return shutil.which("claude")

    def detect(self) -> bool:
        return self._exe() is not None

    def config_path(self) -> Path:
        return Path.home() / ".claude.json"

    def list_entries(self):
        try:
            data = load_json(self.config_path())
        except ConfigError:
            return {}
        servers = data.get("mcpServers")
        return servers if isinstance(servers, dict) else {}

    def url_of(self, block):
        return block.get("url")

    def check_entry(self, block):
        return None

    def _add_args(self, entry: ServerEntry) -> list[str]:
        args = ["mcp", "add", "--transport", "http", "--scope", "user", entry.name, entry.url]
        for name, value in entry.headers.items():
            args += ["--header", f"{name}: {value}"]
        return args

    @staticmethod
    def _redact(text: str, entry: ServerEntry) -> str:
        for value in sorted(entry.headers.values(), key=len, reverse=True):
            if value:
                text = text.replace(value, "<redacted>")
        return text

    def install(self, entry: ServerEntry, *, replace: bool = False, force: bool = False) -> InstallResult:
        exe = self._exe()
        path = str(self.config_path())
        if exe is None:
            masked = dc_replace(entry, headers={k: f"<your {k} value>" for k in entry.headers})
            manual = shlex.join(["claude", *self._add_args(masked)])
            return InstallResult(self.name, "failed", path, f"`claude` is not on PATH; run this yourself:\n{manual}")
        existed = entry.name in self.list_entries()
        if existed:
            if not replace:
                return InstallResult(self.name, "skipped", path, f"'{entry.name}' already exists (pass --yes to replace)")
            self._run([exe, "mcp", "remove", "--scope", "user", entry.name], capture_output=True, text=True)
        proc = self._run([exe, *self._add_args(entry)], capture_output=True, text=True)
        if proc.returncode != 0:
            err = self._redact((proc.stderr or "").strip(), entry)
            return InstallResult(self.name, "failed", path, err or "claude mcp add failed")
        return InstallResult(self.name, "replaced" if existed else "installed", path)
