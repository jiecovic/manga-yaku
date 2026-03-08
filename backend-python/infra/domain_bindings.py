# backend-python/infra/domain_bindings.py
"""Composition root for binding core domain ports to infra adapters.

This module is the runtime wiring layer for dependency inversion:
- `core` defines abstract ports (interfaces) for side-effecting operations.
- `infra` provides concrete implementations backed by persistence/integrations.
- startup code calls :func:`bind_domain_ports` once to register adapters.

Keeping the binding here prevents `core` from importing infrastructure details
and keeps adapter selection explicit at application boot.
"""

from __future__ import annotations

from core.domain.page_ports import PageWritePort, register_page_write_port
from infra.db.store_boxes import (
    set_box_ocr_text_by_id as store_set_box_ocr_text_by_id,
)
from infra.db.store_boxes import (
    set_box_translation_by_id as store_set_box_translation_by_id,
)


class DbStorePageWritePort(PageWritePort):
    """Page write-port adapter backed by database store modules."""

    def set_box_ocr_text_by_id(
        self,
        volume_id: str,
        filename: str,
        *,
        box_id: int,
        ocr_text: str,
    ) -> None:
        store_set_box_ocr_text_by_id(
            volume_id,
            filename,
            box_id=box_id,
            ocr_text=ocr_text,
        )

    def set_box_translation_by_id(
        self,
        volume_id: str,
        filename: str,
        *,
        box_id: int,
        translation: str,
    ) -> None:
        store_set_box_translation_by_id(
            volume_id,
            filename,
            box_id=box_id,
            translation=translation,
        )


def bind_domain_ports() -> None:
    """Register concrete infrastructure adapters for domain port interfaces."""
    register_page_write_port(DbStorePageWritePort())
