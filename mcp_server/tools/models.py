"""Model management tools — list, download, delete, and manage models."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config


def register(mcp: FastMCP) -> None:
    """Register model management tools on the MCP server."""

    @mcp.tool()
    async def download_model(
        url: str,
        model_type: str = "checkpoints",
        filename: str = "",
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Download a model to the ComfyUI models directory. Requires ComfyUI-Manager.

        Args:
            url: Direct download URL for the model file.
            model_type: Target directory type (checkpoints, loras, vae, controlnet, upscale_models, embeddings).
            filename: Target filename. If empty, derived from URL.
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            result = await client.manager_install_model(url, model_type, filename)
            return {"status": "download_queued", "details": result}
        except Exception as exc:
            return {"error": str(exc), "hint": "ComfyUI-Manager must be installed for model downloads."}
        finally:
            await client.close()

    @mcp.tool()
    async def delete_model(
        filename: str,
        model_type: str = "checkpoints",
    ) -> dict[str, Any]:
        """Delete a model file from the local ComfyUI models directory.

        WARNING: This permanently deletes the file. This action cannot be undone.

        Args:
            filename: Name of the model file to delete.
            model_type: Model directory type (checkpoints, loras, vae, etc.).
        """
        from pathlib import Path

        # Resolve the models directory relative to ComfyUI installation
        comfyui_root = Path(__file__).parent.parent.parent.parent.parent
        model_dir = comfyui_root / "models" / model_type
        target = model_dir / filename

        if not target.exists():
            return {"error": f"Model file not found: {filename} in {model_type}"}

        # Safety: ensure we're not escaping the models directory
        try:
            target.resolve().relative_to(model_dir.resolve())
        except ValueError:
            return {"error": "Invalid path — cannot delete files outside the models directory."}

        size_mb = target.stat().st_size / (1024 * 1024)
        return {
            "warning": f"This will permanently delete '{filename}' ({size_mb:.1f} MB). Confirm by calling delete_model_confirm.",
            "filename": filename,
            "model_type": model_type,
            "size_mb": round(size_mb, 1),
        }

    @mcp.tool()
    async def delete_model_confirm(
        filename: str,
        model_type: str = "checkpoints",
    ) -> dict[str, str]:
        """Actually delete a model file after confirmation.

        Args:
            filename: Name of the model file to delete.
            model_type: Model directory type.
        """
        from pathlib import Path

        comfyui_root = Path(__file__).parent.parent.parent.parent.parent
        model_dir = comfyui_root / "models" / model_type
        target = model_dir / filename

        if not target.exists():
            return {"error": f"Model file not found: {filename}"}

        try:
            target.resolve().relative_to(model_dir.resolve())
        except ValueError:
            return {"error": "Invalid path."}

        target.unlink()
        return {"status": "deleted", "filename": filename, "model_type": model_type}

    @mcp.tool()
    async def get_model_info(
        filename: str,
        model_type: str = "checkpoints",
    ) -> dict[str, Any]:
        """Get metadata about a model file (size, hash, modification date).

        Args:
            filename: Name of the model file.
            model_type: Model directory type.
        """
        from pathlib import Path
        import hashlib
        from datetime import datetime

        comfyui_root = Path(__file__).parent.parent.parent.parent.parent
        model_dir = comfyui_root / "models" / model_type
        target = model_dir / filename

        if not target.exists():
            return {"error": f"Model file not found: {filename} in {model_type}"}

        stat = target.stat()
        # Compute partial SHA256 (first 10MB for speed)
        sha256 = hashlib.sha256()
        with open(target, "rb") as f:
            chunk = f.read(10 * 1024 * 1024)
            sha256.update(chunk)

        return {
            "filename": filename,
            "model_type": model_type,
            "size_mb": round(stat.st_size / (1024 * 1024), 1),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "sha256_partial": sha256.hexdigest(),
            "path": str(target),
        }

    @mcp.tool()
    async def unload_models(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Unload all models from VRAM/RAM to free memory.

        Args:
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            result = await client.post("/free", data={"unload_models": True, "free_memory": True})
            return {"status": "models_unloaded", "details": result}
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            await client.close()
