"""Workflow repair — detect missing/obsolete nodes and replace with alternatives."""

from __future__ import annotations

from typing import Any

# ── Known renames and migrations ─────────────────────────────────────

# Map of old_node_type → new_node_type for known renames/deprecations.
# This is checked first before fuzzy matching.
KNOWN_MIGRATIONS: dict[str, str] = {
    # ComfyUI core renames
    "LoadImage": "LoadImage",
    "ImageBatch": "BatchImagesNode",
    # Impact Pack renames
    "SAMLoader": "SAMLoader (Impact)",
    # KJNodes
    "ConditioningSetMaskAndCombine": "ConditioningSetMaskAndCombine",
    # MCP Hub → Arbo Tools migration
    "MCPHub_OptionalLoadImage": "ArboTools_OptionalLoadImage",
    "MCPHub_OptionalMergeImages": "ArboTools_OptionalMergeImages",
    "MCPHub_JoinTextList": "ArboTools_JoinTextList",
}


def find_missing_nodes(workflow: dict[str, Any], available_nodes: dict[str, Any]) -> list[dict[str, Any]]:
    """Find nodes in the workflow that are not available in ComfyUI.

    Args:
        workflow: The workflow JSON (ComfyUI format with 'nodes' list).
        available_nodes: The object_info dict from ComfyUI API.

    Returns:
        List of missing node entries with id, type, title, and position.
    """
    nodes = workflow.get("nodes", [])
    missing = []
    for node in nodes:
        node_type = node.get("type", "")
        if not node_type:
            continue
        # Skip special types (reroute, notes, groups, etc.)
        if node_type in ("Reroute", "Note", "PrimitiveNode", "Group"):
            continue
        if node_type not in available_nodes:
            missing.append({
                "id": node.get("id"),
                "type": node_type,
                "title": node.get("title", ""),
                "pos": node.get("pos"),
            })
    return missing


def _get_node_signature(node_info: dict[str, Any]) -> dict[str, Any]:
    """Extract input/output type signature from a node's object_info."""
    inputs = node_info.get("input", {})
    required = inputs.get("required", {})
    optional = inputs.get("optional", {})

    input_types = {}
    for name, spec in {**required, **optional}.items():
        if isinstance(spec, (list, tuple)) and len(spec) > 0:
            typ = spec[0]
            if isinstance(typ, list):
                # Combo/enum — store as "COMBO"
                input_types[name] = "COMBO"
            else:
                input_types[name] = typ
        else:
            input_types[name] = "UNKNOWN"

    output_types = node_info.get("output", [])
    output_names = node_info.get("output_name", output_types)

    return {
        "input_types": input_types,
        "output_types": list(output_types),
        "output_names": list(output_names),
        "category": node_info.get("category", ""),
    }


def _get_workflow_node_signature(node: dict[str, Any]) -> dict[str, Any]:
    """Extract input/output type signature from a workflow node."""
    input_types = {}
    for inp in node.get("inputs", []):
        name = inp.get("name", "")
        typ = inp.get("type", "UNKNOWN")
        if name and typ != "IMAGEUPLOAD":
            input_types[name] = typ

    output_types = []
    output_names = []
    for out in node.get("outputs", []):
        output_types.append(out.get("type", "UNKNOWN"))
        output_names.append(out.get("name", ""))

    return {
        "input_types": input_types,
        "output_types": output_types,
        "output_names": output_names,
    }


def _score_match(missing_sig: dict, candidate_sig: dict) -> float:
    """Score how well a candidate node matches a missing node's signature.

    Returns a score between 0.0 (no match) and 1.0 (perfect match).
    """
    score = 0.0
    total_weight = 0.0

    # Output type matching (most important — determines what the node produces)
    m_outputs = missing_sig.get("output_types", [])
    c_outputs = candidate_sig.get("output_types", [])
    if m_outputs:
        total_weight += 3.0
        if m_outputs == c_outputs:
            score += 3.0
        elif set(m_outputs) == set(c_outputs):
            score += 2.5
        elif set(m_outputs).issubset(set(c_outputs)):
            score += 2.0
        elif any(t in c_outputs for t in m_outputs):
            score += 1.0

    # Input type matching
    m_inputs = missing_sig.get("input_types", {})
    c_inputs = candidate_sig.get("input_types", {})
    if m_inputs:
        total_weight += 2.0
        m_types = set(m_inputs.values())
        c_types = set(c_inputs.values())
        if m_types == c_types:
            score += 2.0
        elif m_types.issubset(c_types):
            score += 1.5
        elif len(m_types & c_types) > 0:
            overlap = len(m_types & c_types) / len(m_types)
            score += overlap * 1.5

    # Input name matching (bonus for same slot names)
    if m_inputs and c_inputs:
        total_weight += 1.0
        common_names = set(m_inputs.keys()) & set(c_inputs.keys())
        if common_names:
            # Check if common names also have matching types
            type_matches = sum(
                1 for n in common_names if m_inputs[n] == c_inputs[n]
            )
            score += type_matches / max(len(m_inputs), 1)

    return score / total_weight if total_weight > 0 else 0.0


def find_alternatives(
    missing_type: str,
    missing_node: dict[str, Any],
    available_nodes: dict[str, Any],
    max_results: int = 5,
    min_score: float = 0.3,
) -> list[dict[str, Any]]:
    """Find alternative nodes that could replace a missing node.

    Args:
        missing_type: The class name of the missing node.
        missing_node: The workflow node dict.
        available_nodes: The object_info dict from ComfyUI API.
        max_results: Maximum alternatives to return.
        min_score: Minimum match score threshold.

    Returns:
        List of alternatives sorted by match score (best first).
    """
    # Check known migrations first
    if missing_type in KNOWN_MIGRATIONS:
        migrated = KNOWN_MIGRATIONS[missing_type]
        if migrated in available_nodes:
            return [{
                "type": migrated,
                "display_name": available_nodes[migrated].get("display_name", migrated),
                "category": available_nodes[migrated].get("category", ""),
                "score": 1.0,
                "match_reason": "known_migration",
            }]

    # Extract signature from the workflow node
    missing_sig = _get_workflow_node_signature(missing_node)
    if not missing_sig["output_types"] and not missing_sig["input_types"]:
        return []

    # Score all available nodes
    candidates = []
    for node_type, node_info in available_nodes.items():
        candidate_sig = _get_node_signature(node_info)
        score = _score_match(missing_sig, candidate_sig)

        if score >= min_score:
            candidates.append({
                "type": node_type,
                "display_name": node_info.get("display_name", node_type),
                "category": node_info.get("category", ""),
                "score": round(score, 3),
                "match_reason": "signature_match",
            })

    # Sort by score descending
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:max_results]


def repair_workflow(
    workflow: dict[str, Any],
    available_nodes: dict[str, Any],
    replacements: dict[str, str] | None = None,
    auto_migrate: bool = True,
) -> dict[str, Any]:
    """Repair a workflow by replacing missing nodes with alternatives.

    Args:
        workflow: The workflow JSON.
        available_nodes: The object_info dict from ComfyUI API.
        replacements: Optional manual mapping of old_type → new_type.
        auto_migrate: If True, automatically apply known migrations.

    Returns:
        Dict with the repaired workflow, list of changes made, and remaining issues.
    """
    nodes = workflow.get("nodes", [])
    links = workflow.get("links", [])

    # Build effective replacement map
    replace_map: dict[str, str] = {}
    if auto_migrate:
        for old, new in KNOWN_MIGRATIONS.items():
            if new in available_nodes:
                replace_map[old] = new
    if replacements:
        replace_map.update(replacements)

    changes = []
    remaining = []

    for node in nodes:
        node_type = node.get("type", "")
        if not node_type or node_type in available_nodes:
            continue
        if node_type in ("Reroute", "Note", "PrimitiveNode", "Group"):
            continue

        new_type = replace_map.get(node_type)
        if new_type and new_type in available_nodes:
            old_type = node_type
            node["type"] = new_type

            new_info = available_nodes[new_type]
            new_sig = _get_node_signature(new_info)

            # Update display name if it was the default
            if node.get("title", "") == "" or node.get("title", "") == old_type:
                node["title"] = new_info.get("display_name", new_type)

            # Update properties
            props = node.get("properties", {})
            if "Node name for S&R" in props:
                props["Node name for S&R"] = new_type

            # Remap outputs — match by type, then by position
            old_outputs = node.get("outputs", [])
            new_output_types = new_sig["output_types"]
            new_output_names = new_sig["output_names"]

            for i, out in enumerate(old_outputs):
                if i < len(new_output_types):
                    out["type"] = new_output_types[i]
                    if i < len(new_output_names):
                        out["name"] = new_output_names[i]

            # Remap inputs — match by name+type, then by type only
            old_inputs = node.get("inputs", [])
            new_input_types = new_sig["input_types"]

            for inp in old_inputs:
                inp_name = inp.get("name", "")
                inp_type = inp.get("type", "")

                # Direct name match
                if inp_name in new_input_types:
                    inp["type"] = new_input_types[inp_name]
                    continue

                # Type match — find an input with the same type
                for new_name, new_t in new_input_types.items():
                    if new_t == inp_type:
                        inp["name"] = new_name
                        break

            changes.append({
                "node_id": node.get("id"),
                "old_type": old_type,
                "new_type": new_type,
                "title": node.get("title", ""),
            })
        else:
            # No replacement available
            alternatives = find_alternatives(node_type, node, available_nodes, max_results=3)
            remaining.append({
                "node_id": node.get("id"),
                "type": node_type,
                "title": node.get("title", ""),
                "alternatives": alternatives,
            })

    return {
        "workflow": workflow,
        "changes": changes,
        "remaining": remaining,
        "repaired_count": len(changes),
        "remaining_count": len(remaining),
    }
