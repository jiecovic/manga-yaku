# backend-python/api/routers/boxes.py
"""HTTP routes for boxes endpoints."""

from __future__ import annotations

from api.schemas.boxes import Box, BoxPage, BoxTextPatch
from fastapi import APIRouter, HTTPException
from infra.db.db_store import (
    load_page,
    save_page,
    set_box_ocr_text_by_id,
    set_box_translation_by_id,
)

router = APIRouter()


# -----------------------------
# GET boxes for a page
# -----------------------------
@router.get("/boxes/{volume_id}/{page_filename}", response_model=BoxPage)
def get_boxes(volume_id: str, page_filename: str):
    try:
        data = load_page(volume_id, page_filename)
    except Exception as e:
        raise HTTPException(500, f"Failed to load page: {e}") from e

    raw_boxes = data.get("boxes", [])
    boxes = [Box(**b) for b in raw_boxes]
    page_ctx = data.get("pageContext") or ""

    return BoxPage(boxes=boxes, pageContext=page_ctx)


# -----------------------------
# POST (save) boxes + pageContext for a page
# -----------------------------
@router.post("/boxes/{volume_id}/{page_filename}")
def save_boxes(volume_id: str, page_filename: str, payload: BoxPage):
    try:
        page_ctx = payload.pageContext
        if page_ctx is None:
            existing = load_page(volume_id, page_filename)
            page_ctx = existing.get("pageContext") or ""

        data = {
            "boxes": [b.model_dump() for b in payload.boxes],
            "pageContext": page_ctx,
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
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, f"Failed to update box text: {e}") from e
