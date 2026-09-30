"""Shared types and the JSON-config adapter base class."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol

from mcpmaker.configio import ConfigError, ValueStyle, load_json, render_value, write_json_atomic

Status = Literal["installed", "replaced", "skipped", "failed"]


@dataclass(frozen=True)
class ServerEntry:
    name: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)  # raw values; may contain ${VAR}


@dataclass(frozen=True)
class InstallResult:
    client: str
    status: Status
    path: str | None = None
    message: str = ""


class ClientAdapter(Protocol):
    name: str
    display_name: str
    reload_hint: str

    def detect(self) -> bool: ...
    def config_path(self) -> Path: ...
    def list_entries(self) -> dict[str, dict[str, Any]]: ...
    def url_of(self, block: Mapping[str, Any]) -> str | None: ...
    def check_entry(self, block: Mapping[str, Any]) -> str | None: ...
    def install(self, entry: ServerEntry, *, replace: bool = False, force: bool = False) -> InstallResult: ...


def app_config_dir() -> Path:
    """Per-user application config dir: %APPDATA%, ~/Library/Application Support, or XDG config."""
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def render_headers(headers: Mapping[str, str], style: ValueStyle) -> tuple[dict[str, str], bool]:
    rendered: dict[str, str] = {}
    wrote_literal = False
    for name, value in headers.items():
        rendered[name], literal = render_value(value, style)
        wrote_literal = wrote_literal or literal
    return rendered, wrote_literal


class JsonClientAdapter:
    """A client whose MCP servers live under one top-level key of a JSON file."""

    name: str
    display_name: str
    reload_hint: str
    root_key = "mcpServers"

    def config_path(self) -> Path:
        raise NotImplementedError

    def detect(self) -> bool:
        return self.config_path().parent.is_dir()

    def build_block(self, entry: ServerEntry) -> tuple[dict[str, Any], list[str]]:
        """The JSON block for `entry`, plus warnings. May raise ConfigError."""
        raise NotImplementedError

    def url_of(self, block: Mapping[str, Any]) -> str | None:
        return block.get("url")

    def check_entry(self, block: Mapping[str, Any]) -> str | None:
        return None

    def list_entries(self) -> dict[str, dict[str, Any]]:
        try:
            data = load_json(self.config_path())
        except ConfigError:
            return {}
        servers = data.get(self.root_key)
        return servers if isinstance(servers, dict) else {}

    def masked_snippet(self, entry: ServerEntry) -> str:
        """Copy-paste snippet with every header value replaced by a placeholder, so no secret is shown."""
        masked = dc_replace(entry, headers={k: f"<your {k} value>" for k in entry.headers})
        block, _ = self.build_block(masked)
        return json.dumps({self.root_key: {entry.name: block}}, indent=2)

    def install(self, entry: ServerEntry, *, replace: bool = False, force: bool = False) -> InstallResult:
        path = self.config_path()

        def result(status: Status, message: str = "") -> InstallResult:
            return InstallResult(self.name, status, str(path), message)

        try:
            block, warnings = self.build_block(entry)
        except ConfigError as exc:
            return result("failed", str(exc))
        snippet = self.masked_snippet(entry)

        try:
            data = load_json(path)
        except ConfigError as exc:
            if not force:
                return result(
                    "failed",
                    f"{exc}. Fix the file, re-run with --force (a .bak backup is kept), "
                    f"or add this manually:\n{snippet}",
                )
            data = {}

        servers = data.setdefault(self.root_key, {})
        if not isinstance(servers, dict):
            return result("failed", f"'{self.root_key}' in {path} is not an object; add this manually:\n{snippet}")
        existed = entry.name in servers
        if existed and not replace:
            return result("skipped", f"'{entry.name}' already exists (pass --yes to replace)")

        servers[entry.name] = block
        try:
            write_json_atomic(path, data)
        except OSError as exc:
            return result("failed", f"could not write {path} ({exc}); add this manually:\n{snippet}")
        return result("replaced" if existed else "installed", "; ".join(warnings))
