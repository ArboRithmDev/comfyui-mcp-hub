"""OptionalMergeImages — Merge up to 5 image sources, all optional.

Uses lazy evaluation: only requests inputs that are actually connected.
If no image is provided, silently blocks downstream execution.
If only some inputs are connected, merges only the available images.
"""

import torch
import comfy.utils


class OptionalMergeImages:
    """Merge multiple image sources. All inputs are optional — blocks downstream if none provided."""

    _OPTIONAL_INPUTS = ("image_1", "image_2", "image_3", "image_4", "image_5")

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "method": (["nearest-exact", "bilinear", "area", "bicubic", "lanczos"], {"default": "lanczos"}),
            },
            "optional": {
                "image_1": ("IMAGE", {"lazy": True}),
                "image_2": ("IMAGE", {"lazy": True}),
                "image_3": ("IMAGE", {"lazy": True}),
                "image_4": ("IMAGE", {"lazy": True}),
                "image_5": ("IMAGE", {"lazy": True}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"
    CATEGORY = "image"

    def check_lazy_status(self, method, **kwargs):
        """Only request evaluation of inputs that are not yet resolved."""
        needed = []
        for name in self._OPTIONAL_INPUTS:
            if name not in kwargs:
                # Not connected — skip
                continue
            if kwargs[name] is None:
                # Connected but not yet evaluated — request it
                needed.append(name)
        return needed

    def execute(self, method, **kwargs):
        images = []
        for name in self._OPTIONAL_INPUTS:
            img = kwargs.get(name)
            if img is not None:
                images.append(img)

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
