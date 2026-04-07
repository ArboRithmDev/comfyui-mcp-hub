"""Manages the MCP server subprocess lifecycle."""

from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any


def _detect_local_port() -> int:
    """Auto-detect the port ComfyUI is running on."""
    try:
        from server import PromptServer
        port = PromptServer.instance.port
        if port:
            return int(port)
    except Exception:
        pass
    try:
        import comfy.cli_args
        if hasattr(comfy.cli_args, 'port'):
            return int(comfy.cli_args.port)
    except Exception:
        pass
    return 8188


def _detect_local_address() -> str:
    """Auto-detect the address ComfyUI is listening on."""
    try:
        from server import PromptServer
        address = PromptServer.instance.address
        if address:
            return str(address)
    except Exception:
        pass
    try:
        import comfy.cli_args
        if hasattr(comfy.cli_args, 'listen'):
            return str(comfy.cli_args.listen)
    except Exception:
        pass
    return "127.0.0.1"


class MCPProcessManager:
    """Start, stop, and monitor the MCP server as a child process."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._config_path = Path(__file__).parent.parent / "mcp_server" / "hub_config.json"

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self.is_running else None

    def start(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start the MCP server subprocess."""
        if self.is_running:
            return {"status": "already_running", "pid": self._process.pid}

        if config:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(json.dumps(config, indent=2))

        server_module = str(Path(__file__).parent.parent / "mcp_server" / "main.py")
        env = os.environ.copy()
        env["MCP_HUB_CONFIG"] = str(self._config_path)

        self._process = subprocess.Popen(
            [sys.executable, server_module],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        return {"status": "started", "pid": self._process.pid}

    def stop(self) -> dict[str, Any]:
        """Stop the MCP server subprocess."""
        if not self.is_running:
            return {"status": "not_running"}

        pid = self._process.pid
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=2)

        self._process = None
        return {"status": "stopped", "pid": pid}

    def get_status(self) -> dict[str, Any]:
        """Return current server status."""
        if self.is_running:
            return {
                "status": "running",
                "pid": self._process.pid,
            }
        return {"status": "stopped"}

    def get_config(self) -> dict[str, Any]:
        """Load current configuration."""
        if self._config_path.exists():
            return json.loads(self._config_path.read_text())
        return self._default_config()

    def save_config(self, config: dict[str, Any]) -> None:
        """Save configuration to disk."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(config, indent=2))

    def sync_with_comfyui(self) -> None:
        """Sync config with the actual ComfyUI server settings (port, address).

        Called at startup to ensure the MCP config always matches the running
        ComfyUI instance, even if the port changed between restarts.
        """
        port = _detect_local_port()
        address = _detect_local_address()
        config = self.get_config()
        changed = False

        new_url = f"http://{address}:{port}"
        if config.get("comfyui_url") != new_url:
            config["comfyui_url"] = new_url
            changed = True

        # Update the "local" instance entry
        for inst in config.get("instances", []):
            if inst.get("name") == "local":
                if inst.get("host") != address or inst.get("port") != port:
                    inst["host"] = address
                    inst["port"] = port
                    changed = True
                break

        if changed:
            self.save_config(config)
            print(f"[MCP Hub] Config synced with ComfyUI → {new_url}")

    def autostart_enabled(self) -> bool:
        """Check if autostart is enabled in config."""
        return self.get_config().get("autostart", False)

    def try_autostart(self) -> None:
        """Sync config with ComfyUI and start the server if autostart is enabled."""
        self.sync_with_comfyui()
        if self.autostart_enabled() and not self.is_running:
            result = self.start()
            print(f"[MCP Hub] Autostart: {result.get('status')} (pid: {result.get('pid', 'n/a')})")

    def _default_config(self) -> dict[str, Any]:
        port = _detect_local_port()
        return {
            "comfyui_url": f"http://127.0.0.1:{port}",
            "autostart": False,
            "enabled_tools": {
                "introspection": True,
                "workflows": True,
                "generation": True,
                "models": True,
                "packages": True,
                "instances": True,
            },
            "instances": [
                {"name": "local", "host": "127.0.0.1", "port": port, "default": True}
            ],
        }


# Singleton
manager = MCPProcessManager()


# ── Shutdown hooks ────────────────────────────────────────────────────
# Ensure the MCP server subprocess is stopped when ComfyUI exits,
# regardless of how it exits (normal, SIGTERM, SIGINT, etc.)

def _shutdown_handler(*_args: Any) -> None:
    if manager.is_running:
        print("[MCP Hub] Shutting down MCP server...")
        manager.stop()


atexit.register(_shutdown_handler)

# Handle SIGTERM (sent by ComfyUI Desktop when closing the app)
_original_sigterm = signal.getsignal(signal.SIGTERM)


def _sigterm_handler(signum: int, frame: Any) -> None:
    _shutdown_handler()
    # Call previous handler if it was a callable
    if callable(_original_sigterm):
        _original_sigterm(signum, frame)
    else:
        sys.exit(0)


signal.signal(signal.SIGTERM, _sigterm_handler)
