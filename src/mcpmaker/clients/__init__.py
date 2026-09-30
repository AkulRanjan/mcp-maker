"""AI-client adapters. Each knows where its client keeps MCP config and how to write an entry."""

from __future__ import annotations

from mcpmaker.clients.base import ClientAdapter
from mcpmaker.clients.claude_desktop import ClaudeDesktopAdapter
from mcpmaker.clients.cursor import CursorAdapter
from mcpmaker.clients.vscode import VSCodeAdapter
from mcpmaker.clients.windsurf import WindsurfAdapter


def all_adapters() -> list[ClientAdapter]:
    return [CursorAdapter(), VSCodeAdapter(), WindsurfAdapter(), ClaudeDesktopAdapter()]
