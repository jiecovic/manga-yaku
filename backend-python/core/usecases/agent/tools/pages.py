# backend-python/core/usecases/agent/tools/pages.py
"""Page navigation helpers for agent tools."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tools.shared import coerce_filename, list_text_boxes_for_page
from core.usecases.agent.turn_state import get_active_page_revision
from infra.db.store_volume_page import list_page_filenames, load_page


def list_volume_pages_tool(volume_id: str) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}
    filenames = list_page_filenames(volume_id)
    return {
        "volume_id": volume_id,
        "page_count": len(filenames),
        "filenames": filenames,
    }


def set_active_page_tool(
    *,
    volume_id: str,
    filename: str,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename = coerce_filename(filename)
    if not resolved_filename:
        return {"error": "filename is required"}

    filenames = list_page_filenames(volume_id)
    if resolved_filename not in filenames:
        return {
            "error": f"Page {resolved_filename} was not found in volume {volume_id}",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "page_count": len(filenames),
        }

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "text_box_count": len(text_boxes),
        "page_index": int(filenames.index(resolved_filename)) + 1,
        "page_count": len(filenames),
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=resolved_filename,
        ),
    }


def shift_active_page_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    offset: int,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    filenames = list_page_filenames(volume_id)
    if not filenames:
        return {"error": "No pages found in active volume", "volume_id": volume_id, "page_count": 0}

    if active_filename and active_filename in filenames:
        current_index = filenames.index(active_filename)
    else:
        current_index = 0

    delta = int(offset)
    if delta == 0:
        return set_active_page_tool(volume_id=volume_id, filename=filenames[current_index])

    target_index = current_index + delta
    if target_index < 0:
        target_index = 0
    if target_index >= len(filenames):
        target_index = len(filenames) - 1

    target_filename = filenames[target_index]
    result = set_active_page_tool(volume_id=volume_id, filename=target_filename)
    if str(result.get("status") or "").strip().lower() == "ok":
        result["moved_by"] = int(target_index - current_index)
        result["requested_offset"] = delta
        result["at_boundary"] = bool(target_index == 0 or target_index == len(filenames) - 1)
    return result
