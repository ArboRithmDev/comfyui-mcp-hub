"""OptionalMergeImages — Merge up to 5 image sources, all optional.

If no image is connected or all inputs are blocked, silently blocks downstream.
If only some inputs are connected, merges only the available images.
"""

import torch
import comfy.utils


class OptionalMergeImages:
    """Merge multiple image sources. All inputs are optional — blocks downstream if none provided."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "method": (["nearest-exact", "bilinear", "area", "bicubic", "lanczos"], {"default": "lanczos"}),
            },
            "optional": {
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
                "image_3": ("IMAGE",),
                "image_4": ("IMAGE",),
                "image_5": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"
    CATEGORY = "image"

    def execute(self, method, image_1=None, image_2=None, image_3=None, image_4=None, image_5=None):
        images = [img for img in (image_1, image_2, image_3, image_4, image_5) if img is not None]

        if not images:
            from comfy_execution.graph_utils import ExecutionBlocker
            return (ExecutionBlocker(None),)

        out = images[0]
        for img in images[1:]:
            if out.shape[1:] != img.shape[1:]:
                img = comfy.utils.common_upscale(
                    img.movedim(-1, 1), out.shape[2], out.shape[1], method, "center"
                ).movedim(1, -1)
            out = torch.cat((out, img), dim=0)

        return (out,)
