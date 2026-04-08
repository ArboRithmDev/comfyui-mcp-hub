"""ComfyUI MCP Hub — Local MCP server and control panel for ComfyUI."""

import os
import subprocess
import sys
from pathlib import Path


def _running_in_comfyui() -> bool:
    """Detect whether we are being loaded by ComfyUI (vs. pytest/scripts)."""
    # ComfyUI sets up PromptServer or imports from custom_nodes
    return "comfy" in sys.modules or "server" in sys.modules or "nodes" in sys.modules


# Only run ComfyUI-specific initialization when loaded by ComfyUI itself.
# This allows pytest and other tools to import subpackages (mcp_server/)
# without triggering side effects or missing ComfyUI runtime dependencies.
if _running_in_comfyui():
    # ── Auto-install ComfyUI-Manager (required dependency) ────────────────

    _CUSTOM_NODES_DIR = Path(__file__).parent.parent
    _MANAGER_DIR = _CUSTOM_NODES_DIR / "comfyui-manager"
    _MANAGER_REPO = "https://github.com/ltdrdata/ComfyUI-Manager"


    def _ensure_manager() -> None:
        """Install ComfyUI-Manager if not present — required for package/model management."""
        if _MANAGER_DIR.exists():
            return
        print("[MCP Hub] ComfyUI-Manager not found — installing (required dependency)...")
        try:
            subprocess.check_call(
                ["git", "clone", _MANAGER_REPO, str(_MANAGER_DIR)],
                timeout=120,
            )
            # Install Manager's own dependencies
            req_file = _MANAGER_DIR / "requirements.txt"
            if req_file.exists():
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(req_file)],
                    timeout=120,
                )
            print("[MCP Hub] ComfyUI-Manager installed. A restart of ComfyUI is required to activate it.")
        except Exception as exc:
            print(f"[MCP Hub] WARNING: Failed to install ComfyUI-Manager: {exc}")
            print(f"[MCP Hub] Please install it manually: git clone {_MANAGER_REPO} {_MANAGER_DIR}")


    _ensure_manager()

    # ── Auto-install pip dependencies ─────────────────────────────────────

    _DEPENDENCIES = [
        ("mcp", "mcp>=1.0.0"),
        ("aiohttp", "aiohttp>=3.9.0"),
        ("websockets", "websockets>=12.0"),
    ]


    def _ensure_dependencies() -> None:
        """Check and install missing pip dependencies at startup."""
        missing = []
        for import_name, pip_spec in _DEPENDENCIES:
            try:
                __import__(import_name)
            except ImportError:
                missing.append(pip_spec)

        if missing:
            print(f"[MCP Hub] Installing missing dependencies: {', '.join(missing)}")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--quiet"] + missing
                )
                print("[MCP Hub] Dependencies installed successfully.")
            except subprocess.CalledProcessError as exc:
                print(f"[MCP Hub] WARNING: Failed to install dependencies: {exc}")
                print(f"[MCP Hub] Please run manually: pip install {' '.join(missing)}")


    _ensure_dependencies()

    # ── Register routes and panel ─────────────────────────────────────────

    from .server import routes  # noqa: E402, F401 — registers REST endpoints on import
    from .server import ui_bridge  # noqa: E402, F401 — registers UI bridge endpoints
    from .server import activity_log  # noqa: E402, F401 — registers activity log endpoints
    from .server.process_manager import manager  # noqa: E402

    # ── Autostart MCP server if configured ────────────────────────────────

    manager.try_autostart()

    # ── Check for updates (non-blocking) ──────────────────────────────────

    import threading
    from .server.updater import check_for_update

    def _check_update_bg():
        try:
            info = check_for_update()
            if info.get("update_available"):
                print(f"[MCP Hub] Update available: v{info['latest']} (current: v{info['current']})")
        except Exception:
            pass

    threading.Thread(target=_check_update_bg, daemon=True).start()

# ── ComfyUI registration ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
