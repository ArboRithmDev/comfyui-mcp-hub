"""OptionalLoadImage — Load an image or emit a 1x1 empty signal for downstream filtering."""

import os
import hashlib

import numpy as np
import torch
from PIL import Image, ImageOps, ImageSequence

import folder_paths
import node_helpers
import comfy.model_management

# Sentinel size used to signal "no image" to downstream nodes.
# Must be large enough to survive resize/sharpen/padding operations (min 8px).
# OptionalMergeImages filters these out automatically.
EMPTY_SIGNAL_SIZE = 8


def _make_empty_signal():
    """Return a 1x1 black image and mask as the 'no image' signal."""
    image = torch.zeros((1, EMPTY_SIGNAL_SIZE, EMPTY_SIGNAL_SIZE, 3), dtype=torch.float32)
    mask = torch.zeros((1, EMPTY_SIGNAL_SIZE, EMPTY_SIGNAL_SIZE), dtype=torch.float32)
    return (image, mask)


class OptionalLoadImage:
    """Like LoadImage, but with a 'none' option.

    When 'none' is selected (or no valid image), outputs a 1x1 black image
    as a signal. This passes safely through intermediate nodes (resize, etc.).
    Use with 'Merge Images (Optional)' which filters these signals automatically.
    """

    @classmethod
    def INPUT_TYPES(s):
        input_dir = folder_paths.get_input_directory()
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        files = folder_paths.filter_files_content_types(files, ["image"])
        return {
            "required": {
                "image": (["none"] + sorted(files), {"image_upload": True}),
            },
        }

    CATEGORY = "image"
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    def load_image(self, image):
        if image == "none" or not image:
            return _make_empty_signal()

        image_path = folder_paths.get_annotated_filepath(image)

        if not os.path.isfile(image_path):
            return _make_empty_signal()

        img = node_helpers.pillow(Image.open, image_path)

        output_images = []
        output_masks = []
        w, h = None, None
        dtype = comfy.model_management.intermediate_dtype()

        for i in ImageSequence.Iterator(img):
            i = node_helpers.pillow(ImageOps.exif_transpose, i)

            if i.mode == "I":
                i = i.point(lambda x: x * (1 / 255))
            image_rgb = i.convert("RGB")

            if len(output_images) == 0:
                w = image_rgb.size[0]
                h = image_rgb.size[1]

            if image_rgb.size[0] != w or image_rgb.size[1] != h:
                continue

            arr = np.array(image_rgb).astype(np.float32) / 255.0
            tensor = torch.from_numpy(arr)[None,]

            if "A" in i.getbands():
                mask = np.array(i.getchannel("A")).astype(np.float32) / 255.0
                mask = 1.0 - torch.from_numpy(mask)
            elif i.mode == "P" and "transparency" in i.info:
                mask = np.array(i.convert("RGBA").getchannel("A")).astype(np.float32) / 255.0
                mask = 1.0 - torch.from_numpy(mask)
            else:
                mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")

            output_images.append(tensor.to(dtype=dtype))
            output_masks.append(mask.unsqueeze(0).to(dtype=dtype))

            if img.format == "MPO":
                break

        if len(output_images) > 1:
            output_image = torch.cat(output_images, dim=0)
            output_mask = torch.cat(output_masks, dim=0)
        else:
            output_image = output_images[0]
            output_mask = output_masks[0]

        return (output_image, output_mask)

    @classmethod
    def IS_CHANGED(s, image):
        if image == "none" or not image:
            return "none"
        image_path = folder_paths.get_annotated_filepath(image)
        if not os.path.isfile(image_path):
            return "none"
        m = hashlib.sha256()
        with open(image_path, "rb") as f:
            m.update(f.read())
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(s, image):
        if image == "none" or not image:
            return True
        if not folder_paths.exists_annotated_filepath(image):
            return "Invalid image file: {}".format(image)
        return True
