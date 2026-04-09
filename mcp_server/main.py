"""ComfyUI MCP Hub — Main entry point for the MCP server."""

from __future__ import annotations

import os
import sys

# Fix imports when run as a standalone script (not as a module)
# This is needed because MCP clients launch this file directly
if __name__ == "__main__" or __package__ is None:
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _parent_dir = os.path.dirname(_this_dir)
    if _parent_dir not in sys.path:
        sys.path.insert(0, _parent_dir)
    __package__ = "mcp_server"

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .tools import introspection, workflows, generation, models, packages, instances, resolver, ui_bridge, smart_layout, workflow_ops, combo, version, repair
from .resources import status


def create_server() -> FastMCP:
    """Create and configure the MCP server with all enabled tools."""
    config = load_config()
    enabled = config.get("enabled_tools", {})

    mcp = FastMCP("ComfyUI MCP Hub")

    # Register tool modules based on configuration
    if enabled.get("introspection", True):
        introspection.register(mcp)

    if enabled.get("workflows", True):
        workflows.register(mcp)

    if enabled.get("generation", True):
        generation.register(mcp)

    if enabled.get("models", True):
        models.register(mcp)

    if enabled.get("packages", True):
        packages.register(mcp)

    if enabled.get("instances", True):
        instances.register(mcp)

    # Core tools — always enabled
    resolver.register(mcp)
    ui_bridge.register(mcp)
    smart_layout.register(mcp)
    workflow_ops.register(mcp)
    combo.register(mcp)
    version.register(mcp)
    repair.register(mcp)

    # Always register resources
    status.register(mcp)

    return mcp


def main() -> None:
    """Run the MCP server with stdio transport."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
