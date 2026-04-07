"""Detect installed AI CLIs and manage their MCP server configuration."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Any


def _home() -> Path:
    return Path.home()


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _mcp_server_main() -> str:
    return str(Path(__file__).parent.parent / "mcp_server" / "main.py")


def _python_exe() -> str:
    return sys.executable


# ── Base CLI Definition ──────────────────────────────────────────────


class CLIDefinition:
    """Base definition for an AI CLI with JSON-based MCP config."""

    config_format = "json"

    def __init__(
        self,
        name: str,
        display_name: str,
        binary_names: list[str],
        config_paths: list[Path],
        mcp_key: str,
        server_key: str = "comfyui-mcp-hub",
        note: str = "",
    ):
        self.name = name
        self.display_name = display_name
        self.binary_names = binary_names
        self.config_paths = config_paths
        self.mcp_key = mcp_key
        self.server_key = server_key
        self.note = note  # Extra info shown in UI (e.g. "No native MCP support")

    def is_installed(self) -> bool:
        return any(shutil.which(b) is not None for b in self.binary_names)

    def binary_path(self) -> str | None:
        for b in self.binary_names:
            path = shutil.which(b)
            if path:
                return path
        return None

    def config_path(self) -> Path | None:
        for p in self.config_paths:
            if p.exists():
                return p
        return self.config_paths[0] if self.config_paths else None

    def is_configured(self) -> bool:
        path = self.config_path()
        if not path or not path.exists():
            return False
        try:
            return self._check_configured(path)
        except Exception:
            return False

    def configure(self) -> dict[str, Any]:
        path = self.config_path()
        if not path:
            return {"error": f"No config path found for {self.display_name}"}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_config(path)
            return {"status": "configured", "cli": self.name, "config_path": str(path)}
        except Exception as exc:
            return {"error": str(exc)}

    def unconfigure(self) -> dict[str, Any]:
        path = self.config_path()
        if not path or not path.exists():
            return {"error": f"Config file not found for {self.display_name}"}
        try:
            self._remove_config(path)
            return {"status": "removed", "cli": self.name}
        except Exception as exc:
            return {"error": str(exc)}

    def can_configure(self) -> bool:
        """Whether this CLI supports auto-configuration."""
        return True

    # ── JSON implementation (default) ─────────────────────────────────

    def _check_configured(self, path: Path) -> bool:
        config = json.loads(path.read_text())
        servers = config.get(self.mcp_key, {})
        return self.server_key in servers

    def _write_config(self, path: Path) -> None:
        if path.exists():
            config = json.loads(path.read_text())
        else:
            config = {}
        if self.mcp_key not in config:
            config[self.mcp_key] = {}
        config[self.mcp_key][self.server_key] = {
            "command": _python_exe(),
            "args": [_mcp_server_main()],
            "env": {},
        }
        path.write_text(json.dumps(config, indent=2))

    def _remove_config(self, path: Path) -> None:
        config = json.loads(path.read_text())
        servers = config.get(self.mcp_key, {})
        if self.server_key in servers:
            del servers[self.server_key]
            config[self.mcp_key] = servers
            path.write_text(json.dumps(config, indent=2))

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "display_name": self.display_name,
            "installed": self.is_installed(),
            "binary_path": self.binary_path(),
            "config_path": str(self.config_path()) if self.config_path() else None,
            "configured": self.is_configured(),
            "can_configure": self.can_configure(),
            "config_format": self.config_format,
        }
        if self.note:
            result["note"] = self.note
        return result


# ── TOML-based CLI Definition ────────────────────────────────────────


class TOMLCLIDefinition(CLIDefinition):
    """CLI that uses TOML config files (Gemini, Codex, Mistral Vibe)."""

    config_format = "toml"

    def __init__(
        self,
        *args: Any,
        toml_style: str = "section",  # "section" or "array"
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.toml_style = toml_style  # "section" for [mcp_servers.name], "array" for [[mcp_servers]]

    def _check_configured(self, path: Path) -> bool:
        content = path.read_text()
        if self.toml_style == "array":
            # Mistral Vibe: [[mcp_servers]] with name = "comfyui-mcp-hub"
            return f'name = "{self.server_key}"' in content
        else:
            # Codex/Gemini: [mcp_servers.comfyui-mcp-hub] or "comfyui-mcp-hub" in mcpServers
            return f"[{self.mcp_key}.{self.server_key}]" in content or f'"{self.server_key}"' in content

    def _write_config(self, path: Path) -> None:
        if path.exists():
            content = path.read_text()
        else:
            content = ""

        if self._check_configured_in_content(content):
            return  # Already configured

        block = self._build_toml_block()
        content = content.rstrip() + "\n\n" + block + "\n"
        path.write_text(content)

    def _check_configured_in_content(self, content: str) -> bool:
        if self.toml_style == "array":
            return f'name = "{self.server_key}"' in content
        return f"[{self.mcp_key}.{self.server_key}]" in content

    def _build_toml_block(self) -> str:
        if self.toml_style == "array":
            # Mistral Vibe format: [[mcp_servers]]
            return (
                f"[[{self.mcp_key}]]\n"
                f'name = "{self.server_key}"\n'
                f'transport = "stdio"\n'
                f'command = "{_python_exe()}"\n'
                f'args = ["{_mcp_server_main()}"]\n'
            )
        else:
            # Codex/Gemini section format: [mcp_servers.comfyui-mcp-hub]
            return (
                f"[{self.mcp_key}.{self.server_key}]\n"
                f'command = "{_python_exe()}"\n'
                f'args = ["{_mcp_server_main()}"]\n'
            )

    def _remove_config(self, path: Path) -> None:
        content = path.read_text()

        if self.toml_style == "array":
            # Remove [[mcp_servers]] block containing name = "comfyui-mcp-hub"
            pattern = (
                r'\[\[' + re.escape(self.mcp_key) + r'\]\]\s*\n'
                r'(?:(?!\[\[).)*?'
                r'name\s*=\s*"' + re.escape(self.server_key) + r'"'
                r'(?:(?!\[\[).)*?\n'
            )
            content = re.sub(pattern, "", content, flags=re.DOTALL)
        else:
            # Remove [mcp_servers.comfyui-mcp-hub] section
            pattern = (
                r'\[' + re.escape(self.mcp_key) + r'\.' + re.escape(self.server_key) + r'\]\s*\n'
                r'(?:(?!\[).)*'
            )
            content = re.sub(pattern, "", content, flags=re.DOTALL)

        # Clean up extra blank lines
        content = re.sub(r'\n{3,}', '\n\n', content).strip() + "\n"
        path.write_text(content)


# ── Gemini CLI (JSON-based mcpServers in settings.json) ──────────────


class GeminiCLIDefinition(CLIDefinition):
    """Gemini CLI uses JSON settings.json with mcpServers key."""

    config_format = "json"

    def _write_config(self, path: Path) -> None:
        if path.exists():
            config = json.loads(path.read_text())
        else:
            config = {}
        if self.mcp_key not in config:
            config[self.mcp_key] = {}
        config[self.mcp_key][self.server_key] = {
            "command": _python_exe(),
            "args": [_mcp_server_main()],
            "env": {},
            "timeout": 30000,
        }
        path.write_text(json.dumps(config, indent=2))


# ── Non-configurable CLI (info only) ─────────────────────────────────


class InfoOnlyCLIDefinition(CLIDefinition):
    """CLI detected but not auto-configurable (e.g. Ollama without native MCP)."""

    config_format = "none"

    def can_configure(self) -> bool:
        return False

    def is_configured(self) -> bool:
        return False

    def configure(self) -> dict[str, Any]:
        return {"error": f"{self.display_name}: {self.note}"}

    def unconfigure(self) -> dict[str, Any]:
        return {"error": f"{self.display_name}: {self.note}"}


# ── Registry of known AI CLIs ───────────────────────────────────────


def _build_cli_registry() -> list[CLIDefinition]:
    """Build the list of known AI CLIs with platform-specific paths."""
    home = _home()
    clis: list[CLIDefinition] = []

    # ── Claude Code (CLI) ─────────────────────────────────────────
    clis.append(CLIDefinition(
        name="claude-code",
        display_name="Claude Code (CLI)",
        binary_names=["claude"],
        config_paths=[home / ".claude.json"],
        mcp_key="mcpServers",
    ))

    # ── Claude Desktop ────────────────────────────────────────────
    if _is_macos():
        desktop_paths = [home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"]
    elif _is_windows():
        appdata = Path(os.environ.get("APPDATA", ""))
        desktop_paths = [appdata / "Claude" / "claude_desktop_config.json"]
    else:
        desktop_paths = [home / ".config" / "claude" / "claude_desktop_config.json"]

    clis.append(CLIDefinition(
        name="claude-desktop",
        display_name="Claude Desktop",
        binary_names=["claude-desktop"],
        config_paths=desktop_paths,
        mcp_key="mcpServers",
    ))

    # ── Gemini CLI (Google) ───────────────────────────────────────
    clis.append(GeminiCLIDefinition(
        name="gemini",
        display_name="Gemini CLI",
        binary_names=["gemini"],
        config_paths=[home / ".gemini" / "settings.json"],
        mcp_key="mcpServers",
    ))

    # ── Codex CLI (OpenAI) ────────────────────────────────────────
    clis.append(TOMLCLIDefinition(
        name="codex",
        display_name="Codex CLI (OpenAI)",
        binary_names=["codex"],
        config_paths=[home / ".codex" / "config.toml"],
        mcp_key="mcp_servers",
        toml_style="section",
    ))

    # ── Mistral Vibe ──────────────────────────────────────────────
    clis.append(TOMLCLIDefinition(
        name="mistral-vibe",
        display_name="Mistral Vibe",
        binary_names=["vibe", "mistral"],
        config_paths=[home / ".vibe" / "config.toml"],
        mcp_key="mcp_servers",
        toml_style="array",
    ))

    # ── Cursor ────────────────────────────────────────────────────
    clis.append(CLIDefinition(
        name="cursor",
        display_name="Cursor",
        binary_names=["cursor"],
        config_paths=[home / ".cursor" / "mcp.json"],
        mcp_key="mcpServers",
    ))

    # ── Windsurf (Codeium) ────────────────────────────────────────
    clis.append(CLIDefinition(
        name="windsurf",
        display_name="Windsurf",
        binary_names=["windsurf"],
        config_paths=[home / ".codeium" / "windsurf" / "mcp_config.json"],
        mcp_key="mcpServers",
    ))

    # ── Continue.dev ──────────────────────────────────────────────
    clis.append(CLIDefinition(
        name="continue",
        display_name="Continue.dev",
        binary_names=["continue"],
        config_paths=[home / ".continue" / "config.json"],
        mcp_key="mcpServers",
    ))

    # ── VS Code ───────────────────────────────────────────────────
    if _is_macos():
        vscode_paths = [home / "Library" / "Application Support" / "Code" / "User" / "settings.json"]
    elif _is_windows():
        appdata = Path(os.environ.get("APPDATA", ""))
        vscode_paths = [appdata / "Code" / "User" / "settings.json"]
    else:
        vscode_paths = [home / ".config" / "Code" / "User" / "settings.json"]

    clis.append(CLIDefinition(
        name="vscode",
        display_name="VS Code",
        binary_names=["code"],
        config_paths=vscode_paths,
        mcp_key="mcp.servers",
    ))

    # ── Ollama (no native MCP — info only) ────────────────────────
    clis.append(InfoOnlyCLIDefinition(
        name="ollama",
        display_name="Ollama",
        binary_names=["ollama"],
        config_paths=[],
        mcp_key="",
        note="No native MCP support. Use MCPHost or another MCP client to bridge Ollama with MCP servers.",
    ))

    return clis


# ── Public API ───────────────────────────────────────────────────────

_registry: list[CLIDefinition] | None = None


def _get_registry() -> list[CLIDefinition]:
    global _registry
    if _registry is None:
        _registry = _build_cli_registry()
    return _registry


def detect_clis() -> list[dict[str, Any]]:
    """Detect all known AI CLIs and their configuration status."""
    return [cli.to_dict() for cli in _get_registry()]


def configure_cli(name: str) -> dict[str, Any]:
    """Configure a specific CLI to use the MCP Hub server."""
    for cli in _get_registry():
        if cli.name == name:
            return cli.configure()
    return {"error": f"Unknown CLI: {name}"}


def unconfigure_cli(name: str) -> dict[str, Any]:
    """Remove MCP Hub configuration from a specific CLI."""
    for cli in _get_registry():
        if cli.name == name:
            return cli.unconfigure()
    return {"error": f"Unknown CLI: {name}"}


def configure_all() -> list[dict[str, Any]]:
    """Configure all detected and configurable CLIs."""
    results = []
    for cli in _get_registry():
        if not cli.can_configure():
            continue
        if cli.is_installed() or (cli.config_path() and cli.config_path().exists()):
            results.append(cli.configure())
    return results
