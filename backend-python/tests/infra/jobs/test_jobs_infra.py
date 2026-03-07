# backend-python/tests/infra/jobs/test_jobs_infra.py
"""Unit tests for in-memory jobs store and generic worker behavior.

What is tested:
- Job serialization remains SSE/JSON safe.
- Unknown job handlers fail deterministically with expected job status updates.

How it is tested:
- In-process async worker loop with short-lived test jobs.
- Uses only the in-memory store; no database-backed queue access.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from unittest.mock import patch

import pytest

from core.workflows.agent_translate_page.types import (
    AgentTranslateWorkflowSnapshot,
    WorkflowState,
)
from infra.jobs.handlers.agent import AgentTranslatePageJobHandler
from infra.jobs.store import Job, JobStatus, JobStore
from infra.jobs.worker import job_worker


async def _run_unknown_job() -> Job:
    store = JobStore()
    now = store.now()
    job = Job(
        id="test-job",
        type="unknown_job",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload={},
        result=None,
        error=None,
    )
    store.add_job(job)
    worker_task = asyncio.create_task(job_worker(store))
    stored: Job | None = None
    try:
        await store.queue.put(job.id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 2.0
        while loop.time() < deadline:
            await asyncio.sleep(0.01)
            stored = store.get_job(job.id)
            # Poll to avoid race with async worker update timing.
            if stored and stored.status in (JobStatus.failed, JobStatus.finished):
                break
        if not stored or stored.status not in (JobStatus.failed, JobStatus.finished):
            raise AssertionError("Job did not finish in time")
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
    if stored is None:
        raise AssertionError("Job missing from store")
    return stored


def test_format_sse_sanitizes_nonfinite() -> None:
    store = JobStore()
    payload = {
        "value": float("nan"),
        "items": [float("inf"), 1.0],
        "nested": {"neg_inf": float("-inf")},
    }
    data = store.format_sse(payload)
    assert data.startswith("data: ")
    json_text = data.replace("data: ", "", 1).strip()
    parsed = json.loads(json_text)
    assert parsed["value"] is None
    assert parsed["items"][0] is None
    assert parsed["items"][1] == 1.0
    assert parsed["nested"]["neg_inf"] is None


def test_update_job_does_not_resurrect_removed_job() -> None:
    store = JobStore()
    now = store.now()
    job = Job(
        id="deleted-job",
        type="box_detection",
        status=JobStatus.canceled,
        created_at=now,
        updated_at=now,
        payload={},
    )
    store.add_job(job)
    assert store.remove_job(job.id)

    store.update_job(job, progress=90, message="Should stay gone")

    assert store.get_job(job.id) is None


@pytest.mark.asyncio
async def test_canceled_agent_job_ignores_late_progress() -> None:
    store = JobStore()
    now = store.now()
    job = Job(
        id="agent-job",
        type="agent_translate_page",
        status=JobStatus.running,
        created_at=now,
        updated_at=now,
        payload={"volumeId": "vol", "filename": "001.jpg"},
        progress=10,
        message="Running",
    )
    store.add_job(job)

    async def _fake_workflow(*, on_progress, **_: object) -> dict[str, object]:
        store.update_job(job, status=JobStatus.canceled, progress=100, message="Canceled")
        on_progress(
            AgentTranslateWorkflowSnapshot(
                state=WorkflowState.ocr_running,
                stage="ocr_running",
                progress=55,
                message="Late progress",
                detection_profile_id=None,
                detected_boxes=3,
                workflow_run_id="wf-1",
            )
        )
        return {"state": "canceled", "message": "Canceled"}

    handler = AgentTranslatePageJobHandler()
    with patch(
        "infra.jobs.handlers.agent.run_agent_translate_page_workflow",
        side_effect=_fake_workflow,
    ):
        await handler.run(job, store)

    stored = store.get_job(job.id)
    if stored is None:
        raise AssertionError("Expected canceled job to remain in store")
    assert stored.status == JobStatus.canceled
    assert stored.progress == 100
    assert stored.message == "Canceled"
    assert "workflowRunId" not in stored.payload


def test_unknown_job_type_fails() -> None:
    result_job = asyncio.run(_run_unknown_job())
    assert result_job.status == JobStatus.failed
    assert "Unknown job type" in (result_job.error or "")
