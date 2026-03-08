# backend-python/core/usecases/agent/tools/boxes.py
"""Page text-box read and write helpers for agent tools."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.grounding.turn_state import build_page_state_snapshot
from core.usecases.agent.tools.shared import (
    find_text_box_by_id,
    list_text_boxes_for_page,
    resolve_active_page_filename,
    resolve_read_page_filename,
)
from infra.db.store_boxes import (
    set_box_note_by_id,
    set_box_ocr_text_by_id,
    set_box_translation_by_id,
)
from infra.db.store_volume_page import list_page_filenames, load_page


def list_text_boxes_tool(
    *,
    volume_id: str,
    filename: str | None,
    active_filename: str | None = None,
    limit: int = 300,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename, error = resolve_read_page_filename(
        volume_id=volume_id,
        filename=filename,
        active_filename=active_filename,
    )
    if error is not None or resolved_filename is None:
        return error or {"error": "filename resolution failed", "volume_id": volume_id}

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    safe_limit = max(1, min(int(limit), 500))
    ocr_filled_count = sum(1 for box in text_boxes if str(box.get("text") or "").strip())
    translated_count = sum(1 for box in text_boxes if str(box.get("translation") or "").strip())
    untranslated_box_ids = [
        int(box.get("id") or 0)
        for box in text_boxes
        if str(box.get("text") or "").strip() and not str(box.get("translation") or "").strip()
    ]
    return {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "total": len(text_boxes),
        "ocr_filled_count": ocr_filled_count,
        "translated_count": translated_count,
        "untranslated_count": max(0, ocr_filled_count - translated_count),
        "untranslated_box_ids": untranslated_box_ids[:20],
        "boxes": text_boxes[:safe_limit],
    }


def get_text_box_detail_tool(
    *,
    volume_id: str,
    box_id: int,
    filename: str | None,
    active_filename: str | None = None,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename, error = resolve_read_page_filename(
        volume_id=volume_id,
        filename=filename,
        active_filename=active_filename,
    )
    if error is not None or resolved_filename is None:
        return error or {"error": "filename resolution failed", "volume_id": volume_id}

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    target = find_text_box_by_id(text_boxes, int(box_id))
    if target is None:
        return {
            "error": f"Text box {int(box_id)} not found",
            "volume_id": volume_id,
            "filename": resolved_filename,
        }
    return {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "box": target,
    }


def update_text_box_fields_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    box_id: int,
    filename: str | None,
    text: str | None = None,
    translation: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}
    if text is None and translation is None and note is None:
        return {"error": "At least one of text, translation, or note is required"}

    resolved_filename, error = resolve_active_page_filename(
        volume_id=volume_id,
        filename=filename,
        active_filename=active_filename,
        action_label="Writes",
    )
    if error is not None or resolved_filename is None:
        return error or {"error": "filename resolution failed", "volume_id": volume_id}

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    existing = find_text_box_by_id(text_boxes, int(box_id))
    if existing is None:
        return {
            "error": f"Text box {int(box_id)} not found",
            "volume_id": volume_id,
            "filename": resolved_filename,
        }

    if text is not None:
        set_box_ocr_text_by_id(volume_id, resolved_filename, box_id=int(box_id), ocr_text=str(text))
    if translation is not None:
        set_box_translation_by_id(
            volume_id,
            resolved_filename,
            box_id=int(box_id),
            translation=str(translation),
        )
    if note is not None:
        set_box_note_by_id(volume_id, resolved_filename, box_id=int(box_id), note=str(note))

    refreshed = load_page(volume_id, resolved_filename)
    refreshed_boxes = list_text_boxes_for_page(refreshed)
    updated = find_text_box_by_id(refreshed_boxes, int(box_id))
    page_state = build_page_state_snapshot(
        volume_id=volume_id,
        filename=resolved_filename,
        page=refreshed,
    )
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "box_id": int(box_id),
        "updated_fields": {
            "text": text is not None,
            "translation": translation is not None,
            "note": note is not None,
        },
        "page_revision": page_state.page_revision,
        "box": updated or existing,
    }


def search_volume_text_boxes_tool(
    *,
    volume_id: str,
    query: str,
    limit: int = 40,
    only_translated: bool = False,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return {"error": "query is required"}

    safe_limit = max(1, min(int(limit), 200))
    results: list[dict[str, Any]] = []
    for filename in list_page_filenames(volume_id):
        page = load_page(volume_id, filename)
        text_boxes = list_text_boxes_for_page(page)
        for box in text_boxes:
            text_value = str(box.get("text") or "").strip()
            translation_value = str(box.get("translation") or "").strip()
            if only_translated and not translation_value:
                continue
            haystack = f"{text_value}\n{translation_value}".lower()
            if normalized_query not in haystack:
                continue
            results.append(
                {
                    "filename": filename,
                    "box_id": int(box.get("id") or 0),
                    "orderIndex": int(box.get("orderIndex") or 0),
                    "text": text_value,
                    "translation": translation_value,
                }
            )
            if len(results) >= safe_limit:
                return {
                    "volume_id": volume_id,
                    "query": query,
                    "total": len(results),
                    "results": results,
                    "truncated": True,
                }
    return {
        "volume_id": volume_id,
        "query": query,
        "total": len(results),
        "results": results,
        "truncated": False,
    }
