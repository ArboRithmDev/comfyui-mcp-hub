"""Combo tools — batch operations that reduce the number of MCP round-trips.

Optimized for clients with interaction limits (Gemini, etc.) by combining
multiple actions into single tool calls.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config


async def _ui_command(command: str, data: dict = None, timeout: float = 15.0, instance: str = None) -> dict:
    config = load_config()
    client = ComfyUIClient(get_instance_url(config, instance))
    try:
        return await client.post("/mcp-hub/ui/command", data={"command": command, "data": data or {}, "timeout": timeout})
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        await client.close()


def register(mcp: FastMCP) -> None:
    """Register combo/batch tools."""

    # ── Overview: single call to understand the full ComfyUI state ────

    @mcp.tool()
    async def get_overview(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Get a complete overview of the ComfyUI instance in a single call.

        Returns system stats, queue status, installed custom nodes count,
        available model counts by type, and the current canvas summary.
        Saves multiple round-trips compared to calling each tool separately.

        Args:
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            overview: dict[str, Any] = {}

            # System stats + queue
            try:
                stats = await client.get_system_stats()
                queue = await client.get_queue()
                overview["system"] = {
                    "gpu": stats.get("devices", [{}])[0].get("name", "unknown"),
                    "vram_total_mb": round(stats.get("devices", [{}])[0].get("vram_total", 0) / 1048576),
                    "vram_free_mb": round(stats.get("devices", [{}])[0].get("vram_free", 0) / 1048576),
                    "queue_running": len(queue.get("queue_running", [])),
                    "queue_pending": len(queue.get("queue_pending", [])),
                }
            except Exception:
                overview["system"] = {"error": "unavailable"}

            # Model counts by type
            try:
                from pathlib import Path
                from ..tools.introspection import _MODEL_EXTS
                models_root = Path(__file__).parent.parent.parent.parent.parent / "models"
                model_counts = {}
                if models_root.exists():
                    for d in sorted(models_root.iterdir()):
                        if d.is_dir():
                            count = sum(1 for f in d.rglob("*") if f.is_file() and f.suffix.lower() in _MODEL_EXTS)
                            if count > 0:
                                model_counts[d.name] = count
                overview["models"] = model_counts
            except Exception:
                overview["models"] = {}

            # Installed custom nodes count
            try:
                installed = await client.manager_get_installed()
                nodes = installed.get("custom_nodes", []) if isinstance(installed, dict) else []
                overview["custom_nodes"] = {
                    "installed": len(nodes),
                    "enabled": sum(1 for n in nodes if n.get("enabled", True)),
                }
            except Exception:
                overview["custom_nodes"] = {"error": "Manager not available"}

            # Canvas summary (if browser open)
            try:
                canvas = await _ui_command("get_current_workflow", instance=instance)
                wf = canvas.get("workflow", {})
                if isinstance(wf, dict):
                    node_list = wf.get("nodes", [])
                    if isinstance(node_list, list):
                        overview["canvas"] = {
                            "nodes": len(node_list),
                            "node_types": list(set(n.get("type", "") for n in node_list))[:15],
                        }
                    else:
                        # API format
                        overview["canvas"] = {
                            "nodes": len(wf),
                            "node_types": list(set(v.get("class_type", "") for v in wf.values() if isinstance(v, dict)))[:15],
                        }
                else:
                    overview["canvas"] = {"nodes": 0}
            except Exception:
                overview["canvas"] = {"status": "browser tab not open"}

            return overview
        finally:
            await client.close()

    # ── Build workflow: create a complete workflow in one call ────────

    @mcp.tool()
    async def build_workflow(
        nodes: list[dict[str, Any]],
        connections: list[dict[str, Any]] | None = None,
        layout: bool = True,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Build an entire workflow on the canvas in a single call.

        Creates multiple nodes, connects them, and optionally applies smart layout.
        Much more efficient than calling add_node + connect_nodes repeatedly.

        Args:
            nodes: List of nodes to create. Each dict has:
                - type (str): node class type (e.g. "KSampler")
                - id (str, optional): reference ID for connections (e.g. "loader1")
                - widgets (dict, optional): widget values to set
                - title (str, optional): custom title
            connections: List of connections. Each dict has:
                - from_node (str): source node reference ID
                - from_slot (int): output slot index
                - to_node (str): target node reference ID
                - to_slot (int): input slot index
            layout: Apply smart_layout after building (default True).
            instance: Target ComfyUI instance name.
        """
        # Clear canvas first
        await _ui_command("clear_canvas", instance=instance)

        # Create nodes and track ref_id → real node_id
        ref_to_id: dict[str, int] = {}
        created = []

        for i, node_spec in enumerate(nodes):
            ref_id = str(node_spec.get("id", f"node_{i}"))
            result = await _ui_command("add_node", {
                "type": node_spec["type"],
                "x": 100 + (i % 5) * 250,
                "y": 100 + (i // 5) * 200,
                "widgets": node_spec.get("widgets", {}),
                "title": node_spec.get("title", ""),
            }, instance=instance)

            if "error" in result:
                created.append({"ref": ref_id, "error": result["error"]})
            else:
                real_id = result.get("node_id")
                ref_to_id[ref_id] = real_id
                created.append({"ref": ref_id, "node_id": real_id, "type": node_spec["type"]})

        # Create connections
        connected = []
        for conn in (connections or []):
            src_id = ref_to_id.get(str(conn["from_node"]))
            dst_id = ref_to_id.get(str(conn["to_node"]))
            if src_id is None or dst_id is None:
                connected.append({"error": f"Node ref not found", "connection": conn})
                continue
            result = await _ui_command("connect_nodes", {
                "src_id": src_id, "src_slot": conn["from_slot"],
                "dst_id": dst_id, "dst_slot": conn["to_slot"],
            }, instance=instance)
            connected.append(result)

        # Apply layout
        layout_result = None
        if layout:
            layout_result = await _ui_command("smart_layout", {}, instance=instance)

        return {
            "status": "built",
            "nodes_created": len([c for c in created if "error" not in c]),
            "connections_made": len([c for c in connected if "error" not in c]),
            "nodes": created,
            "layout": layout_result,
        }

    # ── Batch update: modify multiple nodes at once ──────────────────

    @mcp.tool()
    async def batch_update_nodes(
        updates: list[dict[str, Any]],
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Update multiple nodes in a single call.

        Args:
            updates: List of updates. Each dict has:
                - node_id (int): node to update
                - widgets (dict, optional): widget values to set
                - title (str, optional): new title
                - color (str, optional): new color
                - collapsed (bool, optional): collapse/expand
                - pos (list, optional): [x, y] new position
            instance: Target ComfyUI instance name.
        """
        results = []
        for upd in updates:
            node_id = upd.get("node_id")
            if node_id is None:
                results.append({"error": "node_id required"})
                continue

            # Position
            if "pos" in upd:
                await _ui_command("move_node", {
                    "node_id": node_id, "x": upd["pos"][0], "y": upd["pos"][1],
                }, instance=instance)

            # Collapse
            if "collapsed" in upd:
                await _ui_command("collapse_node", {
                    "node_id": node_id, "collapsed": upd["collapsed"],
                }, instance=instance)

            # Widgets, title, color
            result = await _ui_command("update_node", {
                "node_id": node_id,
                "widgets": upd.get("widgets", {}),
                "title": upd.get("title", ""),
                "color": upd.get("color", ""),
            }, instance=instance)
            results.append(result)

        return {"status": "updated", "count": len(results), "results": results}

    # ── Setup workflow: end-to-end from template or scratch ──────────

    @mcp.tool()
    async def setup_and_execute(
        template_name: str = "",
        workflow: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        auto_resolve: bool = True,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Load a template (or raw workflow), resolve missing elements, and execute.

        Combines apply_template + resolve_workflow + load_to_canvas + execute in one call.

        Args:
            template_name: Name of a saved template. If empty, uses the workflow parameter.
            workflow: Raw workflow JSON (used if template_name is empty).
            inputs: Variable overrides for the template.
            auto_resolve: Run the resolver to fix missing nodes/models before executing.
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        result_log: dict[str, Any] = {"steps": []}

        # Step 1: Get workflow
        if template_name:
            from .workflow_ops import _templates_dir, _inputs_dir
            import json as _json
            template_path = _templates_dir() / f"{template_name}.json"
            inputs_path = _inputs_dir() / f"{template_name}.json"

            if not template_path.exists():
                return {"error": f"Template '{template_name}' not found"}

            template_str = template_path.read_text()
            saved_inputs = {}
            if inputs_path.exists():
                saved_inputs = _json.loads(inputs_path.read_text())
            if inputs:
                saved_inputs.update(inputs)

            for var_name, value in saved_inputs.items():
                placeholder = "{{" + var_name + "}}"
                template_str = template_str.replace(f'"{placeholder}"', _json.dumps(value))

            workflow = _json.loads(template_str)
            result_log["steps"].append({"step": "template_loaded", "name": template_name})
        elif not workflow:
            return {"error": "Provide template_name or workflow"}

        # Step 2: Resolve missing elements
        if auto_resolve:
            from .resolver import _make_civitai, _make_hf
            client = ComfyUIClient(get_instance_url(config, instance))
            civitai = _make_civitai(config)
            hf = _make_hf(config)
            try:
                from ..workflow_analyzer import analyze_workflow
                analysis = analyze_workflow(workflow)
                available = await client.get_object_info()
                missing_nodes = [t for t in analysis["node_types"] if t not in available]
                if missing_nodes:
                    result_log["steps"].append({"step": "missing_nodes", "nodes": missing_nodes})
            except Exception as exc:
                result_log["steps"].append({"step": "resolve_skipped", "reason": str(exc)})
            finally:
                await client.close()
                await civitai.close()
                await hf.close()

        # Step 3: Load to canvas
        load_result = await _ui_command("load_workflow_to_canvas", {"workflow": workflow}, instance=instance)
        result_log["steps"].append({"step": "loaded_to_canvas", "result": load_result})

        # Step 4: Execute
        exec_result = await _ui_command("execute_current", instance=instance, timeout=20.0)
        result_log["steps"].append({"step": "executed", "result": exec_result})

        result_log["status"] = "done" if "error" not in exec_result else "error"
        result_log["job_id"] = exec_result.get("job_id", "")
        return result_log
