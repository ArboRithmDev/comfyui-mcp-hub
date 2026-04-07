"""Configuration management for the MCP server."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_config() -> dict[str, Any]:
    """Load configuration from file or return defaults."""
    config_path = os.environ.get(
        "MCP_HUB_CONFIG",
        str(Path(__file__).parent / "hub_config.json"),
    )
    path = Path(config_path)
    if path.exists():
        return json.loads(path.read_text())
    return default_config()


def default_config() -> dict[str, Any]:
    return {
        "comfyui_url": "http://127.0.0.1:8188",
        "autostart": False,
        "civitai_token": "",
        "huggingface_token": "",
        "nsfw_filter": "soft",
        "auto_resolve_on_execute": True,
        "enabled_tools": {
            "introspection": True,
            "workflows": True,
            "generation": True,
            "models": True,
            "packages": True,
            "instances": True,
        },
        "instances": [
            {"name": "local", "host": "127.0.0.1", "port": 8188, "default": True}
        ],
    }


def get_instance_url(config: dict[str, Any], instance_name: str | None = None) -> str:
    """Resolve the ComfyUI base URL for a given instance."""
    instances = config.get("instances", [])
    if instance_name:
        for inst in instances:
            if inst["name"] == instance_name:
                return f"http://{inst['host']}:{inst['port']}"
    # Return default
    for inst in instances:
        if inst.get("default"):
            return f"http://{inst['host']}:{inst['port']}"
    return config.get("comfyui_url", "http://127.0.0.1:8188")
