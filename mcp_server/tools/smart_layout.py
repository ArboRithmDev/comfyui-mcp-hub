"""Smart layout tools — intelligent workflow organization and visual design."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config


async def _ui_command(
    command: str,
    data: dict[str, Any] | None = None,
    timeout: float = 15.0,
    instance: str | None = None,
) -> dict[str, Any]:
    config = load_config()
    client = ComfyUIClient(get_instance_url(config, instance))
    try:
        return await client.post("/mcp-hub/ui/command", data={
            "command": command,
            "data": data or {},
            "timeout": timeout,
        })
    except Exception as exc:
        return {"error": f"UI bridge error: {exc}"}
    finally:
        await client.close()


def register(mcp: FastMCP) -> None:
    """Register smart layout tools on the MCP server."""

    @mcp.tool()
    async def smart_layout(
        colorize: bool = True,
        group: bool = True,
        spacing_x: int = 80,
        spacing_y: int = 40,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Intelligently organize the entire workflow on the canvas.

        Applies a rules-based layout that positions nodes in a left-to-right flow:
        Loaders → Conditioning → ControlNet/IPAdapter → Sampling → Latent/VAE → Upscale → Output.

        Optionally colorizes nodes by category and creates named groups around
        logical sections for easier navigation.

        Args:
            colorize: Apply category-based colors to nodes (default True).
            group: Create named groups around logical sections (default True).
            spacing_x: Horizontal spacing between columns in pixels (default 80).
            spacing_y: Vertical spacing between nodes in pixels (default 40).
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("smart_layout", {
            "colorize": colorize,
            "group": group,
            "spacing": {"x": spacing_x, "y": spacing_y},
        }, instance=instance)

    @mcp.tool()
    async def colorize_nodes(
        scheme: str = "category",
        mapping: dict[str, str] | None = None,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Apply a color scheme to nodes on the canvas.

        Args:
            scheme: Color scheme to apply:
                - "category": color by node type (loaders=green, sampling=red, etc.)
                - "branch": color by connected branch (each output path gets a color)
                - "custom": use the mapping parameter to set colors per node ID
            mapping: For "custom" scheme only — dict of node_id (string) → hex color.
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("colorize_nodes", {
            "scheme": scheme,
            "mapping": mapping or {},
        }, instance=instance)

    @mcp.tool()
    async def auto_group(
        mode: str = "category",
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Automatically detect logical sections and create named groups.

        Groups are visually represented as colored frames around related nodes.
        Existing auto-generated groups are replaced.

        Args:
            mode: Grouping strategy:
                - "category": group by node function (Loaders, Sampling, Output, etc.)
                - "branch": group by connected subgraph from each output node
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("auto_group", {
            "mode": mode,
        }, instance=instance)

    @mcp.tool()
    async def add_frame(
        title: str,
        x: float = 0,
        y: float = 0,
        width: float = 400,
        height: float = 300,
        color: str = "#33555555",
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Add a visual frame/annotation to the canvas.

        Frames are colored rectangles with a title, used to annotate and
        organize sections of a workflow visually.

        Args:
            title: Title displayed on the frame.
            x: X position of the frame.
            y: Y position of the frame.
            width: Width in pixels.
            height: Height in pixels.
            color: Background color (hex with alpha, e.g. "#33555555").
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("add_frame", {
            "title": title, "x": x, "y": y,
            "width": width, "height": height, "color": color,
        }, instance=instance)
