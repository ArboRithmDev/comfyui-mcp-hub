"""REST endpoints for controlling the MCP server from ComfyUI's web UI."""

from __future__ import annotations

import asyncio
import json

from aiohttp import web

from .cli_detector import configure_all, configure_cli, detect_clis, unconfigure_cli
from .instance_registry import registry
from .process_manager import manager
from . import updater

try:
    from server import PromptServer

    routes = PromptServer.instance.routes
except Exception:
    # Fallback for testing outside ComfyUI
    routes = web.RouteTableDef()


# ── MCP Server lifecycle ──────────────────────────────────────────────


@routes.post("/mcp-hub/server/start")
async def start_server(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = None
    result = manager.start(config=body)
    return web.json_response(result)


@routes.post("/mcp-hub/server/stop")
async def stop_server(_request: web.Request) -> web.Response:
    result = manager.stop()
    return web.json_response(result)


@routes.get("/mcp-hub/server/status")
async def server_status(_request: web.Request) -> web.Response:
    return web.json_response(manager.get_status())


# ── Configuration ─────────────────────────────────────────────────────


@routes.get("/mcp-hub/config")
async def get_config(_request: web.Request) -> web.Response:
    return web.json_response(manager.get_config())


@routes.post("/mcp-hub/config")
async def save_config(request: web.Request) -> web.Response:
    config = await request.json()
    manager.save_config(config)
    return web.json_response({"status": "saved"})


# ── Instance management ──────────────────────────────────────────────


@routes.get("/mcp-hub/instances")
async def list_instances(_request: web.Request) -> web.Response:
    return web.json_response(registry.list())


@routes.post("/mcp-hub/instances")
async def add_instance(request: web.Request) -> web.Response:
    body = await request.json()
    name = body.get("name", "")
    host = body.get("host", "")
    port = int(body.get("port", 8188))
    if not name or not host:
        return web.json_response({"error": "name and host are required"}, status=400)
    result = registry.add(name, host, port)
    if "error" in result:
        return web.json_response(result, status=409)
    # Persist to config
    config = manager.get_config()
    config["instances"] = registry.list()
    manager.save_config(config)
    return web.json_response(result)


@routes.delete("/mcp-hub/instances/{name}")
async def remove_instance(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    result = registry.remove(name)
    if "error" in result:
        return web.json_response(result, status=400)
    config = manager.get_config()
    config["instances"] = registry.list()
    manager.save_config(config)
    return web.json_response(result)


@routes.post("/mcp-hub/instances/{name}/default")
async def set_default(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    result = registry.set_default(name)
    if "error" in result:
        return web.json_response(result, status=404)
    config = manager.get_config()
    config["instances"] = registry.list()
    manager.save_config(config)
    return web.json_response(result)


@routes.get("/mcp-hub/instances/health")
async def health_check(request: web.Request) -> web.Response:
    name = request.query.get("name")
    results = await registry.health_check(name)
    return web.json_response(results)


# ── AI CLI detection & configuration ─────────────────────────────────


@routes.get("/mcp-hub/clis")
async def list_clis(_request: web.Request) -> web.Response:
    return web.json_response(detect_clis())


@routes.post("/mcp-hub/clis/{name}/configure")
async def configure_cli_route(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    result = configure_cli(name)
    if "error" in result:
        return web.json_response(result, status=400)
    return web.json_response(result)


@routes.post("/mcp-hub/clis/{name}/unconfigure")
async def unconfigure_cli_route(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    result = unconfigure_cli(name)
    if "error" in result:
        return web.json_response(result, status=400)
    return web.json_response(result)


@routes.post("/mcp-hub/clis/configure-all")
async def configure_all_route(_request: web.Request) -> web.Response:
    results = configure_all()
    return web.json_response(results)


# ── Version management ───────────────────────────────────────────────


@routes.get("/mcp-hub/version")
async def get_version(_request: web.Request) -> web.Response:
    return web.json_response({
        "version": updater.get_current_version(),
        "tag": updater.get_current_tag(),
    })


@routes.get("/mcp-hub/version/check")
async def check_update(_request: web.Request) -> web.Response:
    result = await asyncio.get_event_loop().run_in_executor(None, updater.check_for_update)
    return web.json_response(result)


@routes.get("/mcp-hub/version/list")
async def list_versions(_request: web.Request) -> web.Response:
    result = await asyncio.get_event_loop().run_in_executor(None, updater.list_versions)
    return web.json_response(result)


@routes.post("/mcp-hub/version/switch")
async def switch_version(request: web.Request) -> web.Response:
    body = await request.json()
    tag = body.get("tag", "")
    if not tag:
        return web.json_response({"error": "tag is required"}, status=400)
    result = await asyncio.get_event_loop().run_in_executor(None, updater.switch_version, tag)
    return web.json_response(result)
