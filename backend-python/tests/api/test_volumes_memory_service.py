# backend-python/tests/api/test_volumes_memory_service.py
"""Unit tests for extracted volumes memory service helpers.

What is tested:
- Memory payload shaping for page-level and volume-level endpoints.
- Clear operations and error/status mapping behavior.

How it is tested:
- Volume/context repository calls are patched at service boundaries.
- Service helpers are exercised directly without starting API app lifecycle.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.services.volumes_memory_service import (
    clear_page_memory,
    clear_volume_derived_state_payload,
    get_page_memory_payload,
    get_volume_memory_payload,
)


def test_get_volume_memory_defaults_when_missing_context() -> None:
    with (
        patch("api.services.volumes_memory_service.get_volume", return_value=object()),
        patch("api.services.volumes_memory_service.get_volume_context", return_value=None),
    ):
        payload = get_volume_memory_payload("vol-a")

    assert payload["rollingSummary"] == ""
    assert payload["activeCharacters"] == []
    assert payload["openThreads"] == []
    assert payload["glossary"] == []
    assert payload["lastPageIndex"] is None
    assert payload["updatedAt"] is None


def test_get_page_memory_rejects_unknown_page() -> None:
    with (
        patch("api.services.volumes_memory_service.get_volume", return_value=object()),
        patch("api.services.volumes_memory_service.list_page_filenames", return_value=["001.jpg"]),
        pytest.raises(HTTPException) as raised,
    ):
        get_page_memory_payload("vol-a", "002.jpg")

    assert raised.value.status_code == 404
    assert "page not found" in str(raised.value.detail).lower()


def test_get_page_memory_includes_manual_notes() -> None:
    with (
        patch("api.services.volumes_memory_service.get_volume", return_value=object()),
        patch("api.services.volumes_memory_service.list_page_filenames", return_value=["001.jpg"]),
        patch(
            "api.services.volumes_memory_service.get_page_context_snapshot",
            return_value={
                "manual_notes": "notes",
                "page_summary": "summary",
                "image_summary": "image",
                "characters_snapshot": [],
                "open_threads_snapshot": [],
                "glossary_snapshot": [],
                "created_at": None,
                "updated_at": None,
            },
        ),
    ):
        payload = get_page_memory_payload("vol-a", "001.jpg")

    assert payload["manualNotes"] == "notes"
    assert payload["pageSummary"] == "summary"


def test_clear_page_memory_clears_snapshot_only() -> None:
    with (
        patch("api.services.volumes_memory_service.get_volume", return_value=object()),
        patch("api.services.volumes_memory_service.list_page_filenames", return_value=["001.jpg"]),
        patch("api.services.volumes_memory_service.clear_page_context_snapshot") as clear_snapshot_mock,
    ):
        clear_page_memory("vol-a", "001.jpg")

    clear_snapshot_mock.assert_called_once_with("vol-a", "001.jpg")


def test_clear_volume_derived_state_maps_runtime_error_to_409() -> None:
    with (
        patch("api.services.volumes_memory_service.get_volume", return_value=object()),
        patch(
            "api.services.volumes_memory_service.clear_volume_derived_data",
            side_effect=RuntimeError("busy"),
        ),
        pytest.raises(HTTPException) as raised,
    ):
        clear_volume_derived_state_payload("vol-a")

    assert raised.value.status_code == 409
    assert "busy" in str(raised.value.detail)


def test_clear_volume_derived_state_maps_counts() -> None:
    with (
        patch("api.services.volumes_memory_service.get_volume", return_value=object()),
        patch(
            "api.services.volumes_memory_service.clear_volume_derived_data",
            return_value={"pages_touched": 2, "boxes_deleted": 7},
        ),
    ):
        payload = clear_volume_derived_state_payload("vol-a")

    assert payload["cleared"] is True
    assert payload["details"]["pagesTouched"] == 2
    assert payload["details"]["boxesDeleted"] == 7
    assert payload["details"]["llmCallLogsDeleted"] == 0
