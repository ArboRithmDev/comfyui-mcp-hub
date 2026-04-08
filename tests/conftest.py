"""Shared fixtures for MCP Hub tests.

Prevents pytest from importing the root __init__.py (ComfyUI node entry point)
by pre-populating sys.modules with a stub for the root package.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# The root __init__.py requires ComfyUI runtime (relative imports to .server).
# We pre-register a stub module so Python never attempts to load it when
# resolving `mcp_server` as a sub-package.
_PROJECT_ROOT = Path(__file__).parent.parent
_ROOT_PKG_NAME = _PROJECT_ROOT.name  # "comfyui-mcp-hub" — not a valid Python ident

# Ensure the project root is on sys.path so `import mcp_server` works
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Pre-import mcp_server directly so Python doesn't try to resolve a parent package
import importlib
mcp_server_mod = importlib.import_module("mcp_server")
sys.modules.setdefault("mcp_server", mcp_server_mod)


@pytest.fixture
def tmp_models_dir(tmp_path: Path) -> Path:
    """Temporary directory for downloaded model files."""
    d = tmp_path / "models"
    d.mkdir()
    return d
