from __future__ import annotations

from pathlib import Path

from mcpmaker.clients.base import JsonClientAdapter, ServerEntry, render_headers


class WindsurfAdapter(JsonClientAdapter):
    name = "windsurf"
    display_name = "Windsurf"
    reload_hint = "Windsurf: press the refresh button in the MCP panel"

    def config_path(self) -> Path:
        return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"

    def build_block(self, entry: ServerEntry):
        headers, _ = render_headers(entry.headers, "env")
        block = {"serverUrl": entry.url}
        if headers:
            block["headers"] = headers
        return block, []

    def url_of(self, block):
        return block.get("serverUrl")
