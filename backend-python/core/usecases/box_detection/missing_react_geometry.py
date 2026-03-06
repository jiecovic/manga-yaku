# backend-python/core/usecases/box_detection/missing_react_geometry.py
"""Experimental geometry and text helpers for missing-box ReAct."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from PIL import Image, ImageDraw

from infra.images.image_ops import encode_image_data_url, resize_for_llm

from .missing_react_config import (
    _HINT_DESCRIPTION_MARKERS,
    _MAX_BOX_AREA_RATIO,
    _MIN_BOX_EDGE_PX,
)


def _list_existing_text_boxes(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    if not isinstance(raw_boxes, list):
        return []

    out: list[dict[str, Any]] = []
    for item in raw_boxes:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "text":
            continue
        width = float(item.get("width") or 0.0)
        height = float(item.get("height") or 0.0)
        if width <= 0 or height <= 0:
            continue
        out.append(
            {
                "id": int(item.get("id") or 0),
                "x": float(item.get("x") or 0.0),
                "y": float(item.get("y") or 0.0),
                "width": width,
                "height": height,
                "text": str(item.get("text") or "").strip(),
            }
        )
    return out


def _box_area(box: dict[str, float]) -> float:
    return max(0.0, float(box["width"])) * max(0.0, float(box["height"]))


def _box_iou(a: dict[str, float], b: dict[str, float]) -> float:
    ax1 = float(a["x"])
    ay1 = float(a["y"])
    ax2 = ax1 + max(0.0, float(a["width"]))
    ay2 = ay1 + max(0.0, float(a["height"]))

    bx1 = float(b["x"])
    by1 = float(b["y"])
    bx2 = bx1 + max(0.0, float(b["width"]))
    by2 = by1 + max(0.0, float(b["height"]))

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    union = _box_area(a) + _box_area(b) - inter
    if union <= 0:
        return 0.0
    return inter / union


def _is_cjk_or_kana(char: str) -> bool:
    code = ord(char)
    return (
        (0x3040 <= code <= 0x30FF)
        or (0x3400 <= code <= 0x4DBF)
        or (0x4E00 <= code <= 0x9FFF)
        or (0xF900 <= code <= 0xFAFF)
    )


def _is_useful_observed_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False

    meaningful = [ch for ch in compact if ch.isalnum() or _is_cjk_or_kana(ch)]
    if len(meaningful) < 2:
        return False

    if compact.startswith(("…", "...")) or compact.endswith(("…", "...")):
        if len(meaningful) < 4:
            return False

    ratio = len(meaningful) / max(1, len(compact))
    return ratio >= 0.45


def _hint_looks_like_literal_text(hint_text: str) -> bool:
    hint = str(hint_text or "").strip()
    if not hint:
        return False
    if len(hint) > 48:
        return False
    lowered = hint.lower()
    if any(marker in lowered for marker in _HINT_DESCRIPTION_MARKERS):
        return False
    if any(token in hint for token in ("(", ")", ":", "[", "]")):
        return False
    return True


def _normalize_compare_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    compact = re.sub(r"\s+", "", normalized)
    return "".join(ch for ch in compact if ch.isalnum() or _is_cjk_or_kana(ch))


def _observed_matches_hint(hint_text: str, observed_text: str) -> bool:
    hint = _normalize_compare_text(hint_text)
    observed = _normalize_compare_text(observed_text)
    if not hint or not observed:
        return False
    if hint in observed or observed in hint:
        return True
    overlap = sum(1 for ch in hint if ch in observed)
    ratio = overlap / max(1, len(hint))
    return ratio >= 0.6


def _normalize_candidate_bbox(
    *,
    x: Any,
    y: Any,
    width: Any,
    height: Any,
    image_w: int,
    image_h: int,
) -> dict[str, float] | None:
    try:
        left = float(x)
        top = float(y)
        box_w = float(width)
        box_h = float(height)
    except (TypeError, ValueError):
        return None

    if box_w <= 0 or box_h <= 0:
        return None

    left = max(0.0, min(left, float(image_w - 1)))
    top = max(0.0, min(top, float(image_h - 1)))
    right = max(left + 1.0, min(float(image_w), left + box_w))
    bottom = max(top + 1.0, min(float(image_h), top + box_h))
    norm_w = right - left
    norm_h = bottom - top
    if norm_w < _MIN_BOX_EDGE_PX or norm_h < _MIN_BOX_EDGE_PX:
        return None
    if norm_w * norm_h > float(image_w * image_h) * _MAX_BOX_AREA_RATIO:
        return None
    return {
        "x": left,
        "y": top,
        "width": norm_w,
        "height": norm_h,
    }


def _retry_candidate_box(
    initial_box: dict[str, float],
    *,
    attempt_index: int,
    image_w: int,
    image_h: int,
) -> dict[str, float]:
    # Experimental fallback search pattern for the prototype loop.
    retry_pattern: list[tuple[float, float, float]] = [
        (0.0, 0.0, 1.00),
        (0.0, 0.0, 1.14),
        (-0.20, 0.0, 1.10),
        (0.20, 0.0, 1.10),
        (0.0, -0.20, 1.10),
        (0.0, 0.20, 1.10),
        (-0.24, -0.12, 1.18),
        (0.24, -0.12, 1.18),
        (-0.24, 0.12, 1.18),
        (0.24, 0.12, 1.18),
    ]
    idx = max(1, int(attempt_index))
    if idx <= len(retry_pattern):
        shift_x_ratio, shift_y_ratio, scale = retry_pattern[idx - 1]
    else:
        shift_x_ratio, shift_y_ratio, scale = 0.0, 0.0, 1.35

    base_w = max(_MIN_BOX_EDGE_PX, float(initial_box["width"]))
    base_h = max(_MIN_BOX_EDGE_PX, float(initial_box["height"]))
    center_x = float(initial_box["x"]) + base_w / 2.0 + base_w * shift_x_ratio
    center_y = float(initial_box["y"]) + base_h / 2.0 + base_h * shift_y_ratio
    next_w = min(float(image_w), base_w * scale)
    next_h = min(float(image_h), base_h * scale)
    next_x = center_x - next_w / 2.0
    next_y = center_y - next_h / 2.0
    normalized = _normalize_candidate_bbox(
        x=next_x,
        y=next_y,
        width=next_w,
        height=next_h,
        image_w=image_w,
        image_h=image_h,
    )
    return normalized or dict(initial_box)


def _to_resized_box(box: dict[str, float], *, scale_x: float, scale_y: float) -> dict[str, float]:
    return {
        "x": float(box["x"]) / scale_x,
        "y": float(box["y"]) / scale_y,
        "width": float(box["width"]) / scale_x,
        "height": float(box["height"]) / scale_y,
    }


def _to_original_box(box: dict[str, float], *, scale_x: float, scale_y: float) -> dict[str, float]:
    return {
        "x": float(box["x"]) * scale_x,
        "y": float(box["y"]) * scale_y,
        "width": float(box["width"]) * scale_x,
        "height": float(box["height"]) * scale_y,
    }


def _encode_crop_data_url(
    *,
    image: Image.Image,
    box: dict[str, float],
    padding_px: int,
) -> str:
    pad = max(0, int(padding_px))
    left = max(0, int(float(box["x"])) - pad)
    top = max(0, int(float(box["y"])) - pad)
    right = min(image.width, int(float(box["x"]) + float(box["width"])) + pad)
    bottom = min(image.height, int(float(box["y"]) + float(box["height"])) + pad)
    if right <= left or bottom <= top:
        raise ValueError("Invalid crop bounds")
    crop = image.crop((left, top, right, bottom))
    crop = resize_for_llm(crop, max_side=1024)
    return encode_image_data_url(crop, quality=82)


def _encode_box_overlay_data_url(
    *,
    image: Image.Image,
    current_box: dict[str, float],
    max_side: int = 1536,
) -> str:
    base = resize_for_llm(image.copy(), max_side=max_side)
    draw = ImageDraw.Draw(base)

    scale_x = base.width / max(image.width, 1)
    scale_y = base.height / max(image.height, 1)

    def _draw_box(box: dict[str, float], *, color: tuple[int, int, int], width: int) -> None:
        x = max(0.0, float(box["x"])) * scale_x
        y = max(0.0, float(box["y"])) * scale_y
        w = max(0.0, float(box["width"])) * scale_x
        h = max(0.0, float(box["height"])) * scale_y
        x2 = min(float(base.width - 1), x + w)
        y2 = min(float(base.height - 1), y + h)
        if x2 <= x or y2 <= y:
            return
        draw.rectangle((x, y, x2, y2), outline=color, width=width)

    _draw_box(current_box, color=(255, 80, 80), width=4)

    return encode_image_data_url(base, quality=82)
