# backend-python/tests/infra/jobs/test_operations.py
"""Unit tests for shared persisted job operation helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from infra.jobs.operations import (
    enqueue_ocr_box_operation,
    enqueue_ocr_page_operation,
    enqueue_translate_box_operation,
)


def test_enqueue_ocr_box_operation_builds_workflow_input() -> None:
    with patch(
        "infra.jobs.operations.create_persisted_ocr_box_workflow",
        return_value="wf-ocr-box-1",
    ) as create_mock:
        workflow_id = enqueue_ocr_box_operation(
            {
                "profileId": "manga_ocr_default",
                "volumeId": "vol-a",
                "filename": "001.jpg",
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "boxId": 7,
                "boxOrder": 3,
            }
        )

    assert workflow_id == "wf-ocr-box-1"
    create_mock.assert_called_once()
    workflow_input = create_mock.call_args.args[0]
    assert workflow_input.profile_id == "manga_ocr_default"
    assert workflow_input.volume_id == "vol-a"
    assert workflow_input.filename == "001.jpg"
    assert workflow_input.box_id == 7
    assert workflow_input.box_order == 3


def test_enqueue_ocr_page_operation_prefers_primary_profile() -> None:
    with patch(
        "infra.jobs.operations.create_persisted_ocr_page_workflow",
        return_value="wf-ocr-page-1",
    ) as create_mock:
        workflow_id = enqueue_ocr_page_operation(
            {
                "profileId": "openai_fast_ocr",
                "profileIds": ["openai_fast_ocr", "manga_ocr_default"],
                "volumeId": "vol-a",
                "filename": "001.jpg",
                "skipExisting": False,
            }
        )

    assert workflow_id == "wf-ocr-page-1"
    create_mock.assert_called_once()
    workflow_input = create_mock.call_args.args[0]
    assert workflow_input.profile_ids == ["openai_fast_ocr"]
    assert workflow_input.volume_id == "vol-a"
    assert workflow_input.filename == "001.jpg"
    assert workflow_input.skip_existing is False


def test_enqueue_translate_box_operation_normalizes_payload() -> None:
    with (
        patch(
            "infra.jobs.operations.get_translation_profile",
            return_value={"enabled": True},
        ),
        patch(
            "infra.jobs.operations.get_setting_value",
            return_value=True,
        ),
        patch(
            "infra.jobs.operations.create_translate_workflow_with_task",
            return_value="wf-translate-1",
        ) as create_mock,
    ):
        workflow_id = enqueue_translate_box_operation(
            {
                "profileId": "openai_fast_translate",
                "volumeId": "vol-a",
                "filename": "001.jpg",
                "boxId": 9,
                "usePageContext": None,
                "boxOrder": 3,
            }
        )

    assert workflow_id == "wf-translate-1"
    create_mock.assert_called_once()
    kwargs = create_mock.call_args.kwargs
    assert kwargs["volume_id"] == "vol-a"
    assert kwargs["filename"] == "001.jpg"
    assert kwargs["box_id"] == 9
    assert kwargs["profile_id"] == "openai_fast_translate"
    assert kwargs["use_page_context"] is True
    assert kwargs["request_payload"]["boxOrder"] == 3
    assert kwargs["request_payload"]["usePageContext"] is True


def test_enqueue_translate_box_operation_rejects_disabled_profile() -> None:
    with (
        patch(
            "infra.jobs.operations.get_translation_profile",
            return_value={"enabled": False},
        ),
        pytest.raises(ValueError) as raised,
    ):
        enqueue_translate_box_operation(
            {
                "profileId": "openai_fast_translate",
                "volumeId": "vol-a",
                "filename": "001.jpg",
                "boxId": 9,
            }
        )

    assert "disabled" in str(raised.value).lower()
