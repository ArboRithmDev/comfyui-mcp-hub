"""Introspection tools — discover nodes, models, and system capabilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config

_MODEL_EXTS = {".safetensors", ".pt", ".pth", ".ckpt", ".bin", ".onnx", ".gguf"}


def _scan_model_directory(model_type: str) -> list[str]:
    """Scan the filesystem for model files in a given subdirectory."""
    models_root = Path(__file__).parent.parent.parent.parent.parent / "models"
    target = models_root / model_type
    if not target.exists():
        return [f"Directory not found: models/{model_type}"]
    files = []
    for f in sorted(target.rglob("*")):
        if f.is_file() and f.suffix.lower() in _MODEL_EXTS:
            # Return path relative to the model_type directory
            rel = f.relative_to(target)
            files.append(str(rel))
    return files


def register(mcp: FastMCP) -> None:
    """Register introspection tools on the MCP server."""

    @mcp.tool()
    async def list_nodes(
        category: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """List available ComfyUI nodes with pagination. Filter by category or search term.

        Returns at most `limit` nodes starting from `offset`. Use for browsing
        large node lists without consuming excessive tokens.

        Args:
            category: Filter nodes by category (e.g. "sampling", "loaders").
            search: Search term to filter node names.
            limit: Maximum number of nodes to return (default 50, max 200).
            offset: Number of nodes to skip (for pagination).
            instance: Target ComfyUI instance name. Uses default if omitted.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            info = await client.get_object_info()
            nodes = []
            for name, data in info.items():
                node_cat = data.get("category") or ""
                if category and category.lower() not in node_cat.lower():
                    continue
                display = data.get("display_name") or ""
                if search and search.lower() not in name.lower() and search.lower() not in display.lower():
                    continue
                nodes.append({
                    "name": name,
                    "display_name": data.get("display_name", name),
                    "category": node_cat,
                    "description": data.get("description", ""),
                    "input_types": list(data.get("input", {}).get("required", {}).keys()),
                    "output_types": data.get("output", []),
                })

            total = len(nodes)
            limit = min(limit, 200)
            page = nodes[offset:offset + limit]
            return {
                "nodes": page,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": (offset + limit) < total,
            }
        finally:
            await client.close()

    @mcp.tool()
    async def get_node_info(
        node_name: str,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Get detailed information about a specific ComfyUI node.

        Args:
            node_name: The class name of the node (e.g. "KSampler").
            instance: Target ComfyUI instance name. Uses default if omitted.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            info = await client.get_object_info(node_name)
            if node_name in info:
                return info[node_name]
            return {"error": f"Node '{node_name}' not found"}
        finally:
            await client.close()

    @mcp.tool()
    async def list_models(
        model_type: str = "checkpoints",
        instance: str | None = None,
    ) -> list[str]:
        """List available models by type.

        Supports both standard ComfyUI model types (checkpoints, loras, vae, etc.)
        and any custom model directory (ultralytics/bbox, text_encoders, LLM, SEEDVR2, etc.).
        Use list_model_types to discover all available directories.

        Args:
            model_type: Model directory name. Examples: checkpoints, loras, vae, controlnet, clip,
                        clip_vision, ipadapter, upscale_models, unet, diffusion_models, embeddings,
                        ultralytics, ultralytics/bbox, text_encoders, LLM, vae_approx, etc.
            instance: Target ComfyUI instance name. Uses default if omitted.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            # First try via loader nodes (gives the exact list ComfyUI uses)
            type_to_loader: dict[str, tuple[str, str]] = {
                "checkpoints":      ("CheckpointLoaderSimple", "ckpt_name"),
                "loras":            ("LoraLoader", "lora_name"),
                "vae":              ("VAELoader", "vae_name"),
                "controlnet":       ("ControlNetLoader", "control_net_name"),
                "clip":             ("CLIPLoader", "clip_name"),
                "clip_vision":      ("CLIPVisionLoader", "clip_name"),
                "ipadapter":        ("IPAdapterModelLoader", "ipadapter_file"),
                "upscale_models":   ("UpscaleModelLoader", "model_name"),
                "unet":             ("UNETLoader", "unet_name"),
                "diffusion_models": ("UNETLoader", "unet_name"),
                "hypernetworks":    ("HypernetworkLoader", "hypernetwork_name"),
                "embeddings":       (None, None),
            }

            if model_type == "embeddings":
                return await client.get_embeddings()

            loader = type_to_loader.get(model_type)
            if loader:
                node_name, field_name = loader
                try:
                    info = await client.get_object_info(node_name)
                    if node_name in info:
                        required = info[node_name].get("input", {}).get("required", {})
                        if field_name in required:
                            value = required[field_name]
                            if isinstance(value, (list, tuple)) and len(value) > 0 and isinstance(value[0], list):
                                return value[0]
                        for _key, value in required.items():
                            if isinstance(value, (list, tuple)) and len(value) > 0 and isinstance(value[0], list):
                                return value[0]
                except Exception:
                    pass  # Fall through to filesystem scan

            # Filesystem scan — works for any directory including custom ones
            return _scan_model_directory(model_type)
        finally:
            await client.close()

    @mcp.tool()
    async def list_model_types(
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all available model directories with file counts.

        Returns every subdirectory in the ComfyUI models folder, including
        custom directories like ultralytics/bbox, text_encoders, LLM, etc.

        Args:
            instance: Target ComfyUI instance name. Uses default if omitted.
        """
        from pathlib import Path
        models_root = Path(__file__).parent.parent.parent.parent.parent / "models"
        if not models_root.exists():
            return [{"error": f"Models directory not found: {models_root}"}]

        model_exts = {".safetensors", ".pt", ".pth", ".ckpt", ".bin", ".onnx", ".gguf"}
        result = []

        def _scan(directory: Path, prefix: str = "") -> None:
            if not directory.is_dir():
                return
            for entry in sorted(directory.iterdir()):
                rel_name = f"{prefix}/{entry.name}" if prefix else entry.name
                if entry.is_dir():
                    # Count model files in this directory
                    files = [f for f in entry.rglob("*") if f.is_file() and f.suffix.lower() in model_exts]
                    if files:
                        result.append({
                            "type": rel_name,
                            "count": len(files),
                            "files": [f.name for f in files[:5]],  # Preview first 5
                        })
                    # Recurse into subdirectories
                    for sub in sorted(entry.iterdir()):
                        if sub.is_dir():
                            sub_files = [f for f in sub.rglob("*") if f.is_file() and f.suffix.lower() in model_exts]
                            if sub_files:
                                result.append({
                                    "type": f"{rel_name}/{sub.name}",
                                    "count": len(sub_files),
                                    "files": [f.name for f in sub_files[:5]],
                                })

        _scan(models_root)
        return result

    @mcp.tool()
    async def get_system_stats(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Get system statistics: GPU info, VRAM usage, queue status.

        Args:
            instance: Target ComfyUI instance name. Uses default if omitted.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            stats = await client.get_system_stats()
            queue = await client.get_queue()
            return {
                "system": stats,
                "queue": {
                    "running": len(queue.get("queue_running", [])),
                    "pending": len(queue.get("queue_pending", [])),
                },
            }
        finally:
            await client.close()
