"""Post-installation script for ComfyUI-Manager compatibility.

ComfyUI-Manager calls this script after cloning the repo.
It ensures all dependencies are installed in the current environment.
"""

import subprocess
import sys
from pathlib import Path

requirements = Path(__file__).parent / "requirements.txt"

if requirements.exists():
    print("[MCP Hub] Installing dependencies...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "--quiet", "-r", str(requirements),
    ])
    print("[MCP Hub] Dependencies installed successfully.")
else:
    print("[MCP Hub] No requirements.txt found, skipping.")
