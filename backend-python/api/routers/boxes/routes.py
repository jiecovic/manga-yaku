# backend-python/api/routers/boxes/routes.py
"""HTTP routes for boxes endpoints."""

from __future__ import annotations

from api.schemas.boxes import Box, BoxPage, BoxTextPatch
from fastapi import APIRouter, HTTPException
from infra.db.store_boxes import (
    set_box_note_by_id,
    set_box_ocr_text_by_id,
    set_box_translation_by_id,
)
from infra.db.store_volume_page import load_page, save_page

router = APIRouter()


# -----------------------------
# GET boxes for a page
# -----------------------------
@router.get("/boxes/{volume_id}/{page_filename}", response_model=BoxPage)
def get_boxes(volume_id: str, page_filename: str):
    """Return boxes."""
    try:
        data = load_page(volume_id, page_filename)
    except Exception as e:
        raise HTTPException(500, f"Failed to load page: {e}") from e

    raw_boxes = data.get("boxes", [])
    boxes = [Box(**b) for b in raw_boxes]
    return BoxPage(boxes=boxes)


# -----------------------------
# POST save boxes for a page
# -----------------------------
@router.post("/boxes/{volume_id}/{page_filename}")
def save_boxes(volume_id: str, page_filename: str, payload: BoxPage):
    """Handle save boxes."""
    try:
        data = {
            "boxes": [b.model_dump() for b in payload.boxes],
        }
        save_page(volume_id, page_filename, data)
        return {"status": "ok", "saved": len(payload.boxes)}
    except Exception as e:
        raise HTTPException(500, f"Failed to save boxes: {e}") from e


@router.patch("/boxes/{volume_id}/{page_filename}/{box_id}")
def patch_box_text(
    volume_id: str,
    page_filename: str,
    box_id: int,
    payload: BoxTextPatch,
):
    """Partially update box text."""
    try:
        if payload.text is not None:
            set_box_ocr_text_by_id(
                volume_id,
                page_filename,
                box_id=box_id,
                ocr_text=payload.text,
            )
        if payload.translation is not None:
            set_box_translation_by_id(
                volume_id,
                page_filename,
                box_id=box_id,
                translation=payload.translation,
            )
        if payload.note is not None:
            set_box_note_by_id(
                volume_id,
                page_filename,
                box_id=box_id,
                note=payload.note,
            )
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, f"Failed to update box text: {e}") from e
