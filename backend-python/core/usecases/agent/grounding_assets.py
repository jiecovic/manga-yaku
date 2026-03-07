# backend-python/core/usecases/agent/grounding_assets.py
"""Helpers for building visual grounding assets for agent turns."""

from __future__ import annotations

from typing import Any

from PIL import ImageDraw

from infra.images.image_ops import encode_image_data_url, load_volume_image, resize_for_llm


def build_page_overlay_data_url(
    *,
    volume_id: str,
    filename: str,
    text_boxes: list[dict[str, Any]],
) -> str:
    original = load_volume_image(volume_id, filename)
    overlay = resize_for_llm(original)
    draw = ImageDraw.Draw(overlay)

    scale_x = overlay.width / max(original.width, 1)
    scale_y = overlay.height / max(original.height, 1)

    for item in text_boxes:
        x = max(0.0, float(item["x"])) * scale_x
        y = max(0.0, float(item["y"])) * scale_y
        w = max(0.0, float(item["width"])) * scale_x
        h = max(0.0, float(item["height"])) * scale_y
        x2 = min(float(overlay.width - 1), x + w)
        y2 = min(float(overlay.height - 1), y + h)
        if x2 <= x or y2 <= y:
            continue

        draw.rectangle((x, y, x2, y2), outline=(255, 80, 80), width=3)
        label = f"#{int(item['id'])}"
        tx = int(max(0, x + 2))
        ty = int(max(0, y - 14))
        label_w = max(24, 8 * len(label))
        draw.rectangle((tx, ty, tx + label_w, ty + 14), fill=(0, 0, 0))
        draw.text((tx + 2, ty + 1), label, fill=(255, 255, 0))

    return encode_image_data_url(overlay)
