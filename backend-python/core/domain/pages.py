# backend-python/core/domain/pages.py
from __future__ import annotations

from infra.db.db_store import (
    set_box_ocr_text_by_id as store_set_box_ocr_text_by_id,
)
from infra.db.db_store import (
    set_box_translation_by_id as store_set_box_translation_by_id,
)


def set_box_ocr_text_by_id(
        volume_id: str,
        filename: str,
        box_id: int,
        ocr_text: str,
) -> None:
    """
    Update the 'text' field of a box identified by its numeric id.
    """
    store_set_box_ocr_text_by_id(
        volume_id,
        filename,
        box_id=box_id,
        ocr_text=ocr_text,
    )


def set_box_translation_by_id(
        volume_id: str,
        filename: str,
        box_id: int,
        translation: str,
) -> None:
    """
    Update the 'translation' field of a box identified by its numeric id
    and persist the page state.
    """
    store_set_box_translation_by_id(
        volume_id,
        filename,
        box_id=box_id,
        translation=translation,
    )

