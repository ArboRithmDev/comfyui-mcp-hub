"""Async client for the CivitAI API v1."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any

import aiohttp

_BASE_URL = "https://civitai.com/api/v1"

# CivitAI model type → ComfyUI models subdirectory
MODEL_TYPE_MAP: dict[str, str] = {
    "Checkpoint": "checkpoints",
    "TextualInversion": "embeddings",
    "Hypernetwork": "hypernetworks",
    "AestheticGradient": "checkpoints",
    "LORA": "loras",
    "LoCon": "loras",
    "DoRA": "loras",
    "Controlnet": "controlnet",
    "Upscaler": "upscale_models",
    "VAE": "vae",
    "Poses": "poses",
    "Wildcards": "wildcards",
    "MotionModule": "animatediff_motion_lora",
    "Other": "checkpoints",
}

# NSFW filter levels → CivitAI nsfw ratings to exclude
_NSFW_FILTERS: dict[str, set[str]] = {
    "none": {"Soft", "Mature", "X"},
    "soft": {"Mature", "X"},
    "mature": {"X"},
    "x": set(),
}


class CivitAIClient:
    """Async client for CivitAI API with auth, NSFW filtering, and download support."""

    def __init__(
        self,
        token: str = "",
        nsfw_filter: str = "soft",
        models_root: str | Path = "",
    ) -> None:
        self.token = token
        self.nsfw_filter = nsfw_filter
        self.models_root = Path(models_root) if models_root else None
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            # Large model downloads can take 30+ minutes on slow connections.
            # Default aiohttp total timeout (300s) truncates these transfers.
            timeout = aiohttp.ClientTimeout(
                total=None,       # No total timeout — let downloads finish
                connect=30,       # 30s to establish connection
                sock_read=120,    # 120s between chunks (detects stalled transfers)
            )
            self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _should_exclude(self, nsfw_rating: str) -> bool:
        """Check if a result should be excluded based on NSFW filter."""
        excluded = _NSFW_FILTERS.get(self.nsfw_filter, set())
        return nsfw_rating in excluded

    # ── Search ────────────────────────────────────────────────────────

    async def search_models(
        self,
        query: str,
        model_type: str | None = None,
        sort: str = "Highest Rated",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search CivitAI for models.

        Args:
            query: Search text.
            model_type: Filter by type (Checkpoint, LORA, VAE, etc.).
            sort: Sort order (Highest Rated, Most Downloaded, Newest).
            limit: Max results to return.
        """
        session = await self._get_session()
        params: dict[str, Any] = {
            "query": query,
            "limit": min(limit * 2, 20),  # Fetch extra to account for NSFW filtering
            "sort": sort,
        }
        if model_type:
            params["types"] = model_type
        if self.nsfw_filter == "none":
            params["nsfw"] = "false"

        async with session.get(f"{_BASE_URL}/models", params=params) as resp:
            if resp.status == 429:
                return [{"error": "Rate limited by CivitAI. Try again later or add an API token."}]
            resp.raise_for_status()
            data = await resp.json()

        results = []
        for item in data.get("items", []):
            nsfw_rating = item.get("nsfw", False)
            # CivitAI returns nsfw as bool or string depending on endpoint
            if isinstance(nsfw_rating, bool):
                nsfw_label = "X" if nsfw_rating else "None"
            else:
                nsfw_label = str(nsfw_rating)

            if self._should_exclude(nsfw_label):
                continue

            # Get the latest version info
            versions = item.get("modelVersions", [])
            latest = versions[0] if versions else {}
            files = latest.get("files", [])
            primary_file = files[0] if files else {}

            results.append({
                "id": item.get("id"),
                "name": item.get("name", ""),
                "type": item.get("type", ""),
                "nsfw": nsfw_label,
                "description": (item.get("description") or "")[:200],
                "tags": item.get("tags", [])[:5],
                "stats": {
                    "rating": item.get("stats", {}).get("rating", 0),
                    "downloads": item.get("stats", {}).get("downloadCount", 0),
                },
                "version": {
                    "id": latest.get("id"),
                    "name": latest.get("name", ""),
                    "download_url": latest.get("downloadUrl", ""),
                    "filename": primary_file.get("name", ""),
                    "size_mb": round(primary_file.get("sizeKB", 0) / 1024, 1),
                    "sha256": (primary_file.get("hashes", {}) or {}).get("SHA256", ""),
                },
                "civitai_url": f"https://civitai.com/models/{item.get('id')}",
            })

            if len(results) >= limit:
                break

        return results

    # ── Lookup by hash ────────────────────────────────────────────────

    async def find_by_hash(self, sha256: str) -> dict[str, Any] | None:
        """Find a model version by its SHA256 hash."""
        session = await self._get_session()
        url = f"{_BASE_URL}/model-versions/by-hash/{sha256}"
        try:
            async with session.get(url) as resp:
                if resp.status == 404:
                    return None
                if resp.status == 429:
                    return {"error": "Rate limited"}
                resp.raise_for_status()
                data = await resp.json()

                files = data.get("files", [])
                primary_file = files[0] if files else {}
                model_id = data.get("modelId")

                return {
                    "model_id": model_id,
                    "version_id": data.get("id"),
                    "version_name": data.get("name", ""),
                    "download_url": data.get("downloadUrl", ""),
                    "filename": primary_file.get("name", ""),
                    "size_mb": round(primary_file.get("sizeKB", 0) / 1024, 1),
                    "sha256": sha256,
                    "civitai_url": f"https://civitai.com/models/{model_id}",
                    "match_type": "hash_exact",
                }
        except aiohttp.ClientError:
            return None

    # ── Get model details ─────────────────────────────────────────────

    async def get_model(self, model_id: int) -> dict[str, Any]:
        """Get full model details by ID."""
        session = await self._get_session()
        async with session.get(f"{_BASE_URL}/models/{model_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_version(self, version_id: int) -> dict[str, Any]:
        """Get model version details by ID."""
        session = await self._get_session()
        async with session.get(f"{_BASE_URL}/model-versions/{version_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

    # ── Download ──────────────────────────────────────────────────────

    async def download_model(
        self,
        version_id: int,
        target_dir: str | Path,
        filename: str = "",
        on_progress: Any = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        """Download a model file from CivitAI with integrity verification.

        Args:
            version_id: The model version ID to download.
            target_dir: Directory to save the file to.
            filename: Override filename. If empty, uses the original filename.
            on_progress: Optional callback(downloaded_bytes, total_bytes) for progress tracking.
            retries: Number of retry attempts on failure (default 3).

        Returns:
            Dict with status, path, size info, and integrity check results.
        """
        version = await self.get_version(version_id)
        files = version.get("files", [])
        if not files:
            return {"error": "No files found for this version"}

        primary = files[0]
        download_url = version.get("downloadUrl", "")
        if not download_url:
            return {"error": "No download URL available"}

        expected_sha256 = (primary.get("hashes", {}) or {}).get("SHA256", "")
        expected_size_kb = primary.get("sizeKB", 0)

        fname = filename or primary.get("name", f"model_{version_id}.safetensors")
        target = Path(target_dir) / fname
        target.parent.mkdir(parents=True, exist_ok=True)

        last_error = ""
        for attempt in range(1, retries + 1):
            try:
                result = await self._download_with_verification(
                    download_url, target, fname, version_id,
                    expected_sha256, expected_size_kb, on_progress,
                )
                if "error" not in result:
                    return result
                # Auth errors should not be retried
                if "Authentication" in result["error"]:
                    return result
                # Integrity failure — retry
                last_error = result["error"]
                if attempt < retries:
                    await asyncio.sleep(2 * attempt)  # Backoff
                    continue
                return result
            except aiohttp.ClientError as exc:
                last_error = str(exc)
                if target.exists():
                    target.unlink()
                if attempt < retries:
                    await asyncio.sleep(2 * attempt)
                    continue
            except Exception as exc:
                if target.exists():
                    target.unlink()
                return {"error": str(exc)}

        return {"error": f"Download failed after {retries} attempts: {last_error}"}

    async def _download_with_verification(
        self,
        url: str,
        target: Path,
        fname: str,
        version_id: int,
        expected_sha256: str,
        expected_size_kb: float,
        on_progress: Any,
    ) -> dict[str, Any]:
        """Download a file and verify its integrity."""
        session = await self._get_session()
        async with session.get(url) as resp:
            if resp.status == 401:
                return {"error": "Authentication required. Please set your CivitAI API token."}
            resp.raise_for_status()

            content_length = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            last_report = 0
            sha256 = hashlib.sha256() if expected_sha256 else None

            with open(target, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if sha256:
                        sha256.update(chunk)
                    if on_progress and (downloaded - last_report) >= 5 * 1024 * 1024:
                        on_progress(downloaded, total=content_length)
                        last_report = downloaded

            if on_progress:
                on_progress(downloaded, total=content_length)

            # ── Integrity checks ──────────────────────────────────
            integrity = {"size_match": True, "hash_match": True}

            # Size check: compare to Content-Length header
            if content_length > 0 and downloaded != content_length:
                integrity["size_match"] = False
                if target.exists():
                    target.unlink()
                return {
                    "error": f"Download truncated: got {downloaded} bytes, expected {content_length}",
                    "downloaded_bytes": downloaded,
                    "expected_bytes": content_length,
                }

            # Size check: compare to CivitAI metadata (tolerance: 1%)
            if expected_size_kb > 0:
                expected_bytes = int(expected_size_kb * 1024)
                tolerance = max(expected_bytes * 0.01, 1024)  # 1% or 1KB
                if abs(downloaded - expected_bytes) > tolerance:
                    integrity["size_match"] = False
                    if target.exists():
                        target.unlink()
                    return {
                        "error": f"Size mismatch: got {downloaded} bytes, CivitAI reports {expected_bytes}",
                        "downloaded_bytes": downloaded,
                        "expected_bytes": expected_bytes,
                    }

            # SHA256 check
            if expected_sha256 and sha256:
                actual_hash = sha256.hexdigest().upper()
                expected_upper = expected_sha256.upper()
                if actual_hash != expected_upper:
                    integrity["hash_match"] = False
                    if target.exists():
                        target.unlink()
                    return {
                        "error": f"SHA256 mismatch: expected {expected_upper[:16]}..., got {actual_hash[:16]}...",
                        "expected_sha256": expected_upper,
                        "actual_sha256": actual_hash,
                    }

            return {
                "status": "downloaded",
                "path": str(target),
                "filename": fname,
                "size_mb": round(downloaded / (1024 * 1024), 1),
                "version_id": version_id,
                "integrity": integrity,
            }

    def resolve_target_dir(self, model_type: str) -> Path:
        """Resolve the target directory for a model type."""
        comfyui_type = MODEL_TYPE_MAP.get(model_type, model_type)
        if self.models_root:
            return self.models_root / comfyui_type
        # Fallback: relative to this package
        return Path(__file__).parent.parent.parent.parent / "models" / comfyui_type
