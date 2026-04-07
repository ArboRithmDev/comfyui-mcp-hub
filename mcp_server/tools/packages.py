"""Package management tools — search, install, update, and manage custom nodes."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .. import activity as act
from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config


def register(mcp: FastMCP) -> None:
    """Register package management tools on the MCP server."""

    @mcp.tool()
    async def search_packages(
        query: str,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for custom node packages on the ComfyUI registry.

        Args:
            query: Search term to find custom nodes.
            instance: Target ComfyUI instance name (Manager must be installed).
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            # Try v2 getmappings first, then fall back to getlist
            try:
                nodes = await client.manager_get("/customnode/getlist")
            except Exception:
                nodes = {}

            if not isinstance(nodes, dict) or "custom_nodes" not in nodes:
                # V2 may not have getlist — use installed + mappings as fallback
                mappings = await client.manager_get_mappings()
                if isinstance(mappings, dict):
                    results = []
                    query_lower = query.lower()
                    for pkg_url, node_info in mappings.items():
                        pkg_name = pkg_url.split("/")[-1] if "/" in pkg_url else pkg_url
                        node_names = node_info if isinstance(node_info, list) else node_info.get("nodenames", [])
                        if query_lower in pkg_name.lower() or any(query_lower in n.lower() for n in node_names):
                            results.append({
                                "title": pkg_name,
                                "reference": pkg_url,
                                "nodes": node_names[:10],
                            })
                    return results
                return [{"error": "Unexpected response from ComfyUI-Manager"}]

            results = []
            query_lower = query.lower()
            for node in nodes.get("custom_nodes", []):
                title = node.get("title", "")
                desc = node.get("description", "")
                ref = node.get("reference", "")
                if query_lower in title.lower() or query_lower in desc.lower() or query_lower in ref.lower():
                    results.append({
                        "title": title,
                        "description": desc,
                        "reference": ref,
                        "author": node.get("author", ""),
                        "installed": node.get("installed", "False"),
                    })
            return results
        except Exception as exc:
            return [{"error": str(exc), "hint": "ComfyUI-Manager must be installed."}]
        finally:
            await client.close()

    @mcp.tool()
    async def install_package(
        reference: str,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Install a custom node package. Requires ComfyUI-Manager.

        Args:
            reference: Git URL or package reference for the custom node.
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            result = await client.manager_install_package(reference)
            await act.log("install_package", f"Installing package: {reference}", act.INFO)
            return {"status": "install_queued", "reference": reference, "details": result}
        except Exception as exc:
            await act.log("install_package", f"Install failed: {reference} — {exc}", act.ERROR)
            return {"error": str(exc)}
        finally:
            await client.close()

    @mcp.tool()
    async def update_package(
        reference: str,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Update a custom node package. Requires ComfyUI-Manager.

        Args:
            reference: Package reference or name to update.
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            result = await client.manager_update_package(reference)
            await act.log("update_package", f"Updating package: {reference}", act.INFO)
            return {"status": "update_queued", "reference": reference, "details": result}
        except Exception as exc:
            await act.log("update_package", f"Update failed: {reference} — {exc}", act.ERROR)
            return {"error": str(exc)}
        finally:
            await client.close()

    @mcp.tool()
    async def uninstall_package(
        reference: str,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Uninstall a custom node package. Requires ComfyUI-Manager.

        WARNING: This will remove the custom node and its files.

        Args:
            reference: Package reference or name to uninstall.
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            result = await client.manager_uninstall_package(reference)
            await act.log("uninstall_package", f"Uninstalling package: {reference}", act.WARNING)
            return {
                "status": "uninstall_queued",
                "warning": "A ComfyUI restart may be required.",
                "reference": reference,
                "details": result,
            }
        except Exception as exc:
            await act.log("uninstall_package", f"Uninstall failed: {reference} — {exc}", act.ERROR)
            return {"error": str(exc)}
        finally:
            await client.close()

    @mcp.tool()
    async def list_installed(
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all installed custom node packages with their versions.

        Args:
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            result = await client.manager_get_installed()
            if isinstance(result, dict) and "custom_nodes" in result:
                return [
                    {
                        "title": n.get("title", ""),
                        "version": n.get("version", "unknown"),
                        "reference": n.get("reference", ""),
                        "cnr_id": n.get("cnr_id", ""),
                        "enabled": n.get("enabled", True),
                    }
                    for n in result["custom_nodes"]
                ]
            return result if isinstance(result, list) else []
        except Exception as exc:
            return [{"error": str(exc)}]
        finally:
            await client.close()

    @mcp.tool()
    async def check_updates(
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Check for available updates for installed custom nodes.

        Args:
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            result = await client.manager_get("/customnode/fetch_updates")
            return result if isinstance(result, list) else [result]
        except Exception as exc:
            return [{"error": str(exc)}]
        finally:
            await client.close()

    @mcp.tool()
    async def resolve_conflicts(
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Detect dependency conflicts between installed custom nodes and suggest resolutions.

        Args:
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            fail_info = await client.manager_post("/customnode/import_fail_info")
            conflicts = []
            if isinstance(fail_info, list):
                for failure in fail_info:
                    conflicts.append({
                        "node": failure.get("title", failure.get("id", "unknown")),
                        "error": failure.get("error", ""),
                        "suggestion": "Try reinstalling or updating this node.",
                    })
            elif isinstance(fail_info, dict):
                for key, info in fail_info.items():
                    if isinstance(info, dict) and info.get("error"):
                        conflicts.append({
                            "node": key,
                            "error": info["error"],
                            "suggestion": "Try reinstalling or updating this node.",
                        })

            return {
                "conflicts_found": len(conflicts),
                "conflicts": conflicts,
            }
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            await client.close()
