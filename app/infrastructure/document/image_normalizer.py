"""Image normalization, resizing, and blank page detection utilities.

Provides:
- normalize_alpha_to_white: Converts transparent PNGs onto a solid white canvas.
- guard_max_dimension: Downscales high-resolution images to a maximum bounding box.
- is_blank_page: Detects whether an image/page is empty (e.g. duplex scanner blanks).
"""

from __future__ import annotations

import io
import logging
from typing import Union

from PIL import Image

logger = logging.getLogger("knowlayer.ingestion.image")


def normalize_alpha_to_white(image_input: Union[bytes, Image.Image]) -> tuple[bytes, Image.Image]:
    """Ensure image is in RGB format with transparent pixels composited onto white.

    Returns:
        (image_bytes, PIL.Image) in RGB format.
    """
    if isinstance(image_input, bytes):
        image = Image.open(io.BytesIO(image_input))
    else:
        image = image_input

    # Check for transparency (RGBA, LA, or paletted with transparency info)
    has_alpha = (
        image.mode in ("RGBA", "LA")
        or (image.mode == "P" and "transparency" in image.info)
    )

    if has_alpha:
        # Convert to RGBA first to handle palette transparency reliably
        rgba_image = image.convert("RGBA")
        background = Image.new("RGB", rgba_image.size, (255, 255, 255))
        background.paste(rgba_image, mask=rgba_image.split()[3])
        normalized = background
    else:
        normalized = image.convert("RGB")

    buf = io.BytesIO()
    normalized.save(buf, format="PNG")
    return buf.getvalue(), normalized


def guard_max_dimension(
    image_input: Union[bytes, Image.Image],
    max_dim: int = 1024,
) -> tuple[bytes, Image.Image]:
    """Constrain maximum width or height to max_dim using high-quality LANCZOS resampling.

    Preserves exact aspect ratio. If both dimensions are <= max_dim, returns unmodified.

    Returns:
        (image_bytes, PIL.Image) in RGB format.
    """
    if isinstance(image_input, bytes):
        image = Image.open(io.BytesIO(image_input))
    else:
        image = image_input

    width, height = image.size
    longest_edge = max(width, height)

    if longest_edge <= max_dim:
        if isinstance(image_input, bytes) and image.mode == "RGB":
            return image_input, image
        buf = io.BytesIO()
        rgb_img = image.convert("RGB")
        rgb_img.save(buf, format="PNG")
        return buf.getvalue(), rgb_img

    scale = max_dim / float(longest_edge)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))

    logger.debug(
        "resizing image from (%d, %d) to (%d, %d) with LANCZOS guard",
        width,
        height,
        new_width,
        new_height,
    )

    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS).convert("RGB")
    buf = io.BytesIO()
    resized.save(buf, format="PNG")
    return buf.getvalue(), resized


def is_blank_page(
    image_input: Union[bytes, Image.Image],
    dark_threshold: int = 180,
    max_dark_pixels: int = 60,
) -> bool:
    """Detect if an image is a blank sheet of paper (e.g. duplex scanner scan).

    Args:
        image_input: Image bytes or PIL Image.
        dark_threshold: Pixel brightness below which a pixel is considered 'ink' (0-255).
        max_dark_pixels: Maximum number of dark pixels allowed to still be considered blank
                         (absorbs scanner dust, marginal paper noise).
    """
    if isinstance(image_input, bytes):
        image = Image.open(io.BytesIO(image_input))
    else:
        image = image_input

    gray = image.convert("L")
    min_val, max_val = gray.getextrema()
    if min_val >= dark_threshold:
        return True

    # Sample down large pages for ultra-fast threshold checking
    if gray.width > 600 or gray.height > 600:
        gray = gray.resize((300, int(300 * gray.height / gray.width)), Image.Resampling.NEAREST)

    pixels = (
        gray.get_flattened_data()
        if hasattr(gray, "get_flattened_data")
        else gray.getdata()
    )
    dark_count = 0
    for pixel in pixels:
        if pixel < dark_threshold:
            dark_count += 1
            if dark_count > max_dark_pixels:
                return False

    return True
