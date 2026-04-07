"""Resolver tools — unified resolution pipeline for workflows, models, and dependencies."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .. import activity as act
from ..civitai_client import CivitAIClient, MODEL_TYPE_MAP
from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config
from ..huggingface_client import HuggingFaceClient
from ..workflow_analyzer import analyze_workflow, extract_model_references, extract_node_types, extract_hashes


def _comfyui_root() -> Path:
    return Path(__file__).parent.parent.parent.parent.parent


def _make_civitai(config: dict[str, Any]) -> CivitAIClient:
    return CivitAIClient(
        token=config.get("civitai_token", ""),
        nsfw_filter=config.get("nsfw_filter", "soft"),
        models_root=_comfyui_root() / "models",
    )


def _make_hf(config: dict[str, Any]) -> HuggingFaceClient:
    return HuggingFaceClient(token=config.get("huggingface_token", ""))


def register(mcp: FastMCP) -> None:
    """Register resolver tools on the MCP server."""

    # ── resolve_workflow ──────────────────────────────────────────────

    @mcp.tool()
    async def resolve_workflow(
        workflow: dict[str, Any],
        auto_install: bool = True,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Analyze a workflow and automatically resolve all missing elements: nodes, models, and dependencies.

        This is the main resolution pipeline. It will:
        1. Detect missing nodes and install them from the ComfyUI registry
        2. Detect missing models and search CivitAI/HuggingFace for them
        3. Detect and fix Python dependency conflicts

        Args:
            workflow: The workflow JSON (ComfyUI API format).
            auto_install: If True, automatically install missing nodes. Models still require confirmation.
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        civitai = _make_civitai(config)
        hf = _make_hf(config)

        await act.log("resolve_workflow", "Analyzing workflow for missing elements...", act.INFO)

        report: dict[str, Any] = {
            "status": "analyzing",
            "nodes": {"installed": [], "failed": [], "already_present": []},
            "models": {"found": [], "pending_choice": [], "not_found": []},
            "dependencies": {"status": "ok", "details": []},
        }

        try:
            # ── Step 1: Missing nodes ─────────────────────────────────
            analysis = analyze_workflow(workflow)
            required_types = analysis["node_types"]

            available_info = await client.get_object_info()
            available_types = set(available_info.keys())
            missing_nodes = [t for t in required_types if t not in available_types]

            if missing_nodes and auto_install:
                # Get node-to-package mappings from Manager
                try:
                    mappings = await client.manager_get("/customnode/getmappings")
                    if isinstance(mappings, dict):
                        node_map = mappings.get("mappings", mappings)
                    else:
                        node_map = {}
                except Exception:
                    node_map = {}

                for node_type in missing_nodes:
                    # Find which package provides this node
                    package_ref = None
                    for pkg_url, nodes_list in node_map.items():
                        if isinstance(nodes_list, list) and node_type in nodes_list:
                            package_ref = pkg_url
                            break
                        elif isinstance(nodes_list, dict):
                            node_names = nodes_list.get("nodenames", [])
                            if node_type in node_names:
                                package_ref = pkg_url
                                break

                    if package_ref:
                        try:
                            await client.manager_install_package(package_ref)
                            report["nodes"]["installed"].append({
                                "node": node_type,
                                "package": package_ref,
                            })
                            await act.log("install_node", f"Installed node '{node_type}' from {package_ref}", act.SUCCESS)
                        except Exception as exc:
                            report["nodes"]["failed"].append({
                                "node": node_type,
                                "error": str(exc),
                            })
                    else:
                        report["nodes"]["failed"].append({
                            "node": node_type,
                            "error": "Package not found in registry",
                        })
            elif missing_nodes:
                report["nodes"]["failed"] = [{"node": n, "error": "auto_install disabled"} for n in missing_nodes]

            report["nodes"]["already_present"] = [t for t in required_types if t in available_types]

            # ── Step 2: Missing models ────────────────────────────────
            model_refs = analysis["model_references"]
            hashes = analysis["hashes"]

            for ref in model_refs:
                model_name = ref["name"]
                model_type = ref["model_type"]

                # Check if model exists locally
                type_to_node = {
                    "checkpoints": "CheckpointLoaderSimple",
                    "loras": "LoraLoader",
                    "vae": "VAELoader",
                    "controlnet": "ControlNetLoader",
                    "clip": "CLIPLoader",
                    "clip_vision": "CLIPVisionLoader",
                    "ipadapter": "IPAdapterModelLoader",
                    "upscale_models": "UpscaleModelLoader",
                    "unet": "UNETLoader",
                    "diffusion_models": "UNETLoader",
                    "embeddings": None,
                }
                loader_node = type_to_node.get(model_type)
                is_present = False

                if loader_node and loader_node in available_info:
                    required = available_info[loader_node].get("input", {}).get("required", {})
                    for _key, value in required.items():
                        if isinstance(value, (list, tuple)) and len(value) > 0 and isinstance(value[0], list):
                            if model_name in value[0]:
                                is_present = True
                                break

                if is_present:
                    report["models"]["found"].append({"name": model_name, "status": "local"})
                    continue

                # Try hash lookup first
                sha = hashes.get(model_name, "")
                candidates = []

                if sha:
                    hash_result = await civitai.find_by_hash(sha)
                    if hash_result and "error" not in hash_result:
                        candidates.append(hash_result)

                # Name search on CivitAI
                if not candidates:
                    # Clean filename for search (remove extension, underscores)
                    search_name = model_name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
                    civitai_type = None
                    for ct, comfy_t in MODEL_TYPE_MAP.items():
                        if comfy_t == model_type:
                            civitai_type = ct
                            break

                    civitai_results = await civitai.search_models(
                        query=search_name,
                        model_type=civitai_type,
                        limit=3,
                    )
                    for r in civitai_results:
                        if "error" not in r:
                            candidates.append({
                                "model_id": r.get("id"),
                                "version_id": r.get("version", {}).get("id"),
                                "name": r.get("name", ""),
                                "filename": r.get("version", {}).get("filename", ""),
                                "download_url": r.get("version", {}).get("download_url", ""),
                                "size_mb": r.get("version", {}).get("size_mb", 0),
                                "sha256": r.get("version", {}).get("sha256", ""),
                                "civitai_url": r.get("civitai_url", ""),
                                "match_type": "name_search",
                                "source": "civitai",
                            })

                # HuggingFace fallback
                if not candidates:
                    hf_results = await hf.search_models(query=search_name, limit=3)
                    for r in hf_results:
                        candidates.append({
                            "name": r.get("name", ""),
                            "url": r.get("url", ""),
                            "downloads": r.get("downloads", 0),
                            "match_type": "name_search",
                            "source": "huggingface",
                        })

                if candidates:
                    report["models"]["pending_choice"].append({
                        "missing": model_name,
                        "model_type": model_type,
                        "candidates": candidates,
                    })
                else:
                    report["models"]["not_found"].append({
                        "name": model_name,
                        "model_type": model_type,
                    })

            # ── Step 3: Dependency check ──────────────────────────────
            dep_result = await _run_dependency_fix(client, instance)
            report["dependencies"] = dep_result

            # ── Final status ──────────────────────────────────────────
            has_failures = (
                report["nodes"]["failed"]
                or report["models"]["not_found"]
                or report["dependencies"].get("status") == "failed"
            )
            has_pending = report["models"]["pending_choice"]

            if has_failures:
                report["status"] = "partial"
                await act.log("resolve_workflow", "Workflow partially resolved — some issues remain", act.WARNING)
            elif has_pending:
                report["status"] = "pending_choices"
                await act.log("resolve_workflow", f"Workflow analyzed — {len(has_pending)} model(s) need selection", act.WARNING)
            else:
                report["status"] = "resolved"
                await act.log("resolve_workflow", "Workflow fully resolved — all dependencies satisfied", act.SUCCESS)

            return report
        finally:
            await client.close()
            await civitai.close()
            await hf.close()

    # ── search_civitai ────────────────────────────────────────────────

    @mcp.tool()
    async def search_civitai(
        query: str,
        model_type: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search CivitAI for models (checkpoints, LoRAs, VAE, etc.).

        Results are filtered according to the NSFW preference set in MCP Hub config.

        Args:
            query: Search text (model name, style, concept, etc.).
            model_type: Filter by type: Checkpoint, LORA, VAE, Controlnet, Upscaler, TextualInversion, Hypernetwork.
            limit: Maximum number of results (default 5).
        """
        config = load_config()
        civitai = _make_civitai(config)
        try:
            return await civitai.search_models(query=query, model_type=model_type, limit=limit)
        finally:
            await civitai.close()

    # ── download_civitai ──────────────────────────────────────────────

    @mcp.tool()
    async def download_civitai(
        version_id: int,
        model_type: str = "Checkpoint",
        filename: str = "",
    ) -> dict[str, Any]:
        """Download a specific model version from CivitAI.

        Args:
            version_id: The CivitAI model version ID to download.
            model_type: CivitAI model type (Checkpoint, LORA, VAE, etc.) — determines the target directory.
            filename: Override filename. If empty, uses the original filename from CivitAI.
        """
        config = load_config()
        civitai = _make_civitai(config)
        try:
            target_dir = civitai.resolve_target_dir(model_type)
            dl_name = filename or f"civitai_v{version_id}"
            _, tracker = act.make_download_tracker(dl_name, source="civitai")
            await tracker.start()
            await act.log("download_civitai", f"Starting download: {dl_name} ({model_type})", act.INFO)

            result = await civitai.download_model(
                version_id, target_dir, filename,
                on_progress=tracker.progress,
            )

            if "error" in result:
                await tracker.finish(success=False, error=result["error"])
                await act.log("download_civitai", f"Download failed: {result['error']}", act.ERROR)
            else:
                await tracker.finish(success=True)
                await act.log("download_civitai", f"Downloaded {result.get('filename', dl_name)} ({result.get('size_mb', 0)} MB)", act.SUCCESS)
            return result
        finally:
            await civitai.close()

    # ── find_missing_models ───────────────────────────────────────────

    @mcp.tool()
    async def find_missing_models(
        workflow: dict[str, Any],
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Analyze a workflow and list missing models with download candidates from CivitAI and HuggingFace.

        For each missing model, returns ranked candidates found by hash match (exact) or name search (fuzzy).

        Args:
            workflow: The workflow JSON.
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        civitai = _make_civitai(config)
        hf = _make_hf(config)

        try:
            model_refs = extract_model_references(workflow)
            hashes = extract_hashes(workflow)
            available_info = await client.get_object_info()
            results = []

            for ref in model_refs:
                model_name = ref["name"]
                model_type = ref["model_type"]

                # Quick local check
                is_local = _check_model_local(model_name, model_type, available_info)
                if is_local:
                    continue

                candidates = []
                sha = hashes.get(model_name, "")

                # Hash lookup (exact match)
                if sha:
                    hash_result = await civitai.find_by_hash(sha)
                    if hash_result and "error" not in hash_result:
                        hash_result["source"] = "civitai"
                        candidates.append(hash_result)

                # Name search
                search_name = model_name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
                civitai_type = _comfyui_to_civitai_type(model_type)

                civitai_results = await civitai.search_models(query=search_name, model_type=civitai_type, limit=3)
                for r in civitai_results:
                    if "error" not in r:
                        candidates.append({
                            "version_id": r.get("version", {}).get("id"),
                            "name": r.get("name", ""),
                            "filename": r.get("version", {}).get("filename", ""),
                            "size_mb": r.get("version", {}).get("size_mb", 0),
                            "civitai_url": r.get("civitai_url", ""),
                            "rating": r.get("stats", {}).get("rating", 0),
                            "downloads": r.get("stats", {}).get("downloads", 0),
                            "match_type": "name_search",
                            "source": "civitai",
                        })

                # HuggingFace fallback
                if not candidates:
                    hf_results = await hf.search_models(query=search_name, limit=3)
                    for r in hf_results:
                        candidates.append({
                            "name": r.get("name", ""),
                            "url": r.get("url", ""),
                            "downloads": r.get("downloads", 0),
                            "match_type": "name_search",
                            "source": "huggingface",
                        })

                results.append({
                    "missing": model_name,
                    "model_type": model_type,
                    "hash": sha or None,
                    "candidates": candidates,
                })

            return results
        finally:
            await client.close()
            await civitai.close()
            await hf.close()

    # ── fix_dependencies ──────────────────────────────────────────────

    @mcp.tool()
    async def fix_dependencies(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Detect and fix Python dependency conflicts between installed custom nodes.

        Uses a three-tier approach:
        - C (full-auto): attempt automatic resolution via pip
        - A (diagnostic): if auto fails, produce detailed conflict report
        - B (proposals): suggest specific actions to resolve remaining conflicts

        Args:
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            return await _run_dependency_fix(client, instance)
        finally:
            await client.close()


# ── Internal helpers ──────────────────────────────────────────────────


def _check_model_local(model_name: str, model_type: str, available_info: dict) -> bool:
    """Check if a model is available locally."""
    type_to_node = {
        "checkpoints": "CheckpointLoaderSimple",
        "loras": "LoraLoader",
        "vae": "VAELoader",
        "controlnet": "ControlNetLoader",
        "clip": "CLIPLoader",
        "clip_vision": "CLIPVisionLoader",
        "ipadapter": "IPAdapterModelLoader",
        "upscale_models": "UpscaleModelLoader",
        "unet": "UNETLoader",
        "diffusion_models": "UNETLoader",
    }
    loader = type_to_node.get(model_type)
    if not loader or loader not in available_info:
        return False
    required = available_info[loader].get("input", {}).get("required", {})
    for _key, value in required.items():
        if isinstance(value, (list, tuple)) and len(value) > 0 and isinstance(value[0], list):
            if model_name in value[0]:
                return True
    return False


def _comfyui_to_civitai_type(comfyui_type: str) -> str | None:
    """Convert ComfyUI model type to CivitAI type string."""
    reverse = {v: k for k, v in MODEL_TYPE_MAP.items()}
    return reverse.get(comfyui_type)


async def _run_dependency_fix(client: ComfyUIClient, instance: str | None) -> dict[str, Any]:
    """Three-tier dependency resolution: C → A → B."""
    result: dict[str, Any] = {"status": "ok", "details": []}

    # Get import failures from Manager
    try:
        fail_info = await client.manager_post("/customnode/import_fail_info")
    except Exception:
        fail_info = []

    if not fail_info or (isinstance(fail_info, list) and len(fail_info) == 0):
        # Also run pip check
        pip_issues = _pip_check()
        if not pip_issues:
            return result
        # There are pip issues but no import failures
        result["details"] = pip_issues
    else:
        result["details"] = fail_info if isinstance(fail_info, list) else [fail_info]

    # ── Tier C: Auto-fix ──────────────────────────────────────────
    auto_fixed = []
    still_broken = []

    for failure in result["details"]:
        error_msg = failure.get("error", "") if isinstance(failure, dict) else str(failure)

        # Try to extract the missing/conflicting package name
        pkg_name = _extract_package_from_error(error_msg)
        if pkg_name:
            success = _try_pip_install(pkg_name)
            if success:
                auto_fixed.append({"package": pkg_name, "action": "installed/upgraded"})
                continue

        still_broken.append(failure)

    if auto_fixed and not still_broken:
        return {"status": "fixed", "fixed": auto_fixed, "details": []}

    # ── Tier A: Diagnostic ────────────────────────────────────────
    diagnostics = []
    for failure in still_broken:
        error_msg = failure.get("error", "") if isinstance(failure, dict) else str(failure)
        node_name = failure.get("title", failure.get("id", "unknown")) if isinstance(failure, dict) else "unknown"

        diagnostic = {
            "node": node_name,
            "error": error_msg,
            "root_cause": _diagnose_error(error_msg),
        }
        diagnostics.append(diagnostic)

    # ── Tier B: Proposals ─────────────────────────────────────────
    proposals = []
    for diag in diagnostics:
        proposal = _suggest_fix(diag)
        if proposal:
            proposals.append(proposal)

    return {
        "status": "partial" if auto_fixed else "failed",
        "fixed": auto_fixed,
        "diagnostics": diagnostics,
        "proposals": proposals,
    }


def _pip_check() -> list[dict[str, str]]:
    """Run pip check and return any conflicts."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return []
        issues = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                issues.append({"type": "pip_conflict", "message": line.strip()})
        return issues
    except Exception:
        return []


def _extract_package_from_error(error: str) -> str | None:
    """Try to extract a pip package name from an import error message."""
    import re

    # "No module named 'xxx'"
    m = re.search(r"No module named ['\"]([^'\"]+)['\"]", error)
    if m:
        pkg = m.group(1).split(".")[0]
        # Map common import names to pip names
        pip_names = {
            "cv2": "opencv-python",
            "PIL": "Pillow",
            "sklearn": "scikit-learn",
            "skimage": "scikit-image",
            "yaml": "pyyaml",
            "attr": "attrs",
        }
        return pip_names.get(pkg, pkg)

    # "xxx requires yyy>=version, but you have zzz"
    m = re.search(r"requires ([a-zA-Z0-9_-]+)", error)
    if m:
        return m.group(1)

    return None


def _try_pip_install(package: str) -> bool:
    """Attempt to pip install/upgrade a package."""
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", package],
            timeout=120,
        )
        return True
    except Exception:
        return False


def _diagnose_error(error: str) -> str:
    """Produce a human-readable root cause from an error message."""
    if "No module named" in error:
        return "Missing Python package — not installed in the current environment."
    if "requires" in error and "but you have" in error:
        return "Version conflict — two packages require incompatible versions of a dependency."
    if "DLL" in error or "shared object" in error or ".so" in error:
        return "Binary/native library missing — may need system-level installation."
    if "CUDA" in error or "cuda" in error:
        return "CUDA-related error — GPU driver or CUDA toolkit mismatch."
    if "ImportError" in error:
        return "Import error — package may be partially installed or corrupted."
    return "Unknown error — manual investigation recommended."


def _suggest_fix(diagnostic: dict[str, Any]) -> dict[str, str] | None:
    """Suggest a concrete fix for a diagnostic."""
    error = diagnostic.get("error", "")
    root = diagnostic.get("root_cause", "")
    node = diagnostic.get("node", "unknown")

    if "Missing Python package" in root:
        pkg = _extract_package_from_error(error)
        if pkg:
            return {
                "node": node,
                "action": f"pip install {pkg}",
                "description": f"Install the missing package '{pkg}'.",
            }

    if "Version conflict" in root:
        return {
            "node": node,
            "action": "pip install --upgrade <conflicting-package>",
            "description": "Upgrade the conflicting dependency. Check both nodes' requirements.txt for compatible versions.",
        }

    if "Binary/native library" in root:
        return {
            "node": node,
            "action": "reinstall",
            "description": f"Try reinstalling the node package for '{node}'. If it persists, check system dependencies.",
        }

    return None
