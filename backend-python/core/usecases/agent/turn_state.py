# backend-python/core/usecases/agent/turn_state.py
"""Per-turn grounding state and response guard helpers for agent chat."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from infra.db.db_store import load_page
from infra.images.image_ops import get_page_image_path

_PAGE_FILENAME_RE = re.compile(r"\b(\d+\.(?:jpg|jpeg|png|webp))\b", re.IGNORECASE)
_TEXT_BOX_COUNT_RE = re.compile(r"\b(\d+)\s+(?:detected\s+)?text\s+boxes?\b", re.IGNORECASE)


def _coerce_filename(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _latest_user_message_text(messages: list[dict[str, Any]]) -> str:
    for item in reversed(messages):
        role = str(item.get("role") or "").strip().lower()
        if role != "user":
            continue
        text = str(item.get("content") or "").strip()
        if text:
            return text
    return ""


def _is_page_translation_intent(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    markers = (
        "translate this page",
        "translate page",
        "can you translate",
        "please translate",
        "translation of this page",
        "translation for this page",
        "übersetz",
    )
    return any(marker in lowered for marker in markers)


def _is_active_page_focus_intent(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    markers = (
        "this page",
        "current page",
        "on this page",
        "on the current page",
        "translate this page",
        "ocr this page",
        "detect boxes",
        "detect text boxes",
        "run ocr",
        "go to next page",
        "next page",
        "previous page",
        "prev page",
        "go to page",
        "switch page",
    )
    return any(marker in lowered for marker in markers)


def _is_cross_page_fact_query_intent(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    markers = (
        "which page",
        "what page",
        "on which page",
        "on what page",
        "where in",
        "summary so far",
        "recap so far",
        "up to",
        "across pages",
        "earlier page",
        "later page",
        "before that",
        "after that",
    )
    return any(marker in lowered for marker in markers)


def _count_text_boxes(page: dict[str, Any]) -> int:
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    if not isinstance(raw_boxes, list):
        return 0
    count = 0
    for box in raw_boxes:
        if not isinstance(box, dict):
            continue
        if str(box.get("type") or "").strip().lower() != "text":
            continue
        if int(box.get("id") or 0) <= 0:
            continue
        count += 1
    return count


def _normalize_box_for_revision(box: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(box.get("id") or 0),
        "type": str(box.get("type") or "").strip().lower(),
        "order_index": int(box.get("orderIndex") or 0),
        "x": round(float(box.get("x") or 0.0), 3),
        "y": round(float(box.get("y") or 0.0), 3),
        "width": round(float(box.get("width") or 0.0), 3),
        "height": round(float(box.get("height") or 0.0), 3),
        "text": str(box.get("text") or "").strip(),
        "translation": str(box.get("translation") or "").strip(),
    }


def _compute_page_revision(
    *,
    volume_id: str,
    filename: str,
    page: dict[str, Any],
) -> str:
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    boxes: list[dict[str, Any]] = []
    if isinstance(raw_boxes, list):
        for item in raw_boxes:
            if isinstance(item, dict):
                boxes.append(_normalize_box_for_revision(item))
    boxes.sort(key=lambda row: (row["order_index"], row["id"]))

    payload: dict[str, Any] = {
        "volume_id": volume_id,
        "filename": filename,
        "boxes": boxes,
    }

    try:
        image_path = get_page_image_path(volume_id, filename)
        stat = image_path.stat()
        payload["image_mtime_ns"] = int(stat.st_mtime_ns)
        payload["image_size"] = int(stat.st_size)
    except Exception:
        pass

    normalized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def get_active_page_state(
    *,
    volume_id: str,
    current_filename: str | None,
) -> tuple[int | None, str | None]:
    resolved = _coerce_filename(current_filename)
    if not volume_id or not resolved:
        return None, None
    try:
        page = load_page(volume_id, resolved)
    except Exception:
        return None, None
    return _count_text_boxes(page), _compute_page_revision(
        volume_id=volume_id,
        filename=resolved,
        page=page,
    )


def get_active_page_text_box_count(
    *,
    volume_id: str,
    current_filename: str | None,
) -> int | None:
    count, _ = get_active_page_state(
        volume_id=volume_id,
        current_filename=current_filename,
    )
    return count


def get_active_page_revision(
    *,
    volume_id: str,
    current_filename: str | None,
) -> str | None:
    _, revision = get_active_page_state(
        volume_id=volume_id,
        current_filename=current_filename,
    )
    return revision


def no_text_boxes_reply(filename: str) -> str:
    return (
        f"No text boxes found on {filename}. "
        "I cannot translate this page until boxes exist. "
        "Run text box detection on this page (or switch to another page), then ask again."
    )


def should_force_no_text_reply(
    *,
    messages: list[dict[str, Any]],
    active_filename: str | None,
    text_box_count: int | None,
) -> bool:
    if _coerce_filename(active_filename) is None:
        return False
    if text_box_count != 0:
        return False
    latest_user_text = _latest_user_message_text(messages)
    return _is_page_translation_intent(latest_user_text)


def build_turn_state_message(
    *,
    volume_id: str,
    active_filename: str | None,
    text_box_count: int | None,
    page_revision: str | None = None,
) -> dict[str, Any]:
    filename_value = _coerce_filename(active_filename) or "none"
    box_count_value = "unknown" if text_box_count is None else str(int(text_box_count))
    revision_value = str(page_revision or "").strip() or "unknown"
    lines = [
        "Authoritative turn state (must not be contradicted):",
        f"- active_volume_id: {volume_id or 'none'}",
        f"- active_filename: {filename_value}",
        f"- active_text_box_count: {box_count_value}",
        f"- active_page_revision: {revision_value}",
        "Use this turn state for any page-specific claims.",
    ]
    return {
        "role": "system",
        "content": [{"type": "input_text", "text": "\n".join(lines)}],
    }


def has_visual_grounding_intent(messages: list[dict[str, Any]]) -> bool:
    text = _latest_user_message_text(messages).lower()
    if not text:
        return False
    markers = (
        "from the image",
        "from image",
        "what do you see",
        "look at",
        "visual",
        "appearance",
        "panel",
        "art",
        "draw",
        "boy or girl",
        "gender",
        "image",
        "picture",
        "bild",
    )
    return any(marker in text for marker in markers)


def sanitize_agent_reply_text(
    *,
    response_text: str,
    messages: list[dict[str, Any]],
    active_filename: str | None,
    active_text_box_count: int | None,
) -> tuple[str, str | None]:
    text = str(response_text or "").strip()
    resolved_filename = _coerce_filename(active_filename)

    if not text:
        if should_force_no_text_reply(
            messages=messages,
            active_filename=resolved_filename,
            text_box_count=active_text_box_count,
        ) and resolved_filename:
            return no_text_boxes_reply(resolved_filename), "empty_output_no_boxes"
        if resolved_filename:
            return (
                f"I couldn't generate a response for {resolved_filename}. Please retry.",
                "empty_output",
            )
        return "I couldn't generate a response. Please retry.", "empty_output"

    if not resolved_filename:
        return text, None

    latest_user_text = _latest_user_message_text(messages)
    enforce_active_page_consistency = _is_active_page_focus_intent(latest_user_text) and not (
        _is_cross_page_fact_query_intent(latest_user_text)
    )

    lowered = text.lower()
    active_filename_lower = resolved_filename.lower()
    page_refs = {m.group(1).lower() for m in _PAGE_FILENAME_RE.finditer(lowered)}
    page_refs.discard(active_filename_lower)

    box_count_mismatch = False
    if active_text_box_count is not None:
        for match in _TEXT_BOX_COUNT_RE.finditer(lowered):
            if int(match.group(1)) != int(active_text_box_count):
                box_count_mismatch = True
                break

    if enforce_active_page_consistency and (page_refs or box_count_mismatch):
        count_text = (
            f" It currently has {int(active_text_box_count)} detected text boxes."
            if active_text_box_count is not None
            else ""
        )
        if active_text_box_count == 0:
            count_text += " No text boxes are available on this page right now."
        return (
            f"I may have mixed stale page context. Active page is {resolved_filename}.{count_text}"
            " I can re-check this page with current grounding/tools if you want.",
            "stale_context",
        )

    return text, None
