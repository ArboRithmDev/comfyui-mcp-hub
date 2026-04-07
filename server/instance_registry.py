"""Registry for managing multiple ComfyUI instances (local + LAN)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class InstanceRegistry:
    """Track and health-check ComfyUI instances."""

    def __init__(self) -> None:
        self._instances: list[dict[str, Any]] = [
            {"name": "local", "host": "127.0.0.1", "port": 8188, "default": True}
        ]

    def load(self, instances: list[dict[str, Any]]) -> None:
        self._instances = instances

    def list(self) -> list[dict[str, Any]]:
        return list(self._instances)

    def add(self, name: str, host: str, port: int) -> dict[str, Any]:
        for inst in self._instances:
            if inst["name"] == name:
                return {"error": f"Instance '{name}' already exists"}
        entry = {"name": name, "host": host, "port": port, "default": False}
        self._instances.append(entry)
        return entry

    def remove(self, name: str) -> dict[str, Any]:
        for i, inst in enumerate(self._instances):
            if inst["name"] == name:
                if inst.get("default"):
                    return {"error": "Cannot remove the default instance"}
                self._instances.pop(i)
                return {"removed": name}
        return {"error": f"Instance '{name}' not found"}

    def set_default(self, name: str) -> dict[str, Any]:
        found = False
        for inst in self._instances:
            if inst["name"] == name:
                found = True
            inst["default"] = inst["name"] == name
        if not found:
            return {"error": f"Instance '{name}' not found"}
        return {"default": name}

    def get_default(self) -> dict[str, Any] | None:
        for inst in self._instances:
            if inst.get("default"):
                return inst
        return self._instances[0] if self._instances else None

    def get(self, name: str) -> dict[str, Any] | None:
        for inst in self._instances:
            if inst["name"] == name:
                return inst
        return None

    def get_url(self, name: str | None = None) -> str:
        inst = self.get(name) if name else self.get_default()
        if not inst:
            return "http://127.0.0.1:8188"
        return f"http://{inst['host']}:{inst['port']}"

    async def health_check(self, name: str | None = None) -> list[dict[str, Any]]:
        targets = [self.get(name)] if name else self._instances
        results = await asyncio.gather(
            *[self._check_one(inst) for inst in targets if inst],
            return_exceptions=True,
        )
        return [r if isinstance(r, dict) else {"error": str(r)} for r in results]

    @staticmethod
    async def _check_one(inst: dict[str, Any]) -> dict[str, Any]:
        url = f"http://{inst['host']}:{inst['port']}/system_stats"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    return {
                        "name": inst["name"],
                        "host": inst["host"],
                        "port": inst["port"],
                        "status": "online",
                        "system_stats": data,
                    }
        except Exception as exc:
            return {
                "name": inst["name"],
                "host": inst["host"],
                "port": inst["port"],
                "status": "offline",
                "error": str(exc),
            }


registry = InstanceRegistry()
