# backend-python/tests/api/test_jobs_service.py
"""Unit tests for jobs service helper functions used by routers.

What is tested:
- Read/control helper behavior for get, cancel, delete, and resume payloads.
- Correct HTTPException behavior for missing/invalid job operations.

How it is tested:
- In-memory `JobStore` instances with deterministic fixture jobs.
- Service functions are exercised directly, outside HTTP request handling.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from api.services.jobs_service import (
    cancel_job,
    delete_job,
    get_job_public,
    get_job_tasks_payload,
    get_resume_agent_payload,
    get_training_log_path,
)
from api.services.jobs_workflow_helpers import workflow_run_to_job_public
from fastapi import HTTPException
from infra.jobs.store import Job, JobStatus, JobStore


@pytest.fixture
def store() -> JobStore:
    return JobStore()


def test_get_job_public_returns_memory_job(store: JobStore) -> None:
    now = store.now()
    store.add_job(
        Job(
            id="job-1",
            type="box_detection",
            status=JobStatus.finished,
            created_at=now,
            updated_at=now,
            payload={"volumeId": "vol", "filename": "001.jpg"},
        )
    )

    public = get_job_public(job_id="job-1", store=store)
    assert public.id == "job-1"
    assert public.type == "box_detection"


def test_get_job_tasks_payload_rejects_non_persisted_memory_job(store: JobStore) -> None:
    now = store.now()
    store.add_job(
        Job(
            id="job-2",
            type="unknown_job",
            status=JobStatus.queued,
            created_at=now,
            updated_at=now,
            payload={},
        )
    )

    with pytest.raises(HTTPException) as raised:
        get_job_tasks_payload(job_id="job-2", store=store)
    assert raised.value.status_code == 400
    assert "task runs" in str(raised.value.detail).lower()


def test_get_training_log_path_reads_persisted_workflow_result(store: JobStore) -> None:
    with patch(
        "api.services.jobs_service.get_workflow_run",
        return_value={
            "id": "wf-train-1",
            "workflow_type": "train_model",
            "result_json": {"log": "/tmp/train.log"},
        },
    ):
        log_path = get_training_log_path(job_id="wf-train-1", store=store)

    assert str(log_path) == "/tmp/train.log"


def test_workflow_run_projection_surfaces_metrics_and_warnings(store: JobStore) -> None:
    public = workflow_run_to_job_public(
        {
            "id": "wf-train-2",
            "workflow_type": "train_model",
            "volume_id": "",
            "filename": "",
            "status": "running",
            "state": "running",
            "error_message": None,
            "created_at": None,
            "updated_at": None,
            "result_json": {
                "request": {"dataset_id": "dataset-1"},
                "progress": 42,
                "message": "Training",
                "metrics": {"device": "cuda:0"},
                "warnings": ["gpu busy"],
            },
        },
        store=store,
    )

    assert public.metrics == {"device": "cuda:0"}
    assert public.warnings == ["gpu busy"]


def test_get_resume_agent_payload_strips_workflow_fields(store: JobStore) -> None:
    now = store.now()
    store.add_job(
        Job(
            id="job-3",
            type="agent_translate_page",
            status=JobStatus.failed,
            created_at=now,
            updated_at=now,
            payload={
                "volumeId": "vol",
                "filename": "002.jpg",
                "workflowRunId": "wf-1",
                "workflowStage": "translate",
            },
        )
    )

    payload = get_resume_agent_payload(job_id="job-3", store=store)
    assert payload["volumeId"] == "vol"
    assert payload["filename"] == "002.jpg"
    assert "workflowRunId" not in payload
    assert "workflowStage" not in payload


@pytest.mark.parametrize("status", ["queued", "running"])
def test_get_resume_agent_payload_rejects_active_persisted_workflow(
    store: JobStore,
    status: str,
) -> None:
    with (
        patch(
            "api.services.jobs_service.get_workflow_run",
            return_value={
                "id": "wf-active-1",
                "workflow_type": "agent_translate_page",
                "status": status,
                "result_json": {"request": {"volumeId": "vol", "filename": "010.jpg"}},
            },
        ),
        pytest.raises(HTTPException) as raised,
    ):
        get_resume_agent_payload(job_id="wf-active-1", store=store)

    assert raised.value.status_code == 409
    assert "already active" in str(raised.value.detail).lower()


def test_cancel_job_marks_memory_job_canceled(store: JobStore) -> None:
    now = store.now()
    store.add_job(
        Job(
            id="job-4",
            type="agent_translate_page",
            status=JobStatus.running,
            created_at=now,
            updated_at=now,
            payload={"volumeId": "vol", "filename": "003.jpg"},
        )
    )

    status = cancel_job(job_id="job-4", store=store)
    assert status == JobStatus.canceled
    stored = store.get_job("job-4")
    if stored is None:
        raise AssertionError("Expected canceled job to remain in store")
    assert stored.status == JobStatus.canceled
    assert stored.message == "Canceled"


def test_cancel_memory_hybrid_job_propagates_to_persisted_workflow(store: JobStore) -> None:
    now = store.now()
    store.add_job(
        Job(
            id="job-4a",
            type="agent_translate_page",
            status=JobStatus.running,
            created_at=now,
            updated_at=now,
            payload={
                "volumeId": "vol",
                "filename": "003a.jpg",
                "workflowRunId": "wf-4a",
            },
        )
    )

    with (
        patch(
            "api.services.jobs_service.cancel_workflow_run", return_value=True
        ) as cancel_run_mock,
        patch("api.services.jobs_service.cancel_pending_tasks") as cancel_tasks_mock,
    ):
        status = cancel_job(job_id="job-4a", store=store)

    assert status == JobStatus.canceled
    stored = store.get_job("job-4a")
    if stored is None:
        raise AssertionError("Expected canceled job to remain in store")
    assert stored.status == JobStatus.canceled
    assert stored.message == "Canceled"
    cancel_run_mock.assert_called_once_with("wf-4a", message="Canceled")
    cancel_tasks_mock.assert_called_once_with("wf-4a")


def test_cancel_job_by_workflow_id_marks_linked_memory_agent_job_canceled(store: JobStore) -> None:
    now = store.now()
    store.add_job(
        Job(
            id="job-4b",
            type="agent_translate_page",
            status=JobStatus.running,
            created_at=now,
            updated_at=now,
            payload={
                "volumeId": "vol",
                "filename": "003b.jpg",
                "workflowRunId": "wf-4b",
            },
        )
    )

    with (
        patch(
            "api.services.jobs_service.get_workflow_run",
            return_value={
                "id": "wf-4b",
                "workflow_type": "agent_translate_page",
                "status": "running",
            },
        ),
        patch(
            "api.services.jobs_service.cancel_workflow_run", return_value=True
        ) as cancel_run_mock,
        patch("api.services.jobs_service.cancel_pending_tasks") as cancel_tasks_mock,
    ):
        status = cancel_job(job_id="wf-4b", store=store)

    assert status == JobStatus.canceled
    stored = store.get_job("job-4b")
    if stored is None:
        raise AssertionError("Expected linked memory job to remain in store")
    assert stored.status == JobStatus.canceled
    assert stored.message == "Canceled"
    cancel_run_mock.assert_called_once_with("wf-4b", message="Canceled")
    cancel_tasks_mock.assert_called_once_with("wf-4b")


def test_delete_job_rejects_running_memory_job(store: JobStore) -> None:
    now = store.now()
    store.add_job(
        Job(
            id="job-5",
            type="agent_translate_page",
            status=JobStatus.running,
            created_at=now,
            updated_at=now,
            payload={"volumeId": "vol", "filename": "004.jpg"},
        )
    )

    with pytest.raises(HTTPException) as raised:
        delete_job(job_id="job-5", store=store)
    assert raised.value.status_code == 409


def test_delete_job_removes_associated_persisted_workflow_for_memory_job(store: JobStore) -> None:
    now = store.now()
    store.add_job(
        Job(
            id="job-6",
            type="agent_translate_page",
            status=JobStatus.canceled,
            created_at=now,
            updated_at=now,
            payload={
                "volumeId": "vol",
                "filename": "005.jpg",
                "workflowRunId": "wf-6",
            },
        )
    )

    with patch("api.services.jobs_service.delete_workflow_run", return_value=True) as delete_run:
        deleted = delete_job(job_id="job-6", store=store)

    assert deleted == 2
    assert store.get_job("job-6") is None
    delete_run.assert_called_once_with("wf-6")
