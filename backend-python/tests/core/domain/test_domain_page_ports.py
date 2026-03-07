# backend-python/tests/core/domain/test_domain_page_ports.py
"""Unit tests for core domain page write-port binding and delegation.

What is tested:
- Domain write helpers delegate calls to the currently bound page-write port.
- Missing binding failures stay explicit and actionable.

How it is tested:
- A small fake port captures calls for assertion.
- Tests bind/unbind the domain port directly without DB involvement.
"""

from __future__ import annotations

import pytest

from core.domain import page_ports
from core.domain.pages import set_box_ocr_text_by_id, set_box_translation_by_id


class _FakePageWritePort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, str, str]] = []

    def set_box_ocr_text_by_id(
        self,
        volume_id: str,
        filename: str,
        *,
        box_id: int,
        ocr_text: str,
    ) -> None:
        self.calls.append(("ocr", volume_id, box_id, filename, ocr_text))

    def set_box_translation_by_id(
        self,
        volume_id: str,
        filename: str,
        *,
        box_id: int,
        translation: str,
    ) -> None:
        self.calls.append(("translation", volume_id, box_id, filename, translation))


@pytest.fixture(autouse=True)
def _restore_page_write_port():
    original = page_ports._page_write_port
    yield
    page_ports._page_write_port = original


def test_domain_pages_delegate_to_registered_port() -> None:
    fake = _FakePageWritePort()
    page_ports.register_page_write_port(fake)

    set_box_ocr_text_by_id("vol", "001.jpg", box_id=3, ocr_text="jp")
    set_box_translation_by_id("vol", "001.jpg", box_id=3, translation="en")

    assert len(fake.calls) == 2
    assert fake.calls[0] == ("ocr", "vol", 3, "001.jpg", "jp")
    assert fake.calls[1] == ("translation", "vol", 3, "001.jpg", "en")


def test_get_port_raises_when_unconfigured() -> None:
    page_ports._page_write_port = None
    with pytest.raises(RuntimeError):
        page_ports.get_page_write_port()
