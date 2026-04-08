"""Version management MCP tools — check for updates, upgrade, and downgrade."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Import the updater from the server package
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from server.updater import check_for_update, list_versions, switch_version as _switch_version


def register(mcp: FastMCP) -> None:
    """Register version management tools on the MCP server."""

    @mcp.tool()
    async def hub_check_update() -> dict[str, Any]:
        """Check if a newer version of MCP Hub is available on GitHub.

        Returns the current version, latest available version, and whether
        an update is available, along with release notes.
        """
        return check_for_update()

    @mcp.tool()
    async def hub_list_versions() -> dict[str, Any]:
        """List all available MCP Hub versions from GitHub Releases.

        Returns a list of all releases with version numbers, release notes,
        dates, and marks which version is currently installed.
        """
        return list_versions()

    @mcp.tool()
    async def hub_switch_version(tag: str) -> dict[str, Any]:
        """Switch MCP Hub to a specific version (upgrade or downgrade).

        This performs a `git checkout` to the specified tag. ComfyUI must be
        restarted after switching for changes to take effect.

        Args:
            tag: The version tag to switch to (e.g. "v0.4.0").
        """
        return _switch_version(tag)
