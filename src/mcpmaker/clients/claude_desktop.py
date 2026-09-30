from __future__ import annotations

import sys
from pathlib import Path

from mcpmaker.clients.base import JsonClientAdapter, ServerEntry, app_config_dir, render_headers


class ClaudeDesktopAdapter(JsonClientAdapter):
    """Claude Desktop's config file launches stdio servers, so it runs `mcpmaker bridge` to reach /mcp."""

    name = "claude-desktop"
    display_name = "Claude Desktop"
    reload_hint = "Claude Desktop: quit it completely and reopen it"

    def config_path(self) -> Path:
        return app_config_dir() / "Claude" / "claude_desktop_config.json"

    def build_block(self, entry: ServerEntry):
        headers, wrote_literal = render_headers(entry.headers, "literal")
        block = {
            # Absolute interpreter path: Claude Desktop launches with a minimal PATH.
            "command": sys.executable,
            "args": ["-m", "mcpmaker", "bridge", "--url", entry.url],
        }
        if headers:
            block["env"] = {f"MCPMAKER_HEADER_{i}": f"{k}: {v}" for i, (k, v) in enumerate(headers.items(), 1)}
        warnings = []
        if wrote_literal:
            warnings.append(
                f"Claude Desktop can't read environment variables: the header value was written "
                f"in plain text to {self.config_path()}"
            )
        return block, warnings

    def url_of(self, block):
        args = list(block.get("args") or [])
        return args[args.index("--url") + 1] if "--url" in args[:-1] else None

    def check_entry(self, block):
        command = block.get("command")
        if not command or not Path(command).exists():
            return f"bridge command not found: {command} (re-run: mcpmaker connect --client claude-desktop)"
        return None
