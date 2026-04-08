"""Workflow operations — optimizer, templates, prompt separation, and versioning."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config


def _workflows_dir() -> Path:
    d = Path(__file__).parent.parent.parent.parent.parent / "user" / "default" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _templates_dir() -> Path:
    d = Path(__file__).parent.parent.parent.parent.parent / "user" / "default" / "workflows" / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _inputs_dir() -> Path:
    d = Path(__file__).parent.parent.parent.parent.parent / "user" / "default" / "workflows" / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Loader node types for dedup detection ────────────────────────────

_LOADER_TYPES = {
    "CheckpointLoaderSimple", "CheckpointLoader", "LoraLoader",
    "LoraLoaderModelOnly", "VAELoader", "CLIPLoader", "CLIPVisionLoader",
    "DualCLIPLoader", "UNETLoader", "ControlNetLoader",
    "IPAdapterModelLoader", "IPAdapterModelLoaderV2",
    "UpscaleModelLoader", "ImageOnlyCheckpointLoader",
}

# ── Widget keys that contain user-creative content ───────────────────

_PROMPT_WIDGET_KEYS = {"text", "prompt", "negative", "string", "text_positive", "text_negative"}
_SEED_WIDGET_KEYS = {"seed", "noise_seed"}


def register(mcp: FastMCP) -> None:
    """Register workflow operation tools on the MCP server."""

    # ── Optimize workflow ─────────────────────────────────────────────

    @mcp.tool()
    async def optimize_workflow(
        workflow: dict[str, Any],
        auto_merge: bool = False,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Analyze a workflow for duplicate model loaders and optimization opportunities.

        Detects nodes that load the same model (same class_type + same model file)
        and either suggests merging them or merges automatically.

        Args:
            workflow: The workflow in ComfyUI API format.
            auto_merge: If True, automatically merge duplicates and return the optimized workflow.
                        If False, just report duplicates with suggestions.
            instance: Target ComfyUI instance name.
        """
        # Find duplicate loaders
        loader_fingerprints: dict[str, list[str]] = {}  # fingerprint → [node_ids]

        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            if class_type not in _LOADER_TYPES:
                continue

            inputs = node.get("inputs", {})
            # Build fingerprint from class_type + model-file inputs (ignore non-model params)
            model_keys = sorted(
                k for k, v in inputs.items()
                if isinstance(v, str) and ("." in v or "/" in v)
            )
            fp_parts = [class_type] + [f"{k}={inputs[k]}" for k in model_keys]
            fingerprint = "|".join(fp_parts)

            loader_fingerprints.setdefault(fingerprint, []).append(node_id)

        duplicates = {fp: ids for fp, ids in loader_fingerprints.items() if len(ids) > 1}

        if not duplicates:
            return {"status": "optimized", "message": "No duplicate loaders found.", "duplicates": []}

        report = []
        for fp, node_ids in duplicates.items():
            parts = fp.split("|")
            report.append({
                "class_type": parts[0],
                "model": parts[1] if len(parts) > 1 else "",
                "node_ids": node_ids,
                "keep": node_ids[0],
                "remove": node_ids[1:],
            })

        if not auto_merge:
            return {
                "status": "duplicates_found",
                "duplicates": report,
                "message": f"Found {len(report)} duplicate loader group(s). Set auto_merge=True to fix.",
            }

        # Auto-merge: rewire connections from duplicates to the kept node
        optimized = dict(workflow)
        for dup in report:
            keep_id = dup["keep"]
            for remove_id in dup["remove"]:
                # Find all nodes that reference remove_id and point them to keep_id
                for nid, node in optimized.items():
                    if not isinstance(node, dict):
                        continue
                    inputs = node.get("inputs", {})
                    for key, value in inputs.items():
                        if isinstance(value, list) and len(value) == 2 and value[0] == remove_id:
                            inputs[key] = [keep_id, value[1]]
                # Remove the duplicate node
                optimized.pop(remove_id, None)

        return {
            "status": "merged",
            "duplicates_merged": len(report),
            "nodes_removed": sum(len(d["remove"]) for d in report),
            "workflow": optimized,
        }

    # ── Templatize workflow ───────────────────────────────────────────

    @mcp.tool()
    async def templatize_workflow(
        name: str,
        workflow: dict[str, Any] | None = None,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Extract prompts and seeds from a workflow into a template + inputs file.

        Saves:
        - `templates/{name}.json` — the workflow with prompts replaced by `{{variable_name}}`
        - `inputs/{name}.json` — the extracted prompt values and seeds

        The template can be shared without exposing personal creative content.
        Use apply_template to re-inject inputs into a template.

        Args:
            name: Name for the template (without extension).
            workflow: Workflow in API format. If omitted, reads from canvas.
            instance: Target ComfyUI instance name.
        """
        if not workflow:
            # Get from canvas
            config = load_config()
            client = ComfyUIClient(get_instance_url(config, instance))
            try:
                result = await client.post("/mcp-hub/ui/command", data={
                    "command": "get_api_prompt", "data": {}, "timeout": 10,
                })
                workflow = result.get("prompt", {})
            finally:
                await client.close()

        if not workflow:
            return {"error": "No workflow provided and canvas is empty"}

        template = json.loads(json.dumps(workflow))  # deep copy
        inputs: dict[str, Any] = {}
        var_counter = 0

        for node_id, node in template.items():
            if not isinstance(node, dict):
                continue
            node_inputs = node.get("inputs", {})
            class_type = node.get("class_type", "")

            for key, value in list(node_inputs.items()):
                if not isinstance(value, str):
                    continue
                key_lower = key.lower()

                # Extract prompts
                if any(pk in key_lower for pk in _PROMPT_WIDGET_KEYS):
                    var_name = f"{class_type}_{node_id}_{key}".replace(" ", "_")
                    inputs[var_name] = value
                    node_inputs[key] = "{{" + var_name + "}}"
                    var_counter += 1

            # Extract seeds (numeric)
            for key, value in list(node_inputs.items()):
                if isinstance(value, (int, float)):
                    key_lower = key.lower()
                    if any(sk in key_lower for sk in _SEED_WIDGET_KEYS):
                        var_name = f"{class_type}_{node_id}_{key}".replace(" ", "_")
                        inputs[var_name] = value
                        node_inputs[key] = "{{" + var_name + "}}"
                        var_counter += 1

        # Save files
        template_path = _templates_dir() / f"{name}.json"
        inputs_path = _inputs_dir() / f"{name}.json"
        template_path.write_text(json.dumps(template, indent=2))
        inputs_path.write_text(json.dumps(inputs, indent=2))

        return {
            "status": "templatized",
            "template": str(template_path),
            "inputs": str(inputs_path),
            "variables_extracted": var_counter,
            "variable_names": list(inputs.keys()),
        }

    # ── Apply template ───────────────────────────────────────────────

    @mcp.tool()
    async def apply_template(
        name: str,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Load a template and inject input values to produce a ready-to-execute workflow.

        Args:
            name: Template name (without extension).
            overrides: Optional dict of variable_name → value to override specific inputs.
                       Unspecified variables use their saved values from the inputs file.
        """
        template_path = _templates_dir() / f"{name}.json"
        inputs_path = _inputs_dir() / f"{name}.json"

        if not template_path.exists():
            return {"error": f"Template '{name}' not found at {template_path}"}

        template_str = template_path.read_text()
        inputs = {}
        if inputs_path.exists():
            inputs = json.loads(inputs_path.read_text())

        # Apply overrides
        if overrides:
            inputs.update(overrides)

        # Replace variables
        for var_name, value in inputs.items():
            placeholder = "{{" + var_name + "}}"
            if isinstance(value, str):
                template_str = template_str.replace(f'"{placeholder}"', json.dumps(value))
            else:
                template_str = template_str.replace(f'"{placeholder}"', json.dumps(value))

        workflow = json.loads(template_str)

        # Check for unreplaced variables
        remaining = re.findall(r'\{\{(\w+)\}\}', template_str)
        if remaining:
            return {
                "status": "partial",
                "workflow": workflow,
                "missing_variables": remaining,
                "message": f"{len(remaining)} variable(s) still unresolved.",
            }

        return {"status": "ready", "workflow": workflow}

    # ── List templates ───────────────────────────────────────────────

    @mcp.tool()
    async def list_templates() -> list[dict[str, Any]]:
        """List all saved workflow templates with their variables."""
        templates = []
        for f in sorted(_templates_dir().glob("*.json")):
            inputs_path = _inputs_dir() / f.name
            variables = []
            if inputs_path.exists():
                try:
                    variables = list(json.loads(inputs_path.read_text()).keys())
                except Exception:
                    pass
            templates.append({
                "name": f.stem,
                "template_path": str(f),
                "inputs_path": str(inputs_path) if inputs_path.exists() else None,
                "variables": variables,
            })
        return templates

    # ── Workflow git ─────────────────────────────────────────────────

    @mcp.tool()
    async def workflow_git(
        action: str,
        message: str = "",
        remote_url: str = "",
        filename: str = "",
    ) -> dict[str, Any]:
        """Version control for workflows using git.

        Manages a git repository in the workflows directory for tracking changes,
        restoring previous versions, and pushing to a remote.

        Args:
            action: Git action to perform:
                - "init": Initialize git repo in the workflows directory
                - "status": Show changed/untracked workflow files
                - "commit": Commit all workflow changes (requires message)
                - "log": Show recent commit history
                - "diff": Show changes since last commit
                - "restore": Restore a specific file from last commit (requires filename)
                - "remote": Set remote URL for pushing (requires remote_url)
                - "push": Push commits to remote
                - "pull": Pull from remote
            message: Commit message (for "commit" action).
            remote_url: Remote git URL (for "remote" action).
            filename: Filename to restore (for "restore" action).
        """
        wf_dir = str(_workflows_dir())
        config = load_config()
        git_dir = config.get("workflow_git_dir", wf_dir)

        def _run(cmd: list[str]) -> dict[str, str]:
            try:
                result = subprocess.run(
                    ["git", "-C", git_dir] + cmd,
                    capture_output=True, text=True, timeout=30,
                )
                return {
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "returncode": str(result.returncode),
                }
            except Exception as exc:
                return {"error": str(exc)}

        if action == "init":
            result = _run(["init"])
            # Also create .gitignore for non-workflow files
            gitignore = Path(git_dir) / ".gitignore"
            if not gitignore.exists():
                gitignore.write_text("__pycache__/\n*.pyc\n.DS_Store\n")
            return {"status": "initialized", "path": git_dir, "details": result}

        elif action == "status":
            return _run(["status", "--porcelain"])

        elif action == "commit":
            if not message:
                message = f"Workflow update — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            _run(["add", "-A"])
            return _run(["commit", "-m", message])

        elif action == "log":
            return _run(["log", "--oneline", "-20"])

        elif action == "diff":
            staged = _run(["diff", "--cached", "--stat"])
            unstaged = _run(["diff", "--stat"])
            return {"staged": staged, "unstaged": unstaged}

        elif action == "restore":
            if not filename:
                return {"error": "filename is required for restore"}
            return _run(["checkout", "HEAD", "--", filename])

        elif action == "remote":
            if not remote_url:
                return {"error": "remote_url is required"}
            result = _run(["remote", "add", "origin", remote_url])
            if "already exists" in result.get("stderr", ""):
                result = _run(["remote", "set-url", "origin", remote_url])
            return {"status": "remote_set", "url": remote_url, "details": result}

        elif action == "push":
            return _run(["push", "-u", "origin", "main"])

        elif action == "pull":
            return _run(["pull", "origin", "main"])

        else:
            return {"error": f"Unknown action: {action}. Use: init, status, commit, log, diff, restore, remote, push, pull"}
