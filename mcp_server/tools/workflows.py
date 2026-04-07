"""Workflow tools — create, execute, and monitor ComfyUI workflows."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config

# Simple in-memory job tracker
_jobs: dict[str, dict[str, Any]] = {}


def _workflows_dir() -> Path:
    """Get the workflows directory."""
    d = Path(__file__).parent.parent.parent.parent.parent / "user" / "default" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    return d


def register(mcp: FastMCP) -> None:
    """Register workflow tools on the MCP server."""

    @mcp.tool()
    async def list_workflows() -> list[dict[str, str]]:
        """List all saved workflows in the ComfyUI workflows directory."""
        wf_dir = _workflows_dir()
        workflows = []
        for f in sorted(wf_dir.glob("*.json")):
            workflows.append({"name": f.stem, "path": str(f)})
        return workflows

    @mcp.tool()
    async def get_workflow(name: str) -> dict[str, Any]:
        """Get the JSON content of a saved workflow.

        Args:
            name: Workflow file name (without .json extension).
        """
        path = _workflows_dir() / f"{name}.json"
        if not path.exists():
            return {"error": f"Workflow '{name}' not found"}
        return json.loads(path.read_text())

    @mcp.tool()
    async def save_workflow(name: str, workflow: dict[str, Any]) -> dict[str, str]:
        """Save a workflow JSON to disk.

        Args:
            name: Name for the workflow file (without .json extension).
            workflow: The workflow JSON object (ComfyUI API format).
        """
        path = _workflows_dir() / f"{name}.json"
        path.write_text(json.dumps(workflow, indent=2))
        return {"status": "saved", "path": str(path)}

    @mcp.tool()
    async def execute_workflow(
        workflow: dict[str, Any],
        instance: str | None = None,
    ) -> dict[str, str]:
        """Execute a workflow on ComfyUI and return a job ID for tracking.

        Args:
            workflow: The workflow in ComfyUI API format (node graph JSON).
            instance: Target ComfyUI instance name. Uses default if omitted.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            client_id = str(uuid.uuid4())
            result = await client.queue_prompt(workflow, client_id=client_id)
            prompt_id = result.get("prompt_id", "")
            _jobs[prompt_id] = {
                "prompt_id": prompt_id,
                "client_id": client_id,
                "status": "queued",
                "instance": instance,
            }
            return {"job_id": prompt_id, "status": "queued"}
        finally:
            await client.close()

    @mcp.tool()
    async def get_job_status(job_id: str) -> dict[str, Any]:
        """Check the status of an executing workflow job.

        Args:
            job_id: The job/prompt ID returned by execute_workflow.
        """
        job = _jobs.get(job_id)
        if not job:
            return {"error": f"Job '{job_id}' not found"}

        config = load_config()
        client = ComfyUIClient(get_instance_url(config, job.get("instance")))
        try:
            history = await client.get_history(job_id)
            if job_id in history:
                entry = history[job_id]
                status = entry.get("status", {})
                if status.get("completed", False):
                    job["status"] = "completed"
                elif status.get("status_str") == "error":
                    job["status"] = "error"
                    job["error"] = status.get("messages", [])
                else:
                    job["status"] = "running"
            return job
        finally:
            await client.close()

    @mcp.tool()
    async def get_job_result(job_id: str) -> dict[str, Any]:
        """Get the output results of a completed job (images, videos, audio).

        Args:
            job_id: The job/prompt ID returned by execute_workflow.
        """
        config = load_config()
        job = _jobs.get(job_id, {})
        client = ComfyUIClient(get_instance_url(config, job.get("instance")))
        try:
            history = await client.get_history(job_id)
            if job_id not in history:
                return {"error": f"No results for job '{job_id}'"}

            outputs = history[job_id].get("outputs", {})
            results = {}
            for node_id, node_output in outputs.items():
                for key, items in node_output.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and "filename" in item:
                                file_info = {
                                    "filename": item["filename"],
                                    "subfolder": item.get("subfolder", ""),
                                    "type": item.get("type", "output"),
                                }
                                results.setdefault(key, []).append(file_info)
            return {"job_id": job_id, "outputs": results}
        finally:
            await client.close()

    @mcp.tool()
    async def cancel_job(
        job_id: str,
        instance: str | None = None,
    ) -> dict[str, str]:
        """Cancel a running or queued job.

        Args:
            job_id: The job/prompt ID to cancel.
            instance: Target ComfyUI instance name. Uses default if omitted.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            await client.delete_queue_item([job_id])
            if job_id in _jobs:
                _jobs[job_id]["status"] = "cancelled"
            return {"job_id": job_id, "status": "cancelled"}
        finally:
            await client.close()
