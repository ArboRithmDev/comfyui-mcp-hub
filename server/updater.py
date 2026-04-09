"""Version management — check for updates, upgrade, and downgrade via git tags."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

_REPO_DIR = Path(__file__).parent.parent
_GITHUB_REPO = "ArboRithmDev/comfyui-arbo-mcp-hub"
_RELEASES_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases"


def get_current_version() -> str:
    """Read the current version from pyproject.toml."""
    pyproject = _REPO_DIR / "pyproject.toml"
    if not pyproject.exists():
        return "unknown"
    for line in pyproject.read_text().splitlines():
        if line.strip().startswith("version"):
            # version = "0.3.0"
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "unknown"


def get_current_tag() -> str:
    """Get the current git tag (if HEAD is on a tag)."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            cwd=str(_REPO_DIR), capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def fetch_releases() -> list[dict[str, Any]]:
    """Fetch all releases from GitHub API."""
    try:
        req = urllib.request.Request(
            _RELEASES_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "comfyui-arbo-mcp-hub"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if not isinstance(data, list):
            return []
        return [
            {
                "tag": r.get("tag_name", ""),
                "name": r.get("name", r.get("tag_name", "")),
                "body": r.get("body", ""),
                "published_at": r.get("published_at", ""),
                "prerelease": r.get("prerelease", False),
            }
            for r in data
            if r.get("tag_name")
        ]
    except Exception as exc:
        return [{"error": str(exc)}]


def check_for_update() -> dict[str, Any]:
    """Check if a newer version is available."""
    current = get_current_version()
    releases = fetch_releases()

    if not releases:
        return {"current": current, "latest": current, "update_available": False}
    if "error" in releases[0]:
        return {"current": current, "error": releases[0]["error"]}

    # Filter out pre-releases for the "latest" check
    stable = [r for r in releases if not r.get("prerelease")]
    latest = stable[0] if stable else releases[0]
    latest_tag = latest["tag"]
    latest_version = latest_tag.lstrip("v")

    return {
        "current": current,
        "latest": latest_version,
        "latest_tag": latest_tag,
        "update_available": latest_version != current,
        "release_name": latest.get("name", ""),
        "release_notes": latest.get("body", ""),
    }


def list_versions() -> dict[str, Any]:
    """List all available versions with the current one marked."""
    current = get_current_version()
    current_tag = get_current_tag()
    releases = fetch_releases()

    if releases and "error" in releases[0]:
        return {"current": current, "error": releases[0]["error"], "versions": []}

    versions = []
    for r in releases:
        tag = r["tag"]
        version = tag.lstrip("v")
        versions.append({
            "tag": tag,
            "version": version,
            "name": r.get("name", ""),
            "notes": r.get("body", ""),
            "date": r.get("published_at", ""),
            "prerelease": r.get("prerelease", False),
            "is_current": version == current or tag == current_tag,
        })

    return {"current": current, "current_tag": current_tag, "versions": versions}


def switch_version(tag: str) -> dict[str, Any]:
    """Switch to a specific version by git tag.

    Args:
        tag: The git tag to checkout (e.g. "v0.4.0").

    Returns:
        Dict with status and details.
    """
    if not tag:
        return {"error": "No tag specified"}

    try:
        # Fetch latest tags from remote
        subprocess.run(
            ["git", "fetch", "--tags", "--force"],
            cwd=str(_REPO_DIR), capture_output=True, text=True, timeout=30,
        )

        # Verify tag exists
        result = subprocess.run(
            ["git", "tag", "-l", tag],
            cwd=str(_REPO_DIR), capture_output=True, text=True, timeout=10,
        )
        if tag not in result.stdout.strip().split("\n"):
            return {"error": f"Tag '{tag}' not found. Run 'Check for updates' first."}

        # Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(_REPO_DIR), capture_output=True, text=True, timeout=10,
        )
        if status.stdout.strip():
            return {"error": "There are uncommitted changes. Please commit or stash them first."}

        # Checkout the tag (detached HEAD)
        checkout = subprocess.run(
            ["git", "checkout", tag],
            cwd=str(_REPO_DIR), capture_output=True, text=True, timeout=30,
        )
        if checkout.returncode != 0:
            return {"error": f"Git checkout failed: {checkout.stderr.strip()}"}

        new_version = get_current_version()
        return {
            "status": "switched",
            "tag": tag,
            "version": new_version,
            "message": f"Switched to {tag} ({new_version}). Restart ComfyUI to apply changes.",
        }
    except subprocess.TimeoutExpired:
        return {"error": "Git operation timed out"}
    except Exception as exc:
        return {"error": str(exc)}
