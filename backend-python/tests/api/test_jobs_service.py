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

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.services.jobs_service import (
    cancel_job,
    delete_job,
    get_job_public,
    get_job_tasks_payload,
    get_resume_agent_payload,
    get_training_log_path,
)
from api.services.jobs_workflow_helpers import workflow_run_to_job_public
from infra.jobs.store import Job, JobStatus, JobStore


class JobsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = JobStore()

    def test_get_job_public_returns_memory_job(self) -> None:
        now = self.store.now()
        self.store.add_job(
            Job(
                id="job-1",
                type="box_detection",
                status=JobStatus.finished,
                created_at=now,
                updated_at=now,
                payload={"volumeId": "vol", "filename": "001.jpg"},
            )
        )

        public = get_job_public(job_id="job-1", store=self.store)
        self.assertEqual(public.id, "job-1")
        self.assertEqual(public.type, "box_detection")

    def test_get_job_tasks_payload_rejects_non_persisted_memory_job(self) -> None:
        # Only persisted workflow job types expose task-run details.
        now = self.store.now()
        self.store.add_job(
            Job(
                id="job-2",
                type="unknown_job",
                status=JobStatus.queued,
                created_at=now,
                updated_at=now,
                payload={},
            )
        )

        with self.assertRaises(HTTPException) as raised:
            get_job_tasks_payload(job_id="job-2", store=self.store)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("task runs", str(raised.exception.detail).lower())

    def test_get_training_log_path_reads_persisted_workflow_result(self) -> None:
        with patch(
            "api.services.jobs_service.get_workflow_run",
            return_value={
                "id": "wf-train-1",
                "workflow_type": "train_model",
                "result_json": {"log": "/tmp/train.log"},
            },
        ):
            log_path = get_training_log_path(job_id="wf-train-1", store=self.store)

        self.assertEqual(str(log_path), "/tmp/train.log")

    def test_workflow_run_projection_surfaces_metrics_and_warnings(self) -> None:
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
            store=self.store,
        )

        self.assertEqual(public.metrics, {"device": "cuda:0"})
        self.assertEqual(public.warnings, ["gpu busy"])

    def test_get_resume_agent_payload_strips_workflow_fields(self) -> None:
        now = self.store.now()
        self.store.add_job(
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

        payload = get_resume_agent_payload(job_id="job-3", store=self.store)
        self.assertEqual(payload["volumeId"], "vol")
        self.assertEqual(payload["filename"], "002.jpg")
        self.assertNotIn("workflowRunId", payload)
        self.assertNotIn("workflowStage", payload)

    def test_cancel_job_marks_memory_job_canceled(self) -> None:
        now = self.store.now()
        self.store.add_job(
            Job(
                id="job-4",
                type="agent_translate_page",
                status=JobStatus.running,
                created_at=now,
                updated_at=now,
                payload={"volumeId": "vol", "filename": "003.jpg"},
            )
        )

        status = cancel_job(job_id="job-4", store=self.store)
        self.assertEqual(status, JobStatus.canceled)
        stored = self.store.get_job("job-4")
        if stored is None:
            raise AssertionError("Expected canceled job to remain in store")
        self.assertEqual(stored.status, JobStatus.canceled)
        self.assertEqual(stored.message, "Canceled")

    def test_delete_job_rejects_running_memory_job(self) -> None:
        now = self.store.now()
        self.store.add_job(
            Job(
                id="job-5",
                type="agent_translate_page",
                status=JobStatus.running,
                created_at=now,
                updated_at=now,
                payload={"volumeId": "vol", "filename": "004.jpg"},
            )
        )

        with self.assertRaises(HTTPException) as raised:
            delete_job(job_id="job-5", store=self.store)
        self.assertEqual(raised.exception.status_code, 409)

    def test_delete_job_removes_associated_persisted_workflow_for_memory_job(self) -> None:
        now = self.store.now()
        self.store.add_job(
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
            deleted = delete_job(job_id="job-6", store=self.store)

        self.assertEqual(deleted, 2)
        self.assertIsNone(self.store.get_job("job-6"))
        delete_run.assert_called_once_with("wf-6")
