# backend-python/core/domain/page_ports.py
"""Core domain models and contracts for page ports."""

from __future__ import annotations

from typing import Protocol


class PageWritePort(Protocol):
    def set_box_ocr_text_by_id(
        self,
        volume_id: str,
        filename: str,
        *,
        box_id: int,
        ocr_text: str,
    ) -> None: ...

    def set_box_translation_by_id(
        self,
        volume_id: str,
        filename: str,
        *,
        box_id: int,
        translation: str,
    ) -> None: ...


_page_write_port: PageWritePort | None = None


def register_page_write_port(port: PageWritePort) -> None:
    global _page_write_port
    _page_write_port = port


def get_page_write_port() -> PageWritePort:
    if _page_write_port is None:
        raise RuntimeError("Page write port is not configured")
    return _page_write_port
