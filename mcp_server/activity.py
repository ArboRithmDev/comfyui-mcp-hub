"""Activity logging client — MCP server side.

Sends activity entries to the ComfyUI backend which stores them
and pushes notifications to the frontend UI.
"""

from __future__ import annotations

import uuid
from typing import Any

from .comfyui_client import ComfyUIClient
from .config import get_instance_url, load_config

# Levels
INFO = "info"
SUCCESS = "success"
WARNING = "warning"
ERROR = "error"
DOWNLOAD = "download"


async def log(
    action: str,
    detail: str = "",
    level: str = INFO,
    data: dict[str, Any] | None = None,
) -> None:
    """Log an activity entry via the ComfyUI backend."""
    config = load_config()
    client = ComfyUIClient(get_instance_url(config))
    try:
        await client.post("/mcp-hub/activity/log", data={
            "action": action,
            "detail": detail,
            "level": level,
            "data": data or {},
        })
    except Exception:
        pass  # Don't fail the tool if logging fails
    finally:
        await client.close()


def make_download_tracker(filename: str, source: str = "civitai") -> tuple[str, Any]:
    """Create a download tracker and return (download_id, progress_callback).

    The callback can be passed to CivitAI/HuggingFace download methods.
    """
    download_id = str(uuid.uuid4())[:8]

    async def _start(total_bytes: int = 0) -> None:
        config = load_config()
        client = ComfyUIClient(get_instance_url(config))
        try:
            await client.post("/mcp-hub/activity/download/start", data={
                "download_id": download_id,
                "filename": filename,
                "source": source,
                "total_bytes": total_bytes,
            })
        except Exception:
            pass
        finally:
            await client.close()

    def _progress_sync(downloaded: int, total: int) -> None:
        """Synchronous progress callback for use inside download loops."""
        # We can't easily await here, so we push via a fire-and-forget approach
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_progress_async(downloaded, total))
            else:
                loop.run_until_complete(_progress_async(downloaded, total))
        except Exception:
            pass

    async def _progress_async(downloaded: int, total: int) -> None:
        config = load_config()
        client = ComfyUIClient(get_instance_url(config))
        try:
            await client.post("/mcp-hub/activity/download/progress", data={
                "download_id": download_id,
                "downloaded_bytes": downloaded,
            })
        except Exception:
            pass
        finally:
            await client.close()

    async def _finish(success: bool = True, error: str = "") -> None:
        config = load_config()
        client = ComfyUIClient(get_instance_url(config))
        try:
            await client.post("/mcp-hub/activity/download/finish", data={
                "download_id": download_id,
                "success": success,
                "error": error,
            })
        except Exception:
            pass
        finally:
            await client.close()

    class Tracker:
        id = download_id
        start = staticmethod(_start)
        progress = staticmethod(_progress_sync)
        finish = staticmethod(_finish)

    return download_id, Tracker
