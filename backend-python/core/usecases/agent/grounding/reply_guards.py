# backend-python/core/usecases/agent/grounding/reply_guards.py
"""Reply guard and intent helpers for agent grounding."""

from __future__ import annotations

import re
from typing import Any

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


def no_text_boxes_reply(filename: str) -> str:
    return (
        f"No text boxes found on {filename}. "
        "I cannot translate this page until boxes exist. "
        "Run text box detection on this page (or switch to another page), then ask again."
    )


def stale_context_warning_message(
    *,
    active_filename: str | None,
    active_text_box_count: int | None,
) -> str:
    resolved_filename = _coerce_filename(active_filename) or "unknown"
    count_text = (
        f"{int(active_text_box_count)} detected text boxes"
        if active_text_box_count is not None
        else "an unknown text-box count"
    )
    return (
        "Warning: the reply may mention stale page facts; "
        f"current active page is {resolved_filename} with {count_text}."
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
        if (
            should_force_no_text_reply(
                messages=messages,
                active_filename=resolved_filename,
                text_box_count=active_text_box_count,
            )
            and resolved_filename
        ):
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
        return text, "stale_context_warning"

    return text, None
