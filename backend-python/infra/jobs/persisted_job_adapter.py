# backend-python/infra/jobs/persisted_job_adapter.py
"""Helpers for executing persisted workflows through job-handler adapters."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event
from typing import Any

from infra.jobs.job_modes import TRAIN_MODEL_JOB_TYPE
from infra.jobs.store import Job, JobStatus, JobStore
from infra.jobs.workflow_repo import get_workflow_run, update_task_run, update_workflow_run

_TERMINAL_JOB_STATUSES = {JobStatus.finished, JobStatus.failed, JobStatus.canceled}


def extract_request_payload(run: dict[str, Any] | None) -> dict[str, Any]:
    """Return the persisted request payload embedded in workflow results."""
    if not isinstance(run, dict):
        return {}
    result_json = run.get("result_json")
    if not isinstance(result_json, dict):
        return {}
    request = result_json.get("request")
    if not isinstance(request, dict):
        return {}
    return dict(request)


def timestamp_or_now(value: Any) -> float:
    """Convert persisted timestamps to epoch seconds with a safe fallback."""
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            pass
    return time.time()


def _job_to_result_json(
    *,
    job: Job,
    request_payload: dict[str, Any],
    log_store: dict[str, Path],
    include_request: bool,
) -> dict[str, Any]:
    result_json: dict[str, Any] = {}
    if include_request:
        result_json["request"] = dict(request_payload)
    if isinstance(job.result, dict):
        result_json.update(job.result)
    if job.progress is not None:
        result_json["progress"] = float(job.progress)
    if job.message:
        result_json["message"] = str(job.message)
    if job.metrics is not None:
        result_json["metrics"] = dict(job.metrics)
    if job.warnings:
        result_json["warnings"] = list(job.warnings)
    if job.error:
        result_json["error_message"] = str(job.error)
    if job.type == TRAIN_MODEL_JOB_TYPE:
        log_path = log_store.get(job.id)
        if log_path is not None:
            result_json["log"] = str(log_path)
    return result_json


def _workflow_status(job: Job) -> str:
    if job.status == JobStatus.finished:
        return "completed"
    if job.status == JobStatus.failed:
        return "failed"
    if job.status == JobStatus.canceled:
        return "canceled"
    if job.status == JobStatus.running:
        return "running"
    return "queued"


class PersistedJobStoreAdapter:
    """JobStore-like adapter that persists handler updates back into workflow rows."""

    def __init__(
        self,
        *,
        workflow_id: str,
        task_id: str,
        request_payload: dict[str, Any],
        job: Job,
        log_store: dict[str, Path],
        shutdown_event: Event,
        signal_store: JobStore,
    ) -> None:
        self.workflow_id = workflow_id
        self.task_id = task_id
        self.request_payload = dict(request_payload)
        self.job = job
        self.logs = log_store
        self.shutdown_event = shutdown_event
        self._signal_store = signal_store

    def get_job(self, job_id: str) -> Job | None:
        normalized_job_id = str(job_id or "").strip()
        if normalized_job_id == str(self.job.id):
            return self.job
        return None

    def is_canceled(self) -> bool:
        run = get_workflow_run(self.workflow_id)
        if not isinstance(run, dict):
            return False
        if (
            bool(run.get("cancel_requested"))
            or str(run.get("status") or "").strip().lower() == "canceled"
        ):
            self.job.status = JobStatus.canceled
            if not self.job.message:
                self.job.message = "Canceled"
            return True
        return False

    def should_stop(self) -> bool:
        return self.shutdown_event.is_set() or self.is_canceled()

    def _persist(self, *, finished: bool) -> None:
        if self.is_canceled() and self.job.status not in _TERMINAL_JOB_STATUSES:
            self.job.status = JobStatus.canceled
        status = _workflow_status(self.job)
        error_text: str | None = None
        if status == "failed":
            error_text = str(self.job.error or self.job.message or "Failed")
        elif status == "canceled":
            error_text = str(self.job.message or "Canceled")

        update_task_run(
            self.task_id,
            status=status,
            error_code="cancel_requested" if status == "canceled" else None,
            error_detail=error_text,
            result_json=_job_to_result_json(
                job=self.job,
                request_payload=self.request_payload,
                log_store=self.logs,
                include_request=False,
            ),
            finished=finished,
        )
        update_workflow_run(
            self.workflow_id,
            state=status,
            status=status,
            error_message=error_text,
            result_json=_job_to_result_json(
                job=self.job,
                request_payload=self.request_payload,
                log_store=self.logs,
                include_request=True,
            ),
        )
        self._signal_store.broadcast_snapshot()

    def mark_started(self) -> None:
        if not self.job.message:
            self.job.message = "Running"
        self.job.status = JobStatus.canceled if self.is_canceled() else JobStatus.running
        self._persist(finished=False)

    def update_job(self, job: Job, **updates: Any) -> Job:
        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = time.time()
        if self.is_canceled() and job.status not in _TERMINAL_JOB_STATUSES:
            job.status = JobStatus.canceled
        self._persist(finished=False)
        return job

    def finish_success(self, result: dict[str, Any]) -> None:
        self.job.result = dict(result)
        self.job.error = None
        self.job.status = JobStatus.canceled if self.is_canceled() else JobStatus.finished
        if self.job.status == JobStatus.finished:
            self.job.progress = (
                100 if self.job.progress is None else max(100.0, float(self.job.progress))
            )
            self.job.message = self.job.message or "Completed"
        self._persist(finished=True)

    def finish_failed(self, error_text: str) -> None:
        self.job.status = JobStatus.canceled if self.is_canceled() else JobStatus.failed
        self.job.error = None if self.job.status == JobStatus.canceled else error_text
        self.job.message = "Canceled" if self.job.status == JobStatus.canceled else error_text[:160]
        self._persist(finished=True)

    def finish_canceled(self, message: str, *, result: dict[str, Any] | None = None) -> None:
        if isinstance(result, dict):
            self.job.result = dict(result)
        self.job.status = JobStatus.canceled
        self.job.error = None
        self.job.message = str(message or "Canceled")
        self._persist(finished=True)
