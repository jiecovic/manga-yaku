# backend-python/tests/core/usecases/test_agent_tool_impl.py
"""Tests for agent tool helper defaults and workflow wiring."""

from __future__ import annotations

from unittest.mock import patch

from core.usecases.agent.tool_boxes import (
    list_text_boxes_tool,
    update_text_box_fields_tool,
)
from core.usecases.agent.tool_context import (
    get_page_memory_tool,
    get_volume_context_tool,
    update_page_memory_tool,
)
from core.usecases.agent.tool_jobs import (
    detect_text_boxes_tool,
    ocr_text_box_tool,
    translate_active_page_tool,
)
from infra.jobs.store import JobStatus


def test_list_text_boxes_defaults_to_active_page() -> None:
    with patch(
        "core.usecases.agent.tool_boxes.load_page",
        return_value={
            "boxes": [
                {
                    "id": 1,
                    "type": "text",
                    "orderIndex": 1,
                    "x": 10,
                    "y": 20,
                    "width": 30,
                    "height": 40,
                    "text": "jp",
                    "translation": "en",
                    "note": "n",
                }
            ]
        },
    ) as load_page_mock:
        result = list_text_boxes_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            filename=None,
            limit=10,
        )

    assert result["filename"] == "001.jpg"
    assert result["total"] == 1
    assert result["ocr_filled_count"] == 1
    assert result["translated_count"] == 1
    assert result["untranslated_count"] == 0
    load_page_mock.assert_called_once_with("vol-a", "001.jpg")


def test_update_text_box_fields_defaults_to_active_page() -> None:
    initial_page = {
        "boxes": [
            {
                "id": 7,
                "type": "text",
                "orderIndex": 7,
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "text": "old",
                "translation": "",
                "note": "",
            }
        ]
    }
    updated_page = {
        "boxes": [
            {
                "id": 7,
                "type": "text",
                "orderIndex": 7,
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "text": "old",
                "translation": "",
                "note": "checked",
            }
        ]
    }
    with (
        patch(
            "core.usecases.agent.tool_boxes.load_page",
            side_effect=[initial_page, updated_page],
        ) as load_page_mock,
        patch("core.usecases.agent.tool_boxes.set_box_note_by_id") as set_note_mock,
        patch(
            "core.usecases.agent.tool_boxes.get_active_page_revision",
            return_value="rev-1",
        ),
    ):
        result = update_text_box_fields_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            box_id=7,
            filename=None,
            note="checked",
        )

    assert result["status"] == "ok"
    assert result["filename"] == "001.jpg"
    set_note_mock.assert_called_once_with("vol-a", "001.jpg", box_id=7, note="checked")
    assert load_page_mock.call_count == 2


def test_ocr_text_box_defaults_to_active_page() -> None:
    initial_page = {
        "boxes": [
            {
                "id": 5,
                "type": "text",
                "orderIndex": 2,
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "text": "",
                "translation": "",
                "note": "",
            }
        ]
    }
    refreshed_page = {
        "boxes": [
            {
                "id": 5,
                "type": "text",
                "orderIndex": 2,
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "text": "ocr text",
                "translation": "",
                "note": "",
            }
        ]
    }
    with (
        patch(
            "core.usecases.agent.tool_jobs.load_page",
            side_effect=[initial_page, refreshed_page],
        ) as load_page_mock,
        patch(
            "core.usecases.agent.tool_jobs.claim_idempotency_key",
            return_value={"status": "claimed", "resource_id": None},
        ),
        patch(
            "core.usecases.agent.tool_jobs.create_ocr_box_workflow",
            return_value="wf-123",
        ) as create_workflow_mock,
        patch(
            "core.usecases.agent.tool_jobs.finalize_idempotency_key",
            return_value="wf-123",
        ),
        patch(
            "core.usecases.agent.tool_jobs.wait_for_workflow_terminal",
            return_value={
                "status": "completed",
                "result_json": {"message": "done"},
            },
        ),
        patch(
            "core.usecases.agent.tool_jobs.get_active_page_revision",
            return_value="rev-2",
        ),
    ):
        result = ocr_text_box_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            box_id=5,
            filename=None,
            profile_id="manga_ocr_default",
        )

    assert result["status"] == "ok"
    assert result["filename"] == "001.jpg"
    create_workflow_mock.assert_called_once()
    workflow_input = create_workflow_mock.call_args.args[0]
    assert workflow_input.filename == "001.jpg"
    assert workflow_input.box_id == 5
    assert load_page_mock.call_count == 2


def test_ocr_text_box_skips_existing_text_by_default() -> None:
    page = {
        "boxes": [
            {
                "id": 5,
                "type": "text",
                "orderIndex": 2,
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "text": "already OCRed",
                "translation": "",
                "note": "",
            }
        ]
    }
    with (
        patch(
            "core.usecases.agent.tool_jobs.load_page",
            return_value=page,
        ) as load_page_mock,
        patch(
            "core.usecases.agent.tool_jobs.claim_idempotency_key",
        ) as claim_mock,
        patch(
            "core.usecases.agent.tool_jobs.create_ocr_box_workflow",
        ) as create_workflow_mock,
        patch(
            "core.usecases.agent.tool_jobs.get_active_page_revision",
            return_value="rev-2",
        ),
    ):
        result = ocr_text_box_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            box_id=5,
            filename=None,
            profile_id="manga_ocr_default",
        )

    assert result["status"] == "skipped_existing"
    assert result["text"] == "already OCRed"
    assert result["resource_reused"]
    load_page_mock.assert_called_once_with("vol-a", "001.jpg")
    claim_mock.assert_not_called()
    create_workflow_mock.assert_not_called()


def test_ocr_text_box_force_rerun_overrides_existing_text_guard() -> None:
    initial_page = {
        "boxes": [
            {
                "id": 5,
                "type": "text",
                "orderIndex": 2,
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "text": "already OCRed",
                "translation": "",
                "note": "",
            }
        ]
    }
    refreshed_page = {
        "boxes": [
            {
                "id": 5,
                "type": "text",
                "orderIndex": 2,
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "text": "rerun text",
                "translation": "",
                "note": "",
            }
        ]
    }
    with (
        patch(
            "core.usecases.agent.tool_jobs.load_page",
            side_effect=[initial_page, refreshed_page],
        ),
        patch(
            "core.usecases.agent.tool_jobs.claim_idempotency_key",
            return_value={"status": "claimed", "resource_id": None},
        ),
        patch(
            "core.usecases.agent.tool_jobs.create_ocr_box_workflow",
            return_value="wf-123",
        ) as create_workflow_mock,
        patch(
            "core.usecases.agent.tool_jobs.finalize_idempotency_key",
            return_value="wf-123",
        ),
        patch(
            "core.usecases.agent.tool_jobs.wait_for_workflow_terminal",
            return_value={
                "status": "completed",
                "result_json": {"message": "done"},
            },
        ),
        patch(
            "core.usecases.agent.tool_jobs.get_active_page_revision",
            return_value="rev-2",
        ),
    ):
        result = ocr_text_box_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            box_id=5,
            filename=None,
            profile_id="manga_ocr_default",
            force_rerun=True,
        )

    assert result["status"] == "ok"
    create_workflow_mock.assert_called_once()


def test_get_volume_context_preserves_character_gender() -> None:
    with patch(
        "core.usecases.agent.tool_context.get_volume_context",
        return_value={
            "rolling_summary": "summary",
            "active_characters": [{"name": "Saitama", "gender": "male", "info": "hero"}],
            "open_threads": ["thread"],
            "glossary": [{"term": "hero", "translation": "hero", "note": ""}],
            "last_page_index": 3,
        },
    ):
        result = get_volume_context_tool(volume_id="vol-a")

    assert result["active_characters"] == [{"name": "Saitama", "gender": "male", "info": "hero"}]
    assert result["last_page_index"] == 3


def test_get_page_memory_defaults_to_active_page() -> None:
    with patch(
        "core.usecases.agent.tool_context.get_page_context_snapshot",
        return_value={
            "manual_notes": "note",
            "page_summary": "summary",
            "image_summary": "image",
            "characters_snapshot": [{"name": "Genos", "gender": "male", "info": "cyborg"}],
            "open_threads_snapshot": ["thread"],
            "glossary_snapshot": [{"term": "A", "translation": "B", "note": "C"}],
            "created_at": None,
            "updated_at": None,
        },
    ):
        result = get_page_memory_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            filename=None,
        )

    assert result["filename"] == "001.jpg"
    assert result["characters"] == [{"name": "Genos", "gender": "male", "info": "cyborg"}]
    assert result["manual_notes"] == "note"


def test_update_page_memory_defaults_to_active_page() -> None:
    existing_snapshot = {
        "manual_notes": "",
        "page_summary": "",
        "image_summary": "",
        "characters_snapshot": [],
        "open_threads_snapshot": [],
        "glossary_snapshot": [],
        "created_at": None,
        "updated_at": None,
    }
    refreshed_snapshot = {
        "manual_notes": "confirmed",
        "page_summary": "summary",
        "image_summary": "",
        "characters_snapshot": [{"name": "Saitama", "gender": "male", "info": "hero"}],
        "open_threads_snapshot": [],
        "glossary_snapshot": [],
        "created_at": None,
        "updated_at": None,
    }
    with (
        patch(
            "core.usecases.agent.tool_context.get_page_context_snapshot",
            side_effect=[existing_snapshot, refreshed_snapshot],
        ),
        patch("core.usecases.agent.tool_context.upsert_page_context") as upsert_mock,
    ):
        result = update_page_memory_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            filename=None,
            manual_notes="confirmed",
            page_summary="summary",
            characters=[{"name": "Saitama", "gender": "male", "info": "hero"}],
        )

    assert result["status"] == "ok"
    assert result["filename"] == "001.jpg"
    assert result["manual_notes"] == "confirmed"
    upsert_mock.assert_called_once_with(
        "vol-a",
        "001.jpg",
        manual_notes="confirmed",
        page_summary="summary",
        image_summary="",
        characters_snapshot=[{"name": "Saitama", "gender": "male", "info": "hero"}],
        open_threads_snapshot=[],
        glossary_snapshot=[],
    )


def test_detect_text_boxes_replay_reuses_equivalent_job() -> None:
    with (
        patch(
            "core.usecases.agent.tool_jobs.get_active_page_revision",
            return_value="rev-1",
        ),
        patch(
            "core.usecases.agent.tool_jobs.claim_idempotency_key",
            return_value={"status": "replay", "resource_id": "job-123"},
        ),
        patch(
            "core.usecases.agent.tool_jobs.wait_for_workflow_terminal",
            return_value=None,
        ),
        patch(
            "core.usecases.agent.tool_jobs.load_page",
            return_value={"boxes": [{"id": 1, "type": "text"}]},
        ),
    ):
        result = detect_text_boxes_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            filename=None,
            profile_id="default",
        )

    assert result["status"] == "ok"
    assert result["idempotency_state"] == "replay"
    assert result["resource_reused"]
    assert result["job_id"] == "job-123"


def test_detect_text_boxes_bypasses_replayed_zero_box_result() -> None:
    with (
        patch(
            "core.usecases.agent.tool_jobs.get_active_page_revision",
            return_value="rev-1",
        ),
        patch(
            "core.usecases.agent.tool_jobs.claim_idempotency_key",
            return_value={"status": "replay", "resource_id": "job-old"},
        ) as claim_mock,
        patch(
            "core.usecases.agent.tool_jobs.create_persisted_utility_workflow",
            return_value="job-789",
        ),
        patch(
            "core.usecases.agent.tool_jobs.wait_for_workflow_terminal",
            return_value={
                "status": "completed",
                "result_json": {"count": 4, "message": "Detected 4 boxes"},
            },
        ),
        patch(
            "core.usecases.agent.tool_jobs.load_page",
            side_effect=[
                {"boxes": []},
                {"boxes": [{"id": 1, "type": "text"}]},
            ],
        ),
    ):
        result = detect_text_boxes_tool(
            volume_id="vol-a",
            active_filename="004.jpg",
            filename=None,
        )

    assert result["status"] == "ok"
    assert result["idempotency_state"] == "new"
    assert not result["resource_reused"]
    assert result["job_id"] == "job-789"
    claim_mock.assert_called_once()


def test_ocr_text_box_claimed_request_finalizes_idempotency() -> None:
    initial_page = {
        "boxes": [
            {
                "id": 5,
                "type": "text",
                "orderIndex": 2,
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "text": "",
                "translation": "",
                "note": "",
            }
        ]
    }
    refreshed_page = {
        "boxes": [
            {
                "id": 5,
                "type": "text",
                "orderIndex": 2,
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "text": "ocr text",
                "translation": "",
                "note": "",
            }
        ]
    }
    with (
        patch(
            "core.usecases.agent.tool_jobs.load_page",
            side_effect=[initial_page, refreshed_page],
        ),
        patch(
            "core.usecases.agent.tool_jobs.get_active_page_revision",
            return_value="rev-2",
        ),
        patch(
            "core.usecases.agent.tool_jobs.claim_idempotency_key",
            return_value={"status": "claimed", "resource_id": None},
        ),
        patch(
            "core.usecases.agent.tool_jobs.create_ocr_box_workflow",
            return_value="wf-123",
        ),
        patch(
            "core.usecases.agent.tool_jobs.finalize_idempotency_key",
            return_value="wf-123",
        ) as finalize_mock,
        patch(
            "core.usecases.agent.tool_jobs.wait_for_workflow_terminal",
            return_value={
                "status": "completed",
                "result_json": {"message": "done"},
            },
        ),
    ):
        result = ocr_text_box_tool(
            volume_id="vol-a",
            active_filename="001.jpg",
            box_id=5,
            filename=None,
            profile_id="manga_ocr_default",
        )

    assert result["status"] == "ok"
    assert result["idempotency_state"] == "new"
    assert not result["resource_reused"]
    finalize_mock.assert_called_once()


def test_translate_active_page_defaults_to_active_page_and_returns_completed_result() -> None:
    finished_job = type(
        "FinishedJob",
        (),
        {
            "status": JobStatus.finished,
            "payload": {"workflowRunId": "wf-123"},
            "message": "done",
            "result": {
                "workflowRunId": "wf-123",
                "state": "completed",
                "stage": "commit",
                "processed": 18,
                "total": 18,
                "updated": 18,
                "orderApplied": True,
                "message": "Page translation complete",
                "storySummary": "story",
                "imageSummary": "image",
                "characters": [{"name": "Arisa", "gender": "female", "info": "lead"}],
                "openThreads": ["thread"],
                "glossary": [{"term": "A", "translation": "B", "note": ""}],
            },
        },
    )()
    with (
        patch(
            "core.usecases.agent.tool_jobs.create_agent_translate_page_job",
            return_value={
                "job_id": "job-123",
                "queued": True,
                "status": "queued",
                "detail": None,
            },
        ),
        patch(
            "core.usecases.agent.tool_jobs.wait_for_memory_job_terminal",
            return_value=finished_job,
        ),
        patch(
            "core.usecases.agent.tool_jobs._count_page_translation_state",
            side_effect=[
                {"text_box_count": 18, "ocr_filled_count": 18, "translated_count": 0},
                {"text_box_count": 18, "ocr_filled_count": 18, "translated_count": 18},
            ],
        ),
    ):
        result = translate_active_page_tool(
            volume_id="vol-a",
            active_filename="004.jpg",
            filename=None,
        )

    assert result["status"] == "completed"
    assert result["filename"] == "004.jpg"
    assert result["workflow_run_id"] == "wf-123"
    assert result["updated"] == 18
    assert not result["resource_reused"]


def test_translate_active_page_reuses_active_run_without_requeueing() -> None:
    with (
        patch(
            "core.usecases.agent.tool_jobs.create_agent_translate_page_job",
            return_value={
                "job_id": "wf-999",
                "queued": False,
                "status": "reused_active",
                "detail": None,
            },
        ),
        patch(
            "core.usecases.agent.tool_jobs.wait_for_memory_job_terminal",
            return_value=None,
        ),
        patch(
            "core.usecases.agent.tool_jobs.get_workflow_run",
            return_value={"status": "running", "result_json": {"message": "Working"}},
        ),
        patch(
            "core.usecases.agent.tool_jobs._count_page_translation_state",
            return_value={
                "text_box_count": 18,
                "ocr_filled_count": 18,
                "translated_count": 0,
            },
        ),
    ):
        result = translate_active_page_tool(
            volume_id="vol-a",
            active_filename="004.jpg",
            filename=None,
        )

    assert result["status"] == "queued"
    assert result["workflow_run_id"] == "wf-999"
    assert result["resource_reused"]


def test_translate_active_page_short_circuits_when_page_already_translated() -> None:
    page = {
        "boxes": [
            {
                "id": 1,
                "type": "text",
                "orderIndex": 1,
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "text": "jp",
                "translation": "en",
                "note": "",
            }
        ]
    }
    with (
        patch(
            "core.usecases.agent.tool_jobs.load_page",
            return_value=page,
        ) as load_page_mock,
        patch(
            "core.usecases.agent.tool_jobs.create_agent_translate_page_job",
        ) as create_job_mock,
    ):
        result = translate_active_page_tool(
            volume_id="vol-a",
            active_filename="004.jpg",
            filename=None,
        )

    assert result["status"] == "already_translated"
    assert result["filename"] == "004.jpg"
    assert result["already_translated_before"]
    assert result["resource_reused"]
    create_job_mock.assert_not_called()
    load_page_mock.assert_called_once_with("vol-a", "004.jpg")
