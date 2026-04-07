"""Instance management tools — register and manage ComfyUI instances on the LAN."""

from __future__ import annotations

from typing import Any

import aiohttp
from mcp.server.fastmcp import FastMCP

from ..config import get_instance_url, load_config


def register(mcp: FastMCP) -> None:
    """Register instance management tools on the MCP server."""

    @mcp.tool()
    async def list_instances() -> list[dict[str, Any]]:
        """List all registered ComfyUI instances with their connection info."""
        config = load_config()
        return config.get("instances", [])

    @mcp.tool()
    async def register_instance(
        name: str,
        host: str,
        port: int = 8188,
    ) -> dict[str, Any]:
        """Register a new ComfyUI instance on the network.

        Args:
            name: Friendly name for this instance (e.g. "gpu-server", "render-farm-1").
            host: Hostname or IP address of the ComfyUI instance.
            port: Port number (default: 8188).
        """
        config = load_config()
        instances = config.get("instances", [])

        for inst in instances:
            if inst["name"] == name:
                return {"error": f"Instance '{name}' already exists. Remove it first."}

        new_inst = {"name": name, "host": host, "port": port, "default": False}
        instances.append(new_inst)
        config["instances"] = instances
        _save_config(config)
        return {"status": "registered", "instance": new_inst}

    @mcp.tool()
    async def remove_instance(name: str) -> dict[str, Any]:
        """Remove a ComfyUI instance from the registry.

        Args:
            name: Name of the instance to remove.
        """
        config = load_config()
        instances = config.get("instances", [])

        for inst in instances:
            if inst["name"] == name:
                if inst.get("default"):
                    return {"error": "Cannot remove the default instance. Set another as default first."}
                instances.remove(inst)
                config["instances"] = instances
                _save_config(config)
                return {"status": "removed", "name": name}

        return {"error": f"Instance '{name}' not found."}

    @mcp.tool()
    async def health_check(
        name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Check connectivity and status of ComfyUI instances.

        Args:
            name: Check a specific instance. If omitted, checks all instances.
        """
        config = load_config()
        instances = config.get("instances", [])

        if name:
            instances = [i for i in instances if i["name"] == name]
            if not instances:
                return [{"error": f"Instance '{name}' not found."}]

        results = []
        for inst in instances:
            url = f"http://{inst['host']}:{inst['port']}/system_stats"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        data = await resp.json()
                        results.append({
                            "name": inst["name"],
                            "host": inst["host"],
                            "port": inst["port"],
                            "status": "online",
                            "gpu": data.get("devices", [{}])[0].get("name", "unknown") if data.get("devices") else "unknown",
                            "vram_free_mb": round(
                                data.get("devices", [{}])[0].get("vram_free", 0) / (1024 * 1024), 0
                            ) if data.get("devices") else 0,
                        })
            except Exception as exc:
                results.append({
                    "name": inst["name"],
                    "host": inst["host"],
                    "port": inst["port"],
                    "status": "offline",
                    "error": str(exc),
                })
        return results

    @mcp.tool()
    async def set_default_instance(name: str) -> dict[str, Any]:
        """Set the default ComfyUI instance for all operations.

        Args:
            name: Name of the instance to set as default.
        """
        config = load_config()
        instances = config.get("instances", [])

        found = False
        for inst in instances:
            if inst["name"] == name:
                found = True
            inst["default"] = inst["name"] == name

        if not found:
            return {"error": f"Instance '{name}' not found."}

        config["instances"] = instances
        _save_config(config)
        return {"status": "default_set", "name": name}


def _save_config(config: dict[str, Any]) -> None:
    """Save config back to disk."""
    import json
    import os
    from pathlib import Path

    config_path = os.environ.get(
        "MCP_HUB_CONFIG",
        str(Path(__file__).parent.parent / "hub_config.json"),
    )
    Path(config_path).write_text(json.dumps(config, indent=2))
