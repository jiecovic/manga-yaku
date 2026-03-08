# backend-python/tests/infra/jobs/test_db_page_translation_worker.py
"""Unit tests for the persisted page-translation workflow worker."""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest
from infra.jobs import db_page_translation_worker
from infra.jobs.store import JobStore


@pytest.mark.asyncio
async def test_run_claimed_workflow_executes_agent_handler_with_persisted_ids() -> None:
    signal_store = JobStore()
    claimed = {
        "workflow_id": "wf-agent-1",
        "task_id": "task-agent-1",
        "input_json": {"volumeId": "vol-a", "filename": "001.jpg"},
    }
    run_record = {
        "id": "wf-agent-1",
        "workflow_type": "page_translation",
        "volume_id": "vol-a",
        "filename": "001.jpg",
        "status": "running",
        "cancel_requested": False,
        "created_at": None,
        "updated_at": None,
        "result_json": {
            "request": {"volumeId": "vol-a", "filename": "001.jpg"},
            "progress": 0,
            "message": "Queued",
        },
    }
    captured_payload: dict[str, object] = {}

    async def _fake_workflow(*, payload, on_progress, is_canceled):
        captured_payload.update(payload)
        assert not is_canceled()
        on_progress(
            type(
                "Snapshot",
                (),
                {
                    "workflow_run_id": "wf-agent-1",
                    "stage": "detect_boxes",
                    "progress": 15,
                    "message": "Detecting text boxes",
                },
            )()
        )
        return {
            "workflowRunId": "wf-agent-1",
            "state": "completed",
            "stage": "commit",
            "processed": 2,
            "total": 2,
            "updated": 2,
            "orderApplied": True,
            "message": "Page translation complete",
        }

    with (
        patch(
            "infra.jobs.handlers.page_translation.run_page_translation_workflow",
            side_effect=_fake_workflow,
        ),
        patch("infra.jobs.persisted_job_adapter.get_workflow_run", return_value=run_record),
        patch.object(db_page_translation_worker, "get_workflow_run", return_value=run_record),
        patch("infra.jobs.persisted_job_adapter.update_task_run") as update_task_mock,
        patch("infra.jobs.persisted_job_adapter.update_workflow_run") as update_workflow_mock,
    ):
        await db_page_translation_worker._run_claimed_workflow(
            claimed,
            log_store={},
            shutdown_event=threading.Event(),
            signal_store=signal_store,
        )

    assert captured_payload["workflowRunId"] == "wf-agent-1"
    assert captured_payload["taskRunId"] == "task-agent-1"
    assert update_task_mock.call_args_list[-1].kwargs["status"] == "completed"
    assert update_workflow_mock.call_args_list[-1].kwargs["status"] == "completed"
    assert (
        update_workflow_mock.call_args_list[-1].kwargs["result_json"]["workflowRunId"]
        == "wf-agent-1"
    )
