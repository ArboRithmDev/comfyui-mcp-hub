"""OptionalMergeImages — Merge image sources, filtering out empty signals.

Works with OptionalLoadImage: images that are 1x1 (empty signal) are
automatically ignored. If all inputs are empty/missing, blocks downstream.
"""

import torch
import comfy.utils

from .optional_load_image import EMPTY_SIGNAL_SIZE


def _is_empty_signal(img):
    """Check if an image tensor is the 1x1 empty signal from OptionalLoadImage."""
    if img is None:
        return True
    # After resize nodes, the image might still be very small (1x1 or similar)
    return img.shape[1] <= EMPTY_SIGNAL_SIZE and img.shape[2] <= EMPTY_SIGNAL_SIZE


class OptionalMergeImages:
    """Merge multiple image sources, ignoring empty signals from OptionalLoadImage.

    All inputs are optional. Empty signals (1x1 images) are filtered out.
    If no real image remains, silently blocks downstream execution.
    """

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
        # Filter out None and empty signal images
        images = [
            img for img in (image_1, image_2, image_3, image_4, image_5)
            if not _is_empty_signal(img)
        ]

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
