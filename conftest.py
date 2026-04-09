"""Root conftest — prevents pytest from importing the ComfyUI node __init__.py.

The root __init__.py requires ComfyUI runtime. We register a stub in sys.modules
so Python's import machinery never tries to load it when resolving mcp_server.
"""

import sys
import types
from pathlib import Path

# Register a fake root package so Python won't load the real __init__.py
_root = Path(__file__).parent
_pkg_name = _root.name  # "comfyui-arbo-mcp-hub"

# Ensure project root is on sys.path for direct mcp_server imports
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Pre-load mcp_server as a standalone package (not a sub-package of root)
if "mcp_server" not in sys.modules:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mcp_server",
        str(_root / "mcp_server" / "__init__.py"),
        submodule_search_locations=[str(_root / "mcp_server")],
    )
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["mcp_server"] = mod
        # Don't execute the module — just register the namespace
        # so submodule imports resolve correctly
        mod.__path__ = [str(_root / "mcp_server")]
        mod.__package__ = "mcp_server"


collect_ignore = ["__init__.py", "server", "web", "install.py"]
