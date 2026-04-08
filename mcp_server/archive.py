"""Archive extraction — auto-extract downloaded archives and dispatch files to correct directories."""

from __future__ import annotations

import os
import zipfile
import tarfile
from pathlib import Path
from typing import Any

# Map filename patterns to ComfyUI model subdirectories.
# Order matters — first match wins.
_FILE_ROUTING: list[tuple[list[str], str]] = [
    # CLIP models
    (["clip_g", "clip_l", "clip_h", "text_encoder"], "clip"),
    # CLIP vision
    (["clip_vision", "clipvision"], "clip_vision"),
    # VAE
    (["vae", "sdxl_vae", "ae.safetensors"], "vae"),
    # GGUF quantized models
    ([".gguf"], "unet"),
    # LoRA
    (["lora"], "loras"),
    # ControlNet
    (["controlnet", "control_"], "controlnet"),
    # Upscale
    (["upscale", "esrgan", "realesrgan", "swinir"], "upscale_models"),
    # Embeddings
    (["embedding", "textual_inversion", "ti-"], "embeddings"),
    # UNet / Diffusion models
    (["unet", "diffusion_model"], "diffusion_models"),
]

# File extensions that are model files (should be routed)
_MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx"}

# File extensions that are archives
_ARCHIVE_EXTENSIONS = {".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2"}

# Files to skip during extraction
_SKIP_PATTERNS = {"__MACOSX", ".DS_Store", "Thumbs.db"}


def is_archive(filepath: str | Path) -> bool:
    """Check if a file is a supported archive."""
    path = Path(filepath)
    name = path.name.lower()
    return any(name.endswith(ext) for ext in _ARCHIVE_EXTENSIONS)


def _route_file(filename: str, default_dir: str) -> str:
    """Determine the target subdirectory for a model file based on its name."""
    name_lower = filename.lower()

    # Skip non-model files
    ext = Path(filename).suffix.lower()
    if ext not in _MODEL_EXTENSIONS:
        return ""  # Skip — not a model file

    # Try pattern matching
    for patterns, target_dir in _FILE_ROUTING:
        for pattern in patterns:
            if pattern in name_lower:
                return target_dir

    # Fallback: use the directory the archive was downloaded to
    return default_dir


def extract_and_dispatch(
    archive_path: str | Path,
    models_root: str | Path,
    default_subdir: str = "checkpoints",
) -> dict[str, Any]:
    """Extract an archive and dispatch model files to correct ComfyUI directories.

    Args:
        archive_path: Path to the archive file.
        models_root: Root of the ComfyUI models directory.
        default_subdir: Fallback subdirectory for files that don't match any pattern.

    Returns:
        Dict with extracted files, their destinations, and status.
    """
    archive_path = Path(archive_path)
    models_root = Path(models_root)

    if not archive_path.exists():
        return {"error": f"Archive not found: {archive_path}"}

    result: dict[str, Any] = {
        "archive": str(archive_path),
        "extracted": [],
        "skipped": [],
        "status": "ok",
    }

    try:
        members = _list_archive_members(archive_path)

        for member_name, member_size in members:
            # Skip directories and junk files
            basename = Path(member_name).name
            if not basename or basename.startswith("."):
                continue
            if any(skip in member_name for skip in _SKIP_PATTERNS):
                continue

            target_subdir = _route_file(basename, default_subdir)
            if not target_subdir:
                result["skipped"].append({
                    "file": basename,
                    "reason": "not a model file",
                    "size_mb": round(member_size / (1024 * 1024), 1),
                })
                continue

            target_dir = models_root / target_subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / basename

            # Extract the file
            _extract_member(archive_path, member_name, target_path)

            result["extracted"].append({
                "file": basename,
                "target_dir": target_subdir,
                "path": str(target_path),
                "size_mb": round(member_size / (1024 * 1024), 1),
            })

        # Delete archive if extraction succeeded
        if result["extracted"] and not any("error" in e for e in result["extracted"]):
            archive_path.unlink()
            result["archive_deleted"] = True
        else:
            result["archive_deleted"] = False

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)

    return result


def _list_archive_members(archive_path: Path) -> list[tuple[str, int]]:
    """List archive members as (name, size) tuples."""
    name = archive_path.name.lower()

    if name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as z:
            return [(info.filename, info.file_size) for info in z.infolist() if not info.is_dir()]

    if name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
        with tarfile.open(archive_path) as t:
            return [(m.name, m.size) for m in t.getmembers() if m.isfile()]

    return []


def _extract_member(archive_path: Path, member_name: str, target_path: Path) -> None:
    """Extract a single member from an archive to a specific path."""
    name = archive_path.name.lower()

    if name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as z:
            with z.open(member_name) as src, open(target_path, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)

    elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
        with tarfile.open(archive_path) as t:
            member = t.getmember(member_name)
            src = t.extractfile(member)
            if src:
                with open(target_path, "wb") as dst:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
