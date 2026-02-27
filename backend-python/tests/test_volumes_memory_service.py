"""Unit tests for extracted volumes memory service helpers.

These tests validate memory payload shaping and error/status behavior moved
out of `api/routers/volumes.py` into `api/routers/volumes_memory_service.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.routers.volumes_memory_service import (
    clear_page_memory,
    clear_volume_derived_state_payload,
    get_page_memory_payload,
    get_volume_memory_payload,
)


class VolumesMemoryServiceTests(unittest.TestCase):
    def test_get_volume_memory_defaults_when_missing_context(self) -> None:
        with (
            patch("api.routers.volumes_memory_service.get_volume", return_value=object()),
            patch("api.routers.volumes_memory_service.get_volume_context", return_value=None),
        ):
            payload = get_volume_memory_payload("vol-a")

        self.assertEqual(payload["rollingSummary"], "")
        self.assertEqual(payload["activeCharacters"], [])
        self.assertEqual(payload["openThreads"], [])
        self.assertEqual(payload["glossary"], [])
        self.assertIsNone(payload["lastPageIndex"])
        self.assertIsNone(payload["updatedAt"])

    def test_get_page_memory_rejects_unknown_page(self) -> None:
        with (
            patch("api.routers.volumes_memory_service.get_volume", return_value=object()),
            patch("api.routers.volumes_memory_service.list_page_filenames", return_value=["001.jpg"]),
            self.assertRaises(HTTPException) as raised,
        ):
            get_page_memory_payload("vol-a", "002.jpg")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertIn("page not found", str(raised.exception.detail).lower())

    def test_clear_page_memory_clears_snapshot_and_text_context(self) -> None:
        with (
            patch("api.routers.volumes_memory_service.get_volume", return_value=object()),
            patch("api.routers.volumes_memory_service.list_page_filenames", return_value=["001.jpg"]),
            patch("api.routers.volumes_memory_service.clear_page_context_snapshot") as clear_snapshot_mock,
            patch("api.routers.volumes_memory_service.set_page_context") as set_context_mock,
        ):
            clear_page_memory("vol-a", "001.jpg")

        clear_snapshot_mock.assert_called_once_with("vol-a", "001.jpg")
        set_context_mock.assert_called_once_with("vol-a", "001.jpg", "")

    def test_clear_volume_derived_state_maps_runtime_error_to_409(self) -> None:
        with (
            patch("api.routers.volumes_memory_service.get_volume", return_value=object()),
            patch(
                "api.routers.volumes_memory_service.clear_volume_derived_data",
                side_effect=RuntimeError("busy"),
            ),
            self.assertRaises(HTTPException) as raised,
        ):
            clear_volume_derived_state_payload("vol-a")

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("busy", str(raised.exception.detail))

    def test_clear_volume_derived_state_maps_counts(self) -> None:
        with (
            patch("api.routers.volumes_memory_service.get_volume", return_value=object()),
            patch(
                "api.routers.volumes_memory_service.clear_volume_derived_data",
                return_value={"pages_touched": 2, "boxes_deleted": 7},
            ),
        ):
            payload = clear_volume_derived_state_payload("vol-a")

        self.assertTrue(payload["cleared"])
        self.assertEqual(payload["details"]["pagesTouched"], 2)
        self.assertEqual(payload["details"]["boxesDeleted"], 7)
        self.assertEqual(payload["details"]["llmCallLogsDeleted"], 0)
