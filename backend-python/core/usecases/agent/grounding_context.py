# backend-python/core/usecases/agent/grounding_context.py
"""Grounding context helpers for active-page agent turns."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tool_impl import list_text_boxes_for_page
from core.usecases.agent.turn_state import has_visual_grounding_intent
from infra.db.db_store import list_page_filenames, load_page
from infra.images.image_ops import encode_image_data_url, load_volume_image, resize_for_llm

from .grounding_assets import build_page_overlay_data_url


def _truncate(value: str, *, max_chars: int = 120) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def _normalize_grounding_mode(raw_mode: str | None) -> str:
    mode = str(raw_mode or "").strip().lower()
    if mode not in {"full", "lazy"}:
        return "lazy"
    return mode


def should_use_visual_grounding(
    messages: list[dict[str, Any]],
    *,
    grounding_mode_setting: str | None,
) -> bool:
    if _normalize_grounding_mode(grounding_mode_setting) == "full":
        return True
    return has_visual_grounding_intent(messages)


def resolve_active_filename(
    *,
    volume_id: str,
    requested_filename: str | None,
    fallback_filename: str | None,
) -> str | None:
    if requested_filename:
        return requested_filename
    if fallback_filename:
        return fallback_filename
    filenames = list_page_filenames(volume_id)
    if filenames:
        return filenames[0]
    return None


def build_grounding_message(
    *,
    volume_id: str,
    filename: str,
    page_revision: str | None,
    include_images: bool,
    grounding_mode_setting: str | None,
) -> dict[str, Any] | None:
    try:
        page = load_page(volume_id, filename)
    except Exception:
        return None

    text_boxes = list_text_boxes_for_page(page)
    summary_lines = [
        "Current active page grounding:",
        f"- volume_id: {volume_id}",
        f"- filename: {filename}",
        f"- page_revision: {page_revision or 'unknown'}",
        f"- text_boxes: {len(text_boxes)}",
        (
            f"Use list_text_boxes(filename=\"{filename}\") / "
            f"get_text_box_detail(box_id=..., filename=\"{filename}\") "
            "for exact geometry and OCR/translation data."
        ),
    ]

    if _normalize_grounding_mode(grounding_mode_setting) == "full" and text_boxes:
        summary_lines.append("Visible text boxes (first 20):")
        for item in text_boxes[:20]:
            summary_lines.append(
                "  - "
                f"#{item['id']} "
                f"bbox=({int(item['x'])},{int(item['y'])},{int(item['width'])},{int(item['height'])}) "
                f"ocr=\"{_truncate(str(item['text']), max_chars=80)}\" "
                f"tr=\"{_truncate(str(item['translation']), max_chars=80)}\""
            )

    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": "\n".join(summary_lines),
        }
    ]

    if include_images:
        try:
            page_image = resize_for_llm(load_volume_image(volume_id, filename))
            content.append(
                {
                    "type": "input_image",
                    "image_url": encode_image_data_url(page_image),
                    "detail": "high",
                }
            )
        except Exception:
            pass

        try:
            overlay_data_url = build_page_overlay_data_url(
                volume_id=volume_id,
                filename=filename,
                text_boxes=text_boxes,
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": overlay_data_url,
                    "detail": "high",
                }
            )
        except Exception:
            pass

    return {
        "role": "user",
        "content": content,
    }
