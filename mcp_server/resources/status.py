"""MCP resources — read-only data exposed via resource URIs."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config


def register(mcp: FastMCP) -> None:
    """Register MCP resources."""

    @mcp.resource("comfyui://status")
    async def system_status() -> str:
        """Current system status: queue, GPU, VRAM, active jobs."""
        config = load_config()
        client = ComfyUIClient(get_instance_url(config))
        try:
            stats = await client.get_system_stats()
            queue = await client.get_queue()
            result = {
                "system": stats,
                "queue": {
                    "running": len(queue.get("queue_running", [])),
                    "pending": len(queue.get("queue_pending", [])),
                },
            }
            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        finally:
            await client.close()

    @mcp.resource("comfyui://models/{model_type}")
    async def models_by_type(model_type: str) -> str:
        """Available models for a given type (checkpoints, loras, vae, etc.)."""
        config = load_config()
        client = ComfyUIClient(get_instance_url(config))
        try:
            type_to_node = {
                "checkpoints": "CheckpointLoaderSimple",
                "loras": "LoraLoader",
                "vae": "VAELoader",
                "controlnet": "ControlNetLoader",
                "embeddings": None,
            }
            if model_type == "embeddings":
                result = await client.get_embeddings()
                return json.dumps(result, indent=2)

            node_name = type_to_node.get(model_type, "CheckpointLoaderSimple")
            info = await client.get_object_info(node_name)
            if node_name in info:
                required = info[node_name].get("input", {}).get("required", {})
                for _key, value in required.items():
                    if isinstance(value, (list, tuple)) and len(value) > 0 and isinstance(value[0], list):
                        return json.dumps(value[0], indent=2)
            return json.dumps([])
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        finally:
            await client.close()

    @mcp.resource("comfyui://nodes")
    async def node_catalog() -> str:
        """Catalog of all available nodes with their input/output signatures."""
        config = load_config()
        client = ComfyUIClient(get_instance_url(config))
        try:
            info = await client.get_object_info()
            catalog = []
            for name, data in info.items():
                catalog.append({
                    "name": name,
                    "display_name": data.get("display_name", name),
                    "category": data.get("category", ""),
                    "inputs": list(data.get("input", {}).get("required", {}).keys()),
                    "outputs": data.get("output", []),
                })
            return json.dumps(catalog, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        finally:
            await client.close()

    @mcp.resource("comfyui://instances")
    async def instance_registry() -> str:
        """Registry of all declared ComfyUI instances and their health."""
        config = load_config()
        return json.dumps(config.get("instances", []), indent=2)
