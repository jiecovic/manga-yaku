# backend-python/infra/images/image_ops.py
"""Image loading, cropping, and conversion helpers."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from config import VOLUMES_ROOT, safe_join


def get_page_image_path(volume_id: str, filename: str) -> Path:
    return safe_join(VOLUMES_ROOT, volume_id, filename)


def crop_volume_image(
        volume_id: str,
        filename: str,
        x: float,
        y: float,
        width: float,
        height: float,
) -> Image.Image:
    """
    Load the page image for (volume_id, filename) and return a cropped PIL.Image.
    """
    img_path = get_page_image_path(volume_id, filename)
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")

    im = Image.open(img_path).convert("RGB")

    left = max(0, int(x))
    top = max(0, int(y))
    right = min(im.width, int(x + width))
    bottom = min(im.height, int(y + height))

    if right <= left or bottom <= top:
        raise ValueError("Invalid crop region")

    return im.crop((left, top, right, bottom))


def load_volume_image(volume_id: str, filename: str) -> Image.Image:
    """
    Load the page image and return a PIL.Image in RGB.
    """
    img_path = get_page_image_path(volume_id, filename)
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")
    return Image.open(img_path).convert("RGB")


def resize_for_llm(
    image: Image.Image,
    *,
    max_side: int = 1536,
) -> Image.Image:
    """
    Downscale the image so the longest edge is <= max_side.
    Never upscales.
    """
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    target = (int(width * scale), int(height * scale))
    return image.resize(target, Image.LANCZOS)


def encode_image_data_url(
    image: Image.Image,
    *,
    quality: int = 80,
    image_format: str = "JPEG",
) -> str:
    """
    Encode a PIL image into a data URL suitable for model input.
    """
    import base64
    import io

    buffer = io.BytesIO()
    image.save(buffer, format=image_format, quality=quality)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/{image_format.lower()};base64,{encoded}"


