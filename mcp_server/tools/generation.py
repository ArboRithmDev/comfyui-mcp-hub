"""Generation tools — high-level shortcuts for common generation tasks."""

from __future__ import annotations

import base64
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..comfyui_client import ComfyUIClient
from ..config import get_instance_url, load_config


def _build_txt2img_workflow(
    prompt: str,
    negative_prompt: str = "",
    model: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int = -1,
) -> dict[str, Any]:
    """Build a standard txt2img workflow in ComfyUI API format."""
    if seed < 0:
        import random
        seed = random.randint(0, 2**32 - 1)

    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": model},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["1", 1]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"images": ["6", 0], "filename_prefix": "mcp_hub"},
        },
    }


def _build_img2img_workflow(
    prompt: str,
    image_path: str,
    negative_prompt: str = "",
    model: str = "",
    denoise: float = 0.75,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int = -1,
) -> dict[str, Any]:
    """Build an img2img workflow."""
    if seed < 0:
        import random
        seed = random.randint(0, 2**32 - 1)

    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": model},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["1", 1]},
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": image_path},
        },
        "5": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["4", 0], "vae": ["1", 2]},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": denoise,
            },
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "mcp_hub_img2img"},
        },
    }


def register(mcp: FastMCP) -> None:
    """Register generation tools on the MCP server."""

    @mcp.tool()
    async def generate_image(
        prompt: str,
        model: str = "",
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        cfg: float = 7.0,
        seed: int = -1,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Generate an image from a text prompt (txt2img).

        Args:
            prompt: The positive text prompt describing the image.
            model: Checkpoint model name. If empty, uses the first available.
            negative_prompt: Things to avoid in the image.
            width: Image width in pixels.
            height: Image height in pixels.
            steps: Number of sampling steps.
            cfg: Classifier-free guidance scale.
            seed: Random seed (-1 for random).
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            if not model:
                info = await client.get_object_info("CheckpointLoaderSimple")
                models = info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
                if models:
                    model = models[0]
                else:
                    return {"error": "No checkpoint models found"}

            workflow = _build_txt2img_workflow(
                prompt=prompt, negative_prompt=negative_prompt,
                model=model, width=width, height=height,
                steps=steps, cfg=cfg, seed=seed,
            )
            client_id = str(uuid.uuid4())
            result = await client.queue_prompt(workflow, client_id=client_id)
            prompt_id = result.get("prompt_id", "")

            # Wait for completion
            history = await client.watch_prompt(prompt_id, client_id, timeout=300)
            if "error" in history:
                return history

            # Extract output images
            outputs = history.get(prompt_id, {}).get("outputs", {})
            images = []
            for _node_id, node_out in outputs.items():
                for item in node_out.get("images", []):
                    images.append({
                        "filename": item["filename"],
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                    })
            return {"status": "completed", "prompt_id": prompt_id, "images": images}
        finally:
            await client.close()

    @mcp.tool()
    async def transform_image(
        prompt: str,
        image_path: str,
        model: str = "",
        negative_prompt: str = "",
        denoise: float = 0.75,
        steps: int = 20,
        cfg: float = 7.0,
        seed: int = -1,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Transform an existing image using a text prompt (img2img).

        Args:
            prompt: The positive text prompt.
            image_path: Name of the image file in ComfyUI's input directory.
            model: Checkpoint model name. If empty, uses the first available.
            negative_prompt: Things to avoid.
            denoise: Denoising strength (0.0 = no change, 1.0 = full regeneration).
            steps: Number of sampling steps.
            cfg: Classifier-free guidance scale.
            seed: Random seed (-1 for random).
            instance: Target ComfyUI instance name.
        """
        config = load_config()
        client = ComfyUIClient(get_instance_url(config, instance))
        try:
            if not model:
                info = await client.get_object_info("CheckpointLoaderSimple")
                models = info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
                if models:
                    model = models[0]
                else:
                    return {"error": "No checkpoint models found"}

            workflow = _build_img2img_workflow(
                prompt=prompt, image_path=image_path,
                negative_prompt=negative_prompt, model=model,
                denoise=denoise, steps=steps, cfg=cfg, seed=seed,
            )
            client_id = str(uuid.uuid4())
            result = await client.queue_prompt(workflow, client_id=client_id)
            prompt_id = result.get("prompt_id", "")

            history = await client.watch_prompt(prompt_id, client_id, timeout=300)
            if "error" in history:
                return history

            outputs = history.get(prompt_id, {}).get("outputs", {})
            images = []
            for _node_id, node_out in outputs.items():
                for item in node_out.get("images", []):
                    images.append({
                        "filename": item["filename"],
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                    })
            return {"status": "completed", "prompt_id": prompt_id, "images": images}
        finally:
            await client.close()

    @mcp.tool()
    async def generate_video(
        prompt: str,
        model: str = "",
        frames: int = 16,
        fps: int = 8,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg: float = 7.0,
        seed: int = -1,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Generate a video from a text prompt. Requires appropriate video model and nodes installed.

        Args:
            prompt: Text prompt describing the video.
            model: Video model name.
            frames: Number of frames to generate.
            fps: Frames per second for output.
            width: Frame width in pixels.
            height: Frame height in pixels.
            steps: Number of sampling steps.
            cfg: Classifier-free guidance scale.
            seed: Random seed (-1 for random).
            instance: Target ComfyUI instance name.
        """
        return {
            "status": "not_implemented",
            "message": "Video generation requires custom workflow. Use execute_workflow with a video-specific workflow JSON instead.",
            "hint": "Use list_nodes(search='video') to discover available video nodes.",
        }

    @mcp.tool()
    async def generate_audio(
        prompt: str,
        model: str = "",
        duration: float = 5.0,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Generate audio from a text prompt. Requires appropriate audio model and nodes installed.

        Args:
            prompt: Text prompt describing the audio.
            model: Audio model name.
            duration: Duration in seconds.
            instance: Target ComfyUI instance name.
        """
        return {
            "status": "not_implemented",
            "message": "Audio generation requires custom workflow. Use execute_workflow with an audio-specific workflow JSON instead.",
            "hint": "Use list_nodes(search='audio') to discover available audio nodes.",
        }
