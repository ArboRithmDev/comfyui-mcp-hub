"""Workflow repair tools — detect and fix missing/obsolete nodes."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .. import activity as act
from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config
from ..workflow_repair import find_missing_nodes, find_alternatives, repair_workflow


def register(mcp: FastMCP) -> None:
    """Register workflow repair tools on the MCP server."""

    @mcp.tool()
    async def diagnose_workflow(
        workflow: dict[str, Any],
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Diagnose a workflow for missing or obsolete nodes.

        For each missing node, returns a list of alternative replacements
        ranked by compatibility (matching inputs/outputs). Known renames
        and migrations are detected automatically.

        Args:
            workflow: The workflow JSON (ComfyUI format).
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            available = await client.get_object_info()
            missing = find_missing_nodes(workflow, available)

            if not missing:
                return {"status": "ok", "message": "No missing nodes found.", "missing": []}

            results = []
            for m in missing:
                # Find the full workflow node data for signature extraction
                wf_node = None
                for n in workflow.get("nodes", []):
                    if n.get("id") == m["id"]:
                        wf_node = n
                        break

                alternatives = []
                if wf_node:
                    alternatives = find_alternatives(m["type"], wf_node, available)

                results.append({
                    **m,
                    "alternatives": alternatives,
                })

            return {
                "status": "issues_found",
                "missing_count": len(results),
                "missing": results,
            }
        finally:
            await client.close()

    @mcp.tool()
    async def repair_missing_nodes(
        workflow: dict[str, Any],
        replacements: dict[str, str] | None = None,
        auto_migrate: bool = True,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Automatically repair a workflow by replacing missing nodes with alternatives.

        Known renames and migrations are applied automatically. You can also provide
        explicit replacements. After repair, the workflow can be loaded directly.

        Args:
            workflow: The workflow JSON to repair.
            replacements: Optional manual mapping of old_type → new_type (e.g. {"OldNode": "NewNode"}).
            auto_migrate: If True (default), automatically apply known node migrations.
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            available = await client.get_object_info()
            result = repair_workflow(workflow, available, replacements, auto_migrate)

            if result["repaired_count"] > 0:
                await act.log(
                    "repair_workflow",
                    f"Repaired {result['repaired_count']} node(s): {', '.join(c['old_type'] + ' → ' + c['new_type'] for c in result['changes'])}",
                    act.SUCCESS,
                )

            if result["remaining_count"] > 0:
                await act.log(
                    "repair_workflow",
                    f"{result['remaining_count']} node(s) could not be auto-repaired",
                    act.WARNING,
                )

            return result
        finally:
            await client.close()
