from __future__ import annotations

from pathlib import Path

from mcpmaker.clients.base import JsonClientAdapter, ServerEntry, app_config_dir, render_headers


class VSCodeAdapter(JsonClientAdapter):
    name = "vscode"
    display_name = "VS Code"
    reload_hint = "VS Code: run 'MCP: List Servers' from the command palette and start the server"
    root_key = "servers"

    def config_path(self) -> Path:
        return app_config_dir() / "Code" / "User" / "mcp.json"

    def build_block(self, entry: ServerEntry):
        # VS Code's docs only promise ${input:} in headers, and ${env:} is reported unexpanded
        # (microsoft/vscode#336232), so write the resolved value and warn.
        headers, wrote_literal = render_headers(entry.headers, "literal")
        block = {"type": "http", "url": entry.url}
        if headers:
            block["headers"] = headers
        warnings = []
        if wrote_literal:
            warnings.append(
                f"VS Code does not reliably expand environment variables in headers: the header value "
                f"was written in plain text to {self.config_path()}"
            )
        return block, warnings
