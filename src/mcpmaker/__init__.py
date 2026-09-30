"""mcpmaker: expose a FastAPI app as an MCP server and connect it to AI clients."""

from mcpmaker.auth import AuthProvider, PassThroughAuth
from mcpmaker.mount import MountHandle, mount_mcp
from mcpmaker.report import MountReport

__all__ = ["AuthProvider", "MountHandle", "MountReport", "PassThroughAuth", "mount_mcp"]
