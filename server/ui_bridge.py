"""Backend bridge: dispatch commands to the frontend via WebSocket and wait for responses."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from aiohttp import web

try:
    from server import PromptServer
    routes = PromptServer.instance.routes
    _prompt_server = PromptServer.instance
except Exception:
    routes = web.RouteTableDef()
    _prompt_server = None

# Pending command futures: command_id → Future
_pending: dict[str, asyncio.Future] = {}

# Default timeout for waiting on frontend response (seconds)
_COMMAND_TIMEOUT = 15.0
_CAPTURE_TIMEOUT = 10.0


def _send_to_frontend(command: str, data: dict[str, Any], command_id: str) -> None:
    """Push a command to the frontend via WebSocket."""
    if _prompt_server is None:
        raise RuntimeError("PromptServer not available")
    _prompt_server.send_sync("mcp-hub:command", {
        "command_id": command_id,
        "command": command,
        "data": data,
    })


async def dispatch_command(
    command: str,
    data: dict[str, Any] | None = None,
    timeout: float = _COMMAND_TIMEOUT,
) -> dict[str, Any]:
    """Send a command to the frontend and wait for the response.

    Args:
        command: Command name (e.g. "get_current_workflow").
        data: Command payload.
        timeout: Max seconds to wait for frontend response.

    Returns:
        The response data from the frontend.
    """
    command_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()
    _pending[command_id] = future

    try:
        _send_to_frontend(command, data or {}, command_id)
        result = await asyncio.wait_for(future, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        return {"error": f"Frontend did not respond within {timeout}s. Is the ComfyUI browser tab open?"}
    finally:
        _pending.pop(command_id, None)


# ── REST endpoint: frontend posts responses here ─────────────────────


@routes.post("/mcp-hub/ui/response")
async def ui_response(request: web.Request) -> web.Response:
    """Receive a response from the frontend for a pending command."""
    body = await request.json()
    command_id = body.get("command_id", "")
    result = body.get("result", {})

    future = _pending.get(command_id)
    if future and not future.done():
        future.set_result(result)
        return web.json_response({"status": "ok"})
    return web.json_response({"status": "no_pending_command"}, status=404)


# ── REST endpoints: MCP server calls these ────────────────────────────


@routes.post("/mcp-hub/ui/command")
async def ui_command(request: web.Request) -> web.Response:
    """Generic command dispatch endpoint. Used by MCP tools."""
    body = await request.json()
    command = body.get("command", "")
    data = body.get("data", {})
    timeout = body.get("timeout", _COMMAND_TIMEOUT)

    if not command:
        return web.json_response({"error": "command is required"}, status=400)

    result = await dispatch_command(command, data, timeout)
    return web.json_response(result)


@routes.post("/mcp-hub/ui/notify")
async def ui_notify(request: web.Request) -> web.Response:
    """Send a toast notification to the frontend (fire-and-forget)."""
    body = await request.json()
    message = body.get("message", "")
    level = body.get("type", "info")

    if _prompt_server is None:
        return web.json_response({"error": "PromptServer not available"}, status=500)

    _prompt_server.send_sync("mcp-hub:notify", {
        "message": message,
        "type": level,
    })
    return web.json_response({"status": "sent"})
