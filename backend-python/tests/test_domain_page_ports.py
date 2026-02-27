# backend-python/tests/test_domain_page_ports.py
"""Unit tests for core domain page write port binding and delegation.

These tests verify domain helpers route writes through the configured port and
that missing-port failures remain explicit.
"""

from __future__ import annotations

import unittest

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


class DomainPagePortsTests(unittest.TestCase):
    def setUp(self) -> None:
        # Preserve global port registration across tests.
        self._orig = page_ports._page_write_port

    def tearDown(self) -> None:
        page_ports._page_write_port = self._orig

    def test_domain_pages_delegate_to_registered_port(self) -> None:
        fake = _FakePageWritePort()
        page_ports.register_page_write_port(fake)

        set_box_ocr_text_by_id("vol", "001.jpg", box_id=3, ocr_text="jp")
        set_box_translation_by_id("vol", "001.jpg", box_id=3, translation="en")

        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[0], ("ocr", "vol", 3, "001.jpg", "jp"))
        self.assertEqual(fake.calls[1], ("translation", "vol", 3, "001.jpg", "en"))

    def test_get_port_raises_when_unconfigured(self) -> None:
        page_ports._page_write_port = None
        with self.assertRaises(RuntimeError):
            page_ports.get_page_write_port()
