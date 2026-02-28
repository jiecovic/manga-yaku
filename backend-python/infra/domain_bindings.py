"""Binds domain ports to infrastructure implementations."""

from __future__ import annotations

from core.domain.page_ports import PageWritePort, register_page_write_port
from infra.db.db_store import (
    set_box_ocr_text_by_id as store_set_box_ocr_text_by_id,
)
from infra.db.db_store import (
    set_box_translation_by_id as store_set_box_translation_by_id,
)


class DbStorePageWritePort(PageWritePort):
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
    register_page_write_port(DbStorePageWritePort())
