from __future__ import annotations

from pathlib import Path

from mcpmaker.clients.base import JsonClientAdapter, ServerEntry, render_headers


class CursorAdapter(JsonClientAdapter):
    name = "cursor"
    display_name = "Cursor"
    reload_hint = "Cursor: open Settings > MCP and toggle the server on (or reload the window)"

    def config_path(self) -> Path:
        return Path.home() / ".cursor" / "mcp.json"

    def build_block(self, entry: ServerEntry):
        headers, _ = render_headers(entry.headers, "env")
        block = {"url": entry.url}
        if headers:
            block["headers"] = headers
        return block, []
