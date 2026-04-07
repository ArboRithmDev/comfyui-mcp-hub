"""Activity log — tracks all MCP agent actions with timestamps."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Any

from aiohttp import web

try:
    from server import PromptServer
    routes = PromptServer.instance.routes
    _prompt_server = PromptServer.instance
except Exception:
    routes = web.RouteTableDef()
    _prompt_server = None

# Max entries kept in memory
_MAX_ENTRIES = 200

# Activity levels
LEVEL_INFO = "info"
LEVEL_SUCCESS = "success"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"
LEVEL_DOWNLOAD = "download"


class ActivityLog:
    """In-memory activity log with optional persistence and push notifications."""

    def __init__(self) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=_MAX_ENTRIES)
        self._downloads: dict[str, dict[str, Any]] = {}  # active downloads by ID
        self._log_path = Path(__file__).parent.parent / "mcp_server" / "activity.jsonl"

    def log(
        self,
        action: str,
        detail: str = "",
        level: str = LEVEL_INFO,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log an activity entry and push notification to the UI."""
        entry = {
            "id": len(self._entries),
            "timestamp": time.time(),
            "time_str": time.strftime("%H:%M:%S"),
            "action": action,
            "detail": detail,
            "level": level,
            "data": data or {},
        }
        self._entries.appendleft(entry)
        self._persist(entry)
        self._notify(entry)
        return entry

    def get_entries(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Get recent log entries."""
        entries = list(self._entries)
        return entries[offset:offset + limit]

    def clear(self) -> None:
        self._entries.clear()

    # ── Downloads tracking ────────────────────────────────────────────

    def start_download(
        self,
        download_id: str,
        filename: str,
        total_bytes: int = 0,
        source: str = "",
    ) -> None:
        """Register a new active download."""
        dl = {
            "id": download_id,
            "filename": filename,
            "source": source,
            "total_bytes": total_bytes,
            "downloaded_bytes": 0,
            "progress": 0.0,
            "status": "downloading",
            "started_at": time.time(),
            "speed_mbps": 0.0,
        }
        self._downloads[download_id] = dl
        self.log("download_start", f"Downloading {filename}", LEVEL_DOWNLOAD, dl)

    def update_download(self, download_id: str, downloaded_bytes: int) -> None:
        """Update download progress."""
        dl = self._downloads.get(download_id)
        if not dl:
            return
        dl["downloaded_bytes"] = downloaded_bytes
        if dl["total_bytes"] > 0:
            dl["progress"] = round(downloaded_bytes / dl["total_bytes"] * 100, 1)
        elapsed = time.time() - dl["started_at"]
        if elapsed > 0:
            dl["speed_mbps"] = round(downloaded_bytes / (1024 * 1024) / elapsed, 2)
        self._notify_download(dl)

    def finish_download(
        self,
        download_id: str,
        success: bool = True,
        error: str = "",
    ) -> None:
        """Mark a download as complete or failed."""
        dl = self._downloads.get(download_id)
        if not dl:
            return
        dl["status"] = "completed" if success else "failed"
        dl["progress"] = 100.0 if success else dl["progress"]
        if error:
            dl["error"] = error
        elapsed = time.time() - dl["started_at"]
        dl["elapsed_seconds"] = round(elapsed, 1)

        level = LEVEL_SUCCESS if success else LEVEL_ERROR
        detail = f"Downloaded {dl['filename']}" if success else f"Failed: {dl['filename']} — {error}"
        self.log("download_complete" if success else "download_failed", detail, level, dl)
        self._downloads.pop(download_id, None)

    def get_active_downloads(self) -> list[dict[str, Any]]:
        """Get all currently active downloads."""
        return list(self._downloads.values())

    # ── Internal ──────────────────────────────────────────────────────

    def _persist(self, entry: dict[str, Any]) -> None:
        """Append entry to the JSONL log file."""
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def _notify(self, entry: dict[str, Any]) -> None:
        """Push activity entry to the frontend via WebSocket."""
        if _prompt_server:
            try:
                _prompt_server.send_sync("mcp-hub:activity", entry)
            except Exception:
                pass

    def _notify_download(self, dl: dict[str, Any]) -> None:
        """Push download progress to the frontend."""
        if _prompt_server:
            try:
                _prompt_server.send_sync("mcp-hub:download-progress", dl)
            except Exception:
                pass


# Singleton
activity = ActivityLog()


# ── REST endpoints ────────────────────────────────────────────────────


@routes.get("/mcp-hub/activity")
async def get_activity(request: web.Request) -> web.Response:
    limit = int(request.query.get("limit", "50"))
    offset = int(request.query.get("offset", "0"))
    return web.json_response(activity.get_entries(limit, offset))


@routes.get("/mcp-hub/activity/downloads")
async def get_downloads(_request: web.Request) -> web.Response:
    return web.json_response(activity.get_active_downloads())


@routes.post("/mcp-hub/activity/clear")
async def clear_activity(_request: web.Request) -> web.Response:
    activity.clear()
    return web.json_response({"status": "cleared"})


@routes.post("/mcp-hub/activity/log")
async def post_activity(request: web.Request) -> web.Response:
    body = await request.json()
    activity.log(
        action=body.get("action", ""),
        detail=body.get("detail", ""),
        level=body.get("level", LEVEL_INFO),
        data=body.get("data"),
    )
    return web.json_response({"status": "logged"})


@routes.post("/mcp-hub/activity/download/start")
async def download_start(request: web.Request) -> web.Response:
    body = await request.json()
    activity.start_download(
        download_id=body.get("download_id", ""),
        filename=body.get("filename", ""),
        total_bytes=body.get("total_bytes", 0),
        source=body.get("source", ""),
    )
    return web.json_response({"status": "started"})


@routes.post("/mcp-hub/activity/download/progress")
async def download_progress(request: web.Request) -> web.Response:
    body = await request.json()
    activity.update_download(
        download_id=body.get("download_id", ""),
        downloaded_bytes=body.get("downloaded_bytes", 0),
    )
    return web.json_response({"status": "updated"})


@routes.post("/mcp-hub/activity/download/finish")
async def download_finish(request: web.Request) -> web.Response:
    body = await request.json()
    activity.finish_download(
        download_id=body.get("download_id", ""),
        success=body.get("success", True),
        error=body.get("error", ""),
    )
    return web.json_response({"status": "finished"})
