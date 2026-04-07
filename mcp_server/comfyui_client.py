"""HTTP/WebSocket client for communicating with ComfyUI instances."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import aiohttp


class ComfyUIClient:
    """Async client wrapping ComfyUI's REST and WebSocket API."""

    # Class-level cache: base_url → detected manager version (1 or 2)
    _mgr_version_cache: dict[str, int] = {}

    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Generic HTTP ──────────────────────────────────────────────────

    async def get(self, path: str, **kwargs: Any) -> Any:
        session = await self._get_session()
        async with session.get(f"{self.base_url}{path}", **kwargs) as resp:
            resp.raise_for_status()
            body = await resp.read()
            if not body:
                return {"status": resp.status}
            try:
                return await resp.json(content_type=None)
            except Exception:
                return {"status": resp.status, "text": body.decode(errors="replace")}

    async def post(self, path: str, data: Any = None, **kwargs: Any) -> Any:
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}{path}", json=data, **kwargs
        ) as resp:
            resp.raise_for_status()
            body = await resp.read()
            if not body:
                return {"status": resp.status}
            try:
                return await resp.json(content_type=None)
            except Exception:
                return {"status": resp.status, "text": body.decode(errors="replace")}

    async def get_bytes(self, path: str, **kwargs: Any) -> bytes:
        session = await self._get_session()
        async with session.get(f"{self.base_url}{path}", **kwargs) as resp:
            resp.raise_for_status()
            return await resp.read()

    # ── System ────────────────────────────────────────────────────────

    async def get_system_stats(self) -> dict[str, Any]:
        return await self.get("/system_stats")

    async def get_queue(self) -> dict[str, Any]:
        return await self.get("/queue")

    # ── Nodes / Object Info ───────────────────────────────────────────

    async def get_object_info(self, node_class: str | None = None) -> dict[str, Any]:
        if node_class:
            return await self.get(f"/object_info/{node_class}")
        return await self.get("/object_info")

    # ── Prompts / Workflows ───────────────────────────────────────────

    async def queue_prompt(self, prompt: dict[str, Any], client_id: str | None = None) -> dict[str, Any]:
        client_id = client_id or str(uuid.uuid4())
        payload = {"prompt": prompt, "client_id": client_id}
        return await self.post("/prompt", data=payload)

    async def get_history(self, prompt_id: str | None = None) -> dict[str, Any]:
        if prompt_id:
            return await self.get(f"/history/{prompt_id}")
        return await self.get("/history")

    async def delete_queue_item(self, delete_list: list[str]) -> Any:
        return await self.post("/queue", data={"delete": delete_list})

    async def clear_queue(self) -> Any:
        return await self.post("/queue", data={"clear": True})

    # ── Images / Output ───────────────────────────────────────────────

    async def get_image(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        return await self.get_bytes("/view", params=params)

    # ── Models ────────────────────────────────────────────────────────

    async def get_embeddings(self) -> list[str]:
        return await self.get("/embeddings")

    async def get_extensions(self) -> list[str]:
        return await self.get("/extensions")

    # ── Manager endpoints (auto-detect v1 legacy vs v2 Desktop) ─────

    async def detect_manager_version(self) -> int:
        """Detect whether Manager uses v1 (legacy) or v2 (Desktop) routes.

        Result is cached per base_url in a class-level dict so it persists
        across client instances but can be re-detected if ComfyUI restarts.
        """
        cache = ComfyUIClient._mgr_version_cache
        if self.base_url in cache:
            return cache[self.base_url]

        session = await self._get_session()
        # Try v2 first (Desktop)
        try:
            async with session.get(f"{self.base_url}/v2/manager/version") as resp:
                if resp.status == 200:
                    cache[self.base_url] = 2
                    return 2
        except Exception:
            pass
        # Try v1 (legacy)
        try:
            async with session.get(f"{self.base_url}/manager/version") as resp:
                if resp.status == 200:
                    cache[self.base_url] = 1
                    return 1
        except Exception:
            pass
        # Don't cache failures — allow retry on next call
        return 0

    def _mgr_path(self, path: str) -> str:
        """Prefix a Manager path with /v2 if Desktop mode."""
        ver = self._mgr_version_cache.get(self.base_url, 0)
        if ver == 2 and not path.startswith("/v2/"):
            return f"/v2{path}"
        return path

    async def manager_get(self, path: str) -> Any:
        await self.detect_manager_version()
        return await self.get(self._mgr_path(path))

    async def manager_post(self, path: str, data: Any = None) -> Any:
        await self.detect_manager_version()
        return await self.post(self._mgr_path(path), data=data)

    async def manager_install_package(self, package_id: str) -> Any:
        """Install a package via Manager, handling v1/v2 API differences."""
        ver = await self.detect_manager_version()
        if ver == 2:
            # V2 uses /v2/manager/queue/task with structured payload
            task = {
                "ui_id": str(uuid.uuid4()),
                "client_id": "mcp-hub",
                "kind": "install",
                "params": {
                    "id": package_id,
                    "version": "unknown",
                    "selected_version": "latest",
                    "mode": "cache",
                    "channel": "default",
                },
            }
            return await self.post("/v2/manager/queue/task", data=task)
        else:
            return await self.post("/manager/queue/install", data={"id": package_id})

    async def manager_uninstall_package(self, package_id: str) -> Any:
        """Uninstall a package via Manager."""
        ver = await self.detect_manager_version()
        if ver == 2:
            task = {
                "ui_id": str(uuid.uuid4()),
                "client_id": "mcp-hub",
                "kind": "uninstall",
                "params": {
                    "id": package_id,
                    "version": "unknown",
                },
            }
            return await self.post("/v2/manager/queue/task", data=task)
        else:
            return await self.post("/manager/queue/uninstall", data={"id": package_id})

    async def manager_update_package(self, package_id: str) -> Any:
        """Update a package via Manager."""
        ver = await self.detect_manager_version()
        if ver == 2:
            task = {
                "ui_id": str(uuid.uuid4()),
                "client_id": "mcp-hub",
                "kind": "update",
                "params": {
                    "id": package_id,
                    "version": "unknown",
                    "selected_version": "latest",
                    "mode": "cache",
                    "channel": "default",
                },
            }
            return await self.post("/v2/manager/queue/task", data=task)
        else:
            return await self.post("/manager/queue/update", data={"id": package_id})

    async def manager_install_model(self, url: str, model_type: str, filename: str = "") -> Any:
        """Download a model via Manager."""
        ver = await self.detect_manager_version()
        if ver == 2:
            task = {
                "ui_id": str(uuid.uuid4()),
                "client_id": "mcp-hub",
                "kind": "install-model",
                "params": {
                    "url": url,
                    "type": model_type,
                    "filename": filename,
                    "name": filename or url.split("/")[-1],
                },
            }
            return await self.post("/v2/manager/queue/task", data=task)
        else:
            return await self.post("/manager/queue/install_model", data={"url": url, "type": model_type, "filename": filename})

    async def manager_get_installed(self) -> dict[str, Any]:
        """Get installed custom nodes — handles v1/v2 format differences."""
        ver = await self.detect_manager_version()
        if ver == 2:
            data = await self.get("/v2/customnode/installed")
            # V2 returns {cnr_id: {ver, cnr_id, aux_id, enabled}, ...}
            # Normalize to a list format
            if isinstance(data, dict):
                nodes = []
                for key, info in data.items():
                    if isinstance(info, dict):
                        nodes.append({
                            "title": key,
                            "version": info.get("ver", "unknown"),
                            "reference": info.get("aux_id") or info.get("cnr_id", key),
                            "cnr_id": info.get("cnr_id", key),
                            "enabled": info.get("enabled", True),
                        })
                return {"custom_nodes": nodes}
            return data
        else:
            return await self.get("/customnode/installed")

    async def manager_get_mappings(self) -> dict[str, Any]:
        """Get node-to-package mappings."""
        return await self.manager_get("/customnode/getmappings")

    # ── WebSocket for job monitoring ──────────────────────────────────

    async def watch_prompt(
        self, prompt_id: str, client_id: str, timeout: float = 300
    ) -> dict[str, Any]:
        """Connect via WebSocket and wait for a prompt to complete."""
        import websockets

        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws?clientId={client_id}"

        async with websockets.connect(ws_url) as ws:
            start = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start) < timeout:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    data = json.loads(msg)
                    if data.get("type") == "executing":
                        exec_data = data.get("data", {})
                        if exec_data.get("prompt_id") == prompt_id and exec_data.get("node") is None:
                            # Execution complete
                            return await self.get_history(prompt_id)
                except asyncio.TimeoutError:
                    continue
        return {"error": "timeout", "prompt_id": prompt_id}
