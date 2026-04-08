"""Lightweight async client for HuggingFace Hub API — model search fallback."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiohttp

_BASE_URL = "https://huggingface.co/api"


class HuggingFaceClient:
    """Search and download models from HuggingFace Hub."""

    def __init__(self, token: str = "") -> None:
        self.token = token
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers: dict[str, str] = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            timeout = aiohttp.ClientTimeout(
                total=None,
                connect=30,
                sock_read=120,
            )
            self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def search_models(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search HuggingFace Hub for models.

        Args:
            query: Search text (model name or keyword).
            limit: Max results.
        """
        session = await self._get_session()
        params = {
            "search": query,
            "limit": limit,
            "sort": "downloads",
            "direction": "-1",
        }

        try:
            async with session.get(f"{_BASE_URL}/models", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []

        results = []
        for item in data:
            model_id = item.get("modelId", item.get("id", ""))
            results.append({
                "id": model_id,
                "name": model_id.split("/")[-1] if "/" in str(model_id) else str(model_id),
                "author": model_id.split("/")[0] if "/" in str(model_id) else "",
                "downloads": item.get("downloads", 0),
                "tags": item.get("tags", [])[:5],
                "pipeline_tag": item.get("pipeline_tag", ""),
                "url": f"https://huggingface.co/{model_id}",
                "source": "huggingface",
                "match_type": "name_search",
            })
        return results

    async def find_model_files(
        self,
        repo_id: str,
        extensions: tuple[str, ...] = (".safetensors", ".ckpt", ".pt", ".bin"),
    ) -> list[dict[str, Any]]:
        """List downloadable model files in a HuggingFace repo.

        Args:
            repo_id: Full repo ID (e.g. "stabilityai/stable-diffusion-xl-base-1.0").
            extensions: File extensions to include.
        """
        session = await self._get_session()
        try:
            async with session.get(f"{_BASE_URL}/models/{repo_id}") as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []

        files = []
        for sibling in data.get("siblings", []):
            fname = sibling.get("rfilename", "")
            if any(fname.endswith(ext) for ext in extensions):
                files.append({
                    "filename": fname,
                    "download_url": f"https://huggingface.co/{repo_id}/resolve/main/{fname}",
                    "repo_id": repo_id,
                })
        return files

    async def download_file(
        self,
        url: str,
        target_dir: str | Path,
        filename: str = "",
        retries: int = 3,
    ) -> dict[str, Any]:
        """Download a file from HuggingFace with integrity verification.

        Args:
            url: Direct download URL.
            target_dir: Directory to save to.
            filename: Override filename.
            retries: Number of retry attempts on failure (default 3).
        """
        if not filename:
            filename = url.split("/")[-1].split("?")[0]

        target = Path(target_dir) / filename
        target.parent.mkdir(parents=True, exist_ok=True)

        last_error = ""
        for attempt in range(1, retries + 1):
            try:
                session = await self._get_session()
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    content_length = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    with open(target, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            f.write(chunk)
                            downloaded += len(chunk)

                    # Size verification
                    if content_length > 0 and downloaded != content_length:
                        if target.exists():
                            target.unlink()
                        last_error = f"Download truncated: got {downloaded} bytes, expected {content_length}"
                        if attempt < retries:
                            await asyncio.sleep(2 * attempt)
                            continue
                        return {"error": last_error}

                    return {
                        "status": "downloaded",
                        "path": str(target),
                        "filename": filename,
                        "size_mb": round(downloaded / (1024 * 1024), 1),
                        "source": "huggingface",
                        "integrity": {"size_match": True},
                    }
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
