"""Parse ComfyUI workflow JSON to extract nodes, model references, and hashes."""

from __future__ import annotations

from typing import Any

# Node input keys that typically hold model file references
_MODEL_INPUT_KEYS = {
    "ckpt_name", "lora_name", "vae_name", "control_net_name",
    "clip_name", "unet_name", "model_name", "upscale_model",
    "embedding", "hypernetwork_name", "style_model_name",
    "gligen_name", "ipadapter_file", "lora_name_1", "lora_name_2",
    "lora_name_3", "lora_name_4",
}

# Map input key patterns to model types (for directory placement)
_KEY_TO_MODEL_TYPE: dict[str, str] = {
    "ckpt_name": "checkpoints",
    "lora_name": "loras",
    "vae_name": "vae",
    "control_net_name": "controlnet",
    "clip_name": "clip",
    "unet_name": "diffusion_models",
    "upscale_model": "upscale_models",
    "embedding": "embeddings",
    "hypernetwork_name": "hypernetworks",
    "style_model_name": "style_models",
    "ipadapter_file": "ipadapter",
}


def _guess_model_type(key: str, node_type: str = "") -> str:
    """Guess model type from input key name and node class type."""
    # Node type gives the best signal for ambiguous keys like "clip_name"
    nt = node_type.lower()
    if "clipvision" in nt or "clip_vision" in nt:
        return "clip_vision"
    if "ipadapter" in nt and "load" in nt:
        return "ipadapter"

    for pattern, model_type in _KEY_TO_MODEL_TYPE.items():
        if pattern in key.lower():
            return model_type
    if "lora" in key.lower():
        return "loras"
    if "checkpoint" in key.lower() or "ckpt" in key.lower():
        return "checkpoints"
    if "vae" in key.lower():
        return "vae"
    return "checkpoints"


def extract_node_types(workflow: dict[str, Any]) -> list[str]:
    """Extract all class_type values from a workflow.

    Supports both API format (flat dict of nodes) and
    UI format (nodes in a "nodes" list).
    """
    class_types: set[str] = set()

    # API format: {"1": {"class_type": "...", "inputs": {...}}, ...}
    if all(isinstance(v, dict) for v in workflow.values()):
        for node in workflow.values():
            ct = node.get("class_type")
            if ct:
                class_types.add(ct)

    # UI format: {"nodes": [{"type": "...", ...}, ...]}
    if "nodes" in workflow and isinstance(workflow["nodes"], list):
        for node in workflow["nodes"]:
            ct = node.get("type") or node.get("class_type")
            if ct:
                class_types.add(ct)

    return sorted(class_types)


def extract_model_references(workflow: dict[str, Any]) -> list[dict[str, str]]:
    """Extract all model file references from a workflow.

    Returns a list of dicts with keys: name, key, model_type, node_type.
    """
    refs: list[dict[str, str]] = []
    seen: set[str] = set()

    def _scan_inputs(inputs: dict[str, Any], node_type: str) -> None:
        for key, value in inputs.items():
            if not isinstance(value, str):
                continue
            # Check known model keys
            is_model_key = any(mk in key.lower() for mk in _MODEL_INPUT_KEYS)
            # Also catch keys ending with _name that look like model refs
            if not is_model_key and key.endswith("_name") and "/" not in value and "." in value:
                is_model_key = True
            if is_model_key and value and value not in seen:
                seen.add(value)
                refs.append({
                    "name": value,
                    "key": key,
                    "model_type": _guess_model_type(key, node_type),
                    "node_type": node_type,
                })

    # API format
    for node_id, node in workflow.items():
        if isinstance(node, dict) and "inputs" in node:
            _scan_inputs(node["inputs"], node.get("class_type", ""))

    # UI format
    if "nodes" in workflow and isinstance(workflow["nodes"], list):
        for node in workflow["nodes"]:
            widgets = node.get("widgets_values", [])
            node_type = node.get("type", "")
            # Widget values are positional — harder to map, skip for now
            # Focus on the "inputs" dict if present
            if "inputs" in node and isinstance(node["inputs"], dict):
                _scan_inputs(node["inputs"], node_type)

    return refs


def extract_hashes(workflow: dict[str, Any]) -> dict[str, str]:
    """Extract model hashes from workflow metadata if present.

    Some workflows embed hashes in extra_data or node metadata.
    Returns a dict mapping filename → SHA256 hash.
    """
    hashes: dict[str, str] = {}

    # Check for hashes in workflow metadata
    extra = workflow.get("extra_data", {}) or workflow.get("extra", {})
    if isinstance(extra, dict):
        wf_meta = extra.get("workflow", {})
        if isinstance(wf_meta, dict):
            for node in wf_meta.get("nodes", []):
                props = node.get("properties", {})
                if isinstance(props, dict):
                    for key, value in props.items():
                        if "hash" in key.lower() and isinstance(value, str) and len(value) >= 32:
                            # Try to find the associated filename
                            widgets = node.get("widgets_values", [])
                            for w in widgets:
                                if isinstance(w, str) and "." in w:
                                    hashes[w] = value
                                    break

    # Some workflows store hashes directly in prompt metadata
    prompt_meta = workflow.get("prompt", {})
    if isinstance(prompt_meta, dict):
        for node_id, node in prompt_meta.items():
            if isinstance(node, dict) and "meta" in node:
                meta = node["meta"]
                if isinstance(meta, dict):
                    for key, value in meta.items():
                        if "hash" in key.lower() and isinstance(value, str):
                            # Try to pair with a model reference
                            inputs = node.get("inputs", {})
                            for ik, iv in inputs.items():
                                if isinstance(iv, str) and "." in iv:
                                    hashes[iv] = value
                                    break

    return hashes


def analyze_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Full analysis of a workflow — nodes, models, hashes."""
    return {
        "node_types": extract_node_types(workflow),
        "model_references": extract_model_references(workflow),
        "hashes": extract_hashes(workflow),
    }
