# backend-python/core/usecases/agent/tool_shared.py
"""Shared helpers for agent page and box tools."""

from __future__ import annotations

from typing import Any


def coerce_filename(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None



def list_text_boxes_for_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    if not isinstance(raw_boxes, list):
        return []

    out: list[dict[str, Any]] = []
    for box in raw_boxes:
        if not isinstance(box, dict):
            continue
        if str(box.get("type") or "").strip().lower() != "text":
            continue
        box_id = int(box.get("id") or 0)
        if box_id <= 0:
            continue
        out.append(
            {
                "id": box_id,
                "orderIndex": int(box.get("orderIndex") or box_id),
                "x": float(box.get("x") or 0.0),
                "y": float(box.get("y") or 0.0),
                "width": float(box.get("width") or 0.0),
                "height": float(box.get("height") or 0.0),
                "text": str(box.get("text") or "").strip(),
                "translation": str(box.get("translation") or "").strip(),
                "note": str(box.get("note") or "").strip(),
            }
        )

    out.sort(key=lambda item: (item["orderIndex"], item["id"]))
    return out



def find_text_box_by_id(text_boxes: list[dict[str, Any]], box_id: int) -> dict[str, Any] | None:
    target_box_id = int(box_id)
    return next((item for item in text_boxes if int(item["id"]) == target_box_id), None)



def resolve_read_page_filename(
    *,
    volume_id: str,
    filename: str | None,
    active_filename: str | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    resolved_filename = coerce_filename(filename)
    if resolved_filename:
        return resolved_filename, None

    resolved_active_filename = coerce_filename(active_filename)
    if resolved_active_filename:
        return resolved_active_filename, None

    return None, {
        "error": "filename is required when no active page is selected",
        "volume_id": volume_id,
    }



def resolve_active_page_filename(
    *,
    volume_id: str,
    filename: str | None,
    active_filename: str | None,
    action_label: str,
) -> tuple[str | None, dict[str, Any] | None]:
    resolved_active_filename = coerce_filename(active_filename)
    if not resolved_active_filename:
        return None, {"error": "No active page selected", "volume_id": volume_id}

    resolved_filename = coerce_filename(filename) or resolved_active_filename
    if resolved_filename != resolved_active_filename:
        return None, {
            "error": (
                f"{action_label} is restricted to the active page ({resolved_active_filename}); "
                f"got {resolved_filename}"
            ),
            "volume_id": volume_id,
            "active_filename": resolved_active_filename,
            "filename": resolved_filename,
        }
    return resolved_filename, None
