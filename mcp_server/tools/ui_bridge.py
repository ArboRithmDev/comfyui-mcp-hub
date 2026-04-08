"""UI Bridge tools — interact with the ComfyUI canvas from AI agents."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config


def _format_validation_error(result: dict[str, Any]) -> dict[str, Any]:
    """Format ComfyUI validation/submission errors into a clear structure."""
    # Direct error message
    if "error" in result and isinstance(result["error"], dict):
        err = result["error"]
        return {
            "status": "error",
            "type": "validation_error",
            "message": err.get("message", str(err)),
            "details": err.get("details", ""),
            "node_errors": _simplify_node_errors(result.get("node_errors", {})),
        }

    # Node-specific errors
    if "node_errors" in result:
        return {
            "status": "error",
            "type": "validation_error",
            "node_errors": _simplify_node_errors(result["node_errors"]),
        }

    # Generic error string
    if "error" in result:
        return {
            "status": "error",
            "type": "error",
            "message": str(result["error"]),
        }

    return {"status": "error", "raw": result}


def _simplify_node_errors(node_errors: dict[str, Any]) -> list[dict[str, Any]]:
    """Simplify ComfyUI's node_errors dict into a flat list."""
    simplified = []
    for node_id, errors in node_errors.items():
        if isinstance(errors, dict):
            class_type = errors.get("class_type", "")
            for err in errors.get("errors", []):
                simplified.append({
                    "node_id": node_id,
                    "node_type": class_type,
                    "message": err.get("message", str(err)),
                    "details": err.get("details", ""),
                })
        elif isinstance(errors, list):
            for err in errors:
                simplified.append({
                    "node_id": node_id,
                    "message": str(err),
                })
    return simplified


def _extract_api_workflow(ui_workflow: dict[str, Any]) -> dict[str, Any] | None:
    """Try to extract API-format workflow from UI-format graph data.

    UI format has {"nodes": [...], "links": [...], ...}
    API format has {"1": {"class_type": ..., "inputs": ...}, ...}
    """
    # If it already looks like API format (keys are node IDs), return as-is
    if "nodes" not in ui_workflow:
        # Check if it looks like API format
        for key in list(ui_workflow.keys())[:5]:
            if isinstance(ui_workflow[key], dict) and "class_type" in ui_workflow[key]:
                return ui_workflow
    return None  # Can't convert — let the caller handle it


async def _ui_command(
    command: str,
    data: dict[str, Any] | None = None,
    timeout: float = 15.0,
    instance: str | None = None,
) -> dict[str, Any]:
    """Send a UI command through the backend bridge."""
    config = load_config()
    client = ComfyUIClient(get_instance_url(config, instance))
    try:
        return await client.post("/mcp-hub/ui/command", data={
            "command": command,
            "data": data or {},
            "timeout": timeout,
        })
    except Exception as exc:
        return {"error": f"UI bridge error: {exc}"}
    finally:
        await client.close()


def register(mcp: FastMCP) -> None:
    """Register UI bridge tools on the MCP server."""

    # ── Canvas state ──────────────────────────────────────────────────

    @mcp.tool()
    async def get_current_workflow(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Get the workflow currently open in the ComfyUI canvas.

        Returns the full graph JSON as displayed in the UI. Requires the ComfyUI browser tab to be open.

        Args:
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("get_current_workflow", instance=instance)

    @mcp.tool()
    async def get_selected_nodes(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Get the nodes currently selected on the ComfyUI canvas.

        Returns a list of selected nodes with their type, position, size, and widget values.

        Args:
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("get_selected_nodes", instance=instance)

    @mcp.tool()
    async def get_node_widgets(
        node_id: int,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Get all widget names and current values for a specific node on the canvas.

        Args:
            node_id: The ID of the node on the canvas.
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("get_node_widgets", {"node_id": node_id}, instance=instance)

    @mcp.tool()
    async def capture_canvas(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Take a screenshot of the ComfyUI canvas as a base64 PNG image.

        This allows multimodal AI agents to visually understand the current workflow layout.

        Args:
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("capture_canvas", timeout=10.0, instance=instance)

    # ── Canvas manipulation ───────────────────────────────────────────

    @mcp.tool()
    async def load_workflow_to_canvas(
        workflow: dict[str, Any],
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Load a workflow JSON into the ComfyUI canvas, replacing the current content.

        Args:
            workflow: The workflow JSON to load.
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("load_workflow_to_canvas", {"workflow": workflow}, instance=instance)

    @mcp.tool()
    async def clear_canvas(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Clear the entire ComfyUI canvas, removing all nodes and connections.

        Args:
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("clear_canvas", instance=instance)

    @mcp.tool()
    async def add_node(
        type: str,
        x: float = 100,
        y: float = 100,
        widgets: dict[str, Any] | None = None,
        title: str = "",
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Add a node to the ComfyUI canvas.

        Args:
            type: The node class type (e.g. "KSampler", "CheckpointLoaderSimple").
            x: X position on the canvas.
            y: Y position on the canvas.
            widgets: Optional dict of widget_name → value to set on the node.
            title: Optional custom title for the node.
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("add_node", {
            "type": type, "x": x, "y": y,
            "widgets": widgets or {}, "title": title,
        }, instance=instance)

    @mcp.tool()
    async def remove_node(
        node_id: int,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Remove a node from the ComfyUI canvas.

        Args:
            node_id: The ID of the node to remove.
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("remove_node", {"node_id": node_id}, instance=instance)

    @mcp.tool()
    async def connect_nodes(
        src_id: int,
        src_slot: int,
        dst_id: int,
        dst_slot: int,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Connect two nodes on the ComfyUI canvas.

        Args:
            src_id: Source node ID.
            src_slot: Output slot index on the source node (0-based).
            dst_id: Destination node ID.
            dst_slot: Input slot index on the destination node (0-based).
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("connect_nodes", {
            "src_id": src_id, "src_slot": src_slot,
            "dst_id": dst_id, "dst_slot": dst_slot,
        }, instance=instance)

    @mcp.tool()
    async def update_node(
        node_id: int,
        widgets: dict[str, Any] | None = None,
        title: str = "",
        color: str = "",
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Update widget values, title, or color of a node on the canvas.

        Args:
            node_id: The ID of the node to update.
            widgets: Dict of widget_name → new_value to set.
            title: New title for the node (empty = keep current).
            color: New color for the node (e.g. "#FF0000", empty = keep current).
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("update_node", {
            "node_id": node_id,
            "widgets": widgets or {},
            "title": title, "color": color,
        }, instance=instance)

    @mcp.tool()
    async def arrange_nodes(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Auto-arrange all nodes on the ComfyUI canvas for a cleaner layout.

        Args:
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("arrange_nodes", instance=instance)

    @mcp.tool()
    async def group_nodes(
        node_ids: list[int],
        title: str = "Group",
        color: str = "#335",
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Create a visual group around specified nodes on the canvas.

        Args:
            node_ids: List of node IDs to group together.
            title: Title for the group.
            color: Color of the group background (hex string).
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("group_nodes", {
            "node_ids": node_ids, "title": title, "color": color,
        }, instance=instance)

    # ── Execution ─────────────────────────────────────────────────────

    @mcp.tool()
    async def execute_current(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Execute the workflow currently displayed on the ComfyUI canvas.

        Returns a job_id that can be used with get_job_status and get_job_result.
        If validation fails, returns the detailed error (node_id, node_type, message).

        Args:
            instance: Target ComfyUI instance name.
        """
        # Step 1: Get the current workflow from the canvas via bridge
        graph_data = await _ui_command("get_current_workflow", instance=instance)
        if "error" in graph_data:
            return graph_data

        workflow = graph_data.get("workflow", {})
        if not workflow:
            return {"error": "Canvas is empty or workflow could not be serialized"}

        # Step 2: Convert UI format to API format if needed, then submit via /prompt
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            import uuid
            client_id = str(uuid.uuid4())

            # The graph from app.graph.serialize() is in UI format.
            # ComfyUI's /prompt expects API format. We submit via the
            # special /api/prompt endpoint which handles both.
            # But first try the output from the canvas as-is.
            try:
                result = await client.post("/prompt", data={
                    "prompt": workflow,
                    "client_id": client_id,
                })
            except Exception as exc:
                # Try extracting API-format workflow from the UI-format
                api_workflow = _extract_api_workflow(workflow)
                if api_workflow:
                    result = await client.post("/prompt", data={
                        "prompt": api_workflow,
                        "client_id": client_id,
                    })
                else:
                    return {"error": f"Failed to submit workflow: {exc}"}

            # Check for validation errors
            if isinstance(result, dict):
                if "error" in result:
                    return _format_validation_error(result)
                if "node_errors" in result and result["node_errors"]:
                    return _format_validation_error(result)
                prompt_id = result.get("prompt_id", "")
                if prompt_id:
                    return {"job_id": prompt_id, "status": "queued"}

            return {"status": "queued", "details": result}
        finally:
            await client.close()

    @mcp.tool()
    async def get_execution_preview(
        node_id: int,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Get the preview image from a node after execution.

        If the node has rendered a preview (e.g. after image generation), returns it as base64 PNG.

        Args:
            node_id: The ID of the node to get the preview from.
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("get_execution_preview", {"node_id": node_id}, timeout=10.0, instance=instance)

    # ── Feedback ──────────────────────────────────────────────────────

    @mcp.tool()
    async def notify_ui(
        message: str,
        type: str = "info",
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Display a toast notification in the ComfyUI interface.

        Args:
            message: The message to display.
            type: Notification type: "info", "warning", or "error".
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            return await client.post("/mcp-hub/ui/notify", data={
                "message": message, "type": type,
            })
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            await client.close()

    @mcp.tool()
    async def refresh_ui(
        mode: str = "soft",
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Refresh the ComfyUI interface.

        Use after installing packages, downloading models, or changing settings
        so the UI picks up the changes without a manual browser reload.

        Args:
            mode: "soft" redraws the canvas and refreshes model/node dropdowns.
                  "hard" triggers a full browser page reload.
            instance: Target ComfyUI instance name.
        """
        return await _ui_command("refresh_ui", {"mode": mode}, instance=instance)

    # ── Debugging ─────────────────────────────────────────────────────

    @mcp.tool()
    async def get_last_error(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Get the last validation or execution error from ComfyUI.

        Checks both the prompt submission endpoint and execution history
        for recent errors. Essential for debugging failed workflows.

        Args:
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            errors = []

            # Check execution history for recent errors
            try:
                history = await client.get("/history?max_items=5")
                if isinstance(history, dict):
                    for prompt_id, entry in history.items():
                        status_info = entry.get("status", {})
                        if status_info.get("status_str") == "error":
                            messages = status_info.get("messages", [])
                            node_errors = entry.get("node_errors", {})
                            errors.append({
                                "type": "execution_error",
                                "prompt_id": prompt_id,
                                "messages": messages,
                                "node_errors": _simplify_node_errors(node_errors),
                            })
            except Exception:
                pass

            # Check queue for items with errors
            try:
                queue = await client.get("/queue")
                for item in queue.get("queue_running", []):
                    if isinstance(item, list) and len(item) > 3:
                        prompt_data = item[2] if len(item) > 2 else {}
                        extra = item[3] if len(item) > 3 else {}
                        if isinstance(extra, dict) and extra.get("error"):
                            errors.append({
                                "type": "queue_error",
                                "error": extra["error"],
                            })
            except Exception:
                pass

            if not errors:
                return {"status": "no_errors", "message": "No recent errors found."}

            return {"errors": errors, "count": len(errors)}
        finally:
            await client.close()

    @mcp.tool()
    async def get_logs(
        lines: int = 50,
        level: str = "",
        instance: str | None = None,
    ) -> list[dict[str, str]]:
        """Get recent ComfyUI server log entries (stdout + stderr, including tracebacks).

        Parses the ComfyUI log file and groups multi-line entries like Python
        tracebacks into single entries so stack traces are never split.

        Args:
            lines: Number of recent entries to return (default 50, max 200).
            level: Filter by level: "error", "warning", "info", or "" for all.
            instance: Target ComfyUI instance name.
        """
        from pathlib import Path
        import re

        lines = min(lines, 200)

        # Find the most recent log file
        log_dir = Path(__file__).parent.parent.parent.parent.parent / "user"
        log_files = sorted(log_dir.glob("comfyui_*.log"), key=lambda f: f.stat().st_mtime, reverse=True)

        if not log_files:
            return [{"level": "error", "message": f"No log files found in {log_dir}"}]

        log_file = log_files[0]
        try:
            all_lines = log_file.read_text(errors="replace").splitlines()
        except Exception as exc:
            return [{"level": "error", "message": f"Cannot read log: {exc}"}]

        # ── Phase 1: Group lines into logical entries ─────────────
        # A new entry starts with [timestamp] or a non-indented line that
        # doesn't look like a continuation (traceback lines, File "...", etc.)
        log_pattern = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]\s*(.*)')
        traceback_start = re.compile(r'^Traceback \(most recent call last\)')
        continuation = re.compile(r'^(\s+File\s"|  |\s+raise\s|\s+return\s|\s+at\s|\s+\.\.\.|\s+\^)')

        raw_entries: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        for line in all_lines:
            ts_match = log_pattern.match(line)

            if ts_match:
                # New timestamped entry
                if current:
                    raw_entries.append(current)
                current = {"timestamp": ts_match.group(1), "lines": [ts_match.group(2)]}

            elif traceback_start.match(line):
                # Start of a traceback block — always error, may follow a timestamped line
                if current:
                    raw_entries.append(current)
                current = {"timestamp": "", "lines": [line]}

            elif continuation.match(line) and current:
                # Continuation of previous entry (indented traceback lines, etc.)
                current["lines"].append(line)

            elif line.strip() == "":
                continue  # Skip blank lines

            else:
                # Non-indented line without timestamp — could be an error message
                # following a traceback, or a standalone log line
                if current and (
                    any("Traceback" in l for l in current["lines"])
                    or any("File " in l for l in current["lines"][-3:])
                ):
                    # Append to current traceback (the final error message)
                    current["lines"].append(line)
                else:
                    if current:
                        raw_entries.append(current)
                    current = {"timestamp": "", "lines": [line]}

        if current:
            raw_entries.append(current)

        # ── Phase 2: Classify and filter ──────────────────────────
        entries = []
        for entry in raw_entries[-lines * 3:]:
            message = "\n".join(entry["lines"])
            msg_lower = message.lower()

            # Detect level
            is_error = (
                "traceback" in msg_lower
                or "error" in msg_lower
                or "exception" in msg_lower
                or "cannot import" in msg_lower
                or "modulenotfounderror" in msg_lower
                or "failed" in msg_lower
            )
            is_warning = "warning" in msg_lower or "warn" in msg_lower or "deprecat" in msg_lower

            if is_error:
                entry_level = "error"
            elif is_warning:
                entry_level = "warning"
            else:
                entry_level = "info"

            if level and entry_level != level:
                continue

            entries.append({
                "level": entry_level,
                "timestamp": entry["timestamp"],
                "message": message[:2000],  # Allow longer messages for tracebacks
            })

        return entries[-lines:]
