# backend-python/infra/jobs/db_utility_worker.py
"""Database-backed worker for persisted single-task utility workflows."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from threading import Event
from typing import Any

from infra.jobs.handlers.registry import HANDLERS
from infra.jobs.job_modes import TRAIN_MODEL_JOB_TYPE, UTILITY_WORKFLOW_TYPES
from infra.jobs.store import Job, JobStatus, JobStore
from infra.jobs.workflow_repo import (
    claim_next_task,
    get_workflow_run,
    update_task_run,
    update_workflow_run,
)
from infra.jobs.workflow_repo import (
    recover_running_tasks_for_startup as repo_recover_running_tasks_for_startup,
)
from infra.logging.correlation import append_correlation, normalize_correlation
from infra.training.job_runner import TrainingCanceled

logger = logging.getLogger(__name__)

_TERMINAL_JOB_STATUSES = {JobStatus.finished, JobStatus.failed, JobStatus.canceled}
_DEFAULT_LEASE_SECONDS = 60 * 60 * 24
_DEFAULT_IDLE_SLEEP_SECONDS = 0.4
_DEFAULT_ERROR_SLEEP_SECONDS = 1.0


def _utility_correlation(
    *,
    component: str,
    workflow_id: str | None = None,
    task_id: str | None = None,
    workflow_type: str | None = None,
    volume_id: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    return normalize_correlation(
        {
            "component": component,
            "workflow_run_id": workflow_id,
            "task_run_id": task_id,
            "volume_id": volume_id,
            "filename": filename,
        },
        workflow_type=workflow_type,
    )


def _extract_request_payload(run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    result_json = run.get("result_json")
    if not isinstance(result_json, dict):
        return {}
    request = result_json.get("request")
    if not isinstance(request, dict):
        return {}
    return dict(request)


def _timestamp_or_now(value: Any) -> float:
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            pass
    return time.time()


def _to_result_json(
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


class _PersistedJobStoreAdapter:
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

    def is_canceled(self) -> bool:
        run = get_workflow_run(self.workflow_id)
        if not isinstance(run, dict):
            return False
        if bool(run.get("cancel_requested")) or str(run.get("status") or "").strip().lower() == "canceled":
            self.job.status = JobStatus.canceled
            if not self.job.message:
                self.job.message = "Canceled"
            return True
        return False

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
            result_json=_to_result_json(
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
            result_json=_to_result_json(
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
            self.job.progress = 100 if self.job.progress is None else max(100.0, float(self.job.progress))
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


def _recover_running_tasks() -> int:
    changed = 0
    for workflow_type in UTILITY_WORKFLOW_TYPES:
        changed += repo_recover_running_tasks_for_startup(
            workflow_types=(workflow_type,),
            stage=workflow_type,
        )
    return changed


def _claim_next_utility_task(
    *,
    lease_seconds: int,
    start_index: int,
) -> tuple[dict[str, Any] | None, int]:
    for offset in range(len(UTILITY_WORKFLOW_TYPES)):
        workflow_type = UTILITY_WORKFLOW_TYPES[(start_index + offset) % len(UTILITY_WORKFLOW_TYPES)]
        claimed = claim_next_task(
            workflow_types=(workflow_type,),
            stage=workflow_type,
            lease_seconds=lease_seconds,
        )
        if claimed:
            payload = claimed.get("input_json") if isinstance(claimed.get("input_json"), dict) else {}
            out = dict(claimed)
            out["workflow_type"] = workflow_type
            out["payload"] = dict(payload)
            return out, (start_index + offset + 1) % len(UTILITY_WORKFLOW_TYPES)
    return None, start_index


async def _run_claimed_task(
    claimed: dict[str, Any],
    *,
    log_store: dict[str, Path],
    shutdown_event: Event,
    signal_store: JobStore,
) -> None:
    workflow_id = str(claimed.get("workflow_id") or "")
    task_id = str(claimed.get("task_id") or "")
    workflow_type = str(claimed.get("workflow_type") or "")
    if not workflow_id or not task_id or not workflow_type:
        return

    run = get_workflow_run(workflow_id)
    request_payload = _extract_request_payload(run)
    if not request_payload:
        payload = claimed.get("payload")
        if isinstance(payload, dict):
            request_payload = dict(payload)

    created_at = _timestamp_or_now(run.get("created_at") if isinstance(run, dict) else None)
    updated_at = _timestamp_or_now(run.get("updated_at") if isinstance(run, dict) else None)
    result_json = run.get("result_json") if isinstance(run, dict) and isinstance(run.get("result_json"), dict) else {}
    job = Job(
        id=workflow_id,
        type=workflow_type,
        status=JobStatus.running,
        created_at=created_at,
        updated_at=updated_at,
        payload={
            **request_payload,
            "workflowRunId": workflow_id,
            "taskRunId": task_id,
        },
        result=None,
        error=None,
        progress=result_json.get("progress") if isinstance(result_json.get("progress"), int | float) else None,
        message=str(result_json.get("message") or "").strip() or None,
        metrics=result_json.get("metrics") if isinstance(result_json.get("metrics"), dict) else None,
        warnings=result_json.get("warnings") if isinstance(result_json.get("warnings"), list) else None,
    )
    adapter = _PersistedJobStoreAdapter(
        workflow_id=workflow_id,
        task_id=task_id,
        request_payload=request_payload,
        job=job,
        log_store=log_store,
        shutdown_event=shutdown_event,
        signal_store=signal_store,
    )
    if adapter.is_canceled():
        adapter.finish_canceled("Canceled")
        return

    handler = HANDLERS.get(workflow_type)
    if handler is None:
        raise RuntimeError(f"Unknown utility workflow type: {workflow_type}")

    adapter.mark_started()
    try:
        result = await handler.run(job, adapter)  # type: ignore[arg-type]
        if adapter.is_canceled() or job.status == JobStatus.canceled:
            adapter.finish_canceled(str(job.message or "Canceled"), result=result)
            return
        adapter.finish_success(result if isinstance(result, dict) else {"value": result})
    except TrainingCanceled as exc:
        adapter.finish_canceled(str(exc) or "Canceled")
    except Exception as exc:
        error_text = str(exc).strip() or repr(exc)
        logger.exception(
            append_correlation(
                "Utility workflow failed",
                _utility_correlation(
                    component="jobs.db_utility.task_error",
                    workflow_id=workflow_id,
                    task_id=task_id,
                    workflow_type=workflow_type,
                    volume_id=str(request_payload.get("volumeId") or ""),
                    filename=str(request_payload.get("filename") or ""),
                ),
                error=error_text,
            )
        )
        adapter.finish_failed(error_text)


async def run_utility_db_worker(
    stop_event: Event,
    *,
    log_store: dict[str, Path],
    signal_store: JobStore,
) -> None:
    lease_seconds = int(_DEFAULT_LEASE_SECONDS)
    idle_sleep = float(_DEFAULT_IDLE_SLEEP_SECONDS)
    error_sleep = float(_DEFAULT_ERROR_SLEEP_SECONDS)

    try:
        recovered = await asyncio.to_thread(_recover_running_tasks)
    except Exception:
        logger.exception(
            append_correlation(
                "Failed to recover running utility tasks on startup",
                {"component": "jobs.db_utility.startup"},
            )
        )
        recovered = 0
    if recovered > 0:
        logger.info(
            append_correlation(
                "Recovered interrupted utility tasks",
                {"component": "jobs.db_utility.startup"},
                recovered=recovered,
            )
        )

    claim_index = 0
    while not stop_event.is_set():
        try:
            claimed, claim_index = await asyncio.to_thread(
                _claim_next_utility_task,
                lease_seconds=lease_seconds,
                start_index=claim_index,
            )
        except Exception:
            logger.exception(
                append_correlation(
                    "Utility DB worker failed to claim task",
                    {"component": "jobs.db_utility.claim"},
                )
            )
            await asyncio.sleep(error_sleep)
            continue

        if not claimed:
            await asyncio.sleep(idle_sleep)
            continue

        try:
            await _run_claimed_task(
                claimed,
                log_store=log_store,
                shutdown_event=stop_event,
                signal_store=signal_store,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                append_correlation(
                    "Utility DB worker failed claimed task",
                    _utility_correlation(
                        component="jobs.db_utility.task",
                        workflow_id=str(claimed.get("workflow_id") or ""),
                        task_id=str(claimed.get("task_id") or ""),
                        workflow_type=str(claimed.get("workflow_type") or ""),
                        volume_id=str(claimed.get("payload", {}).get("volumeId") or ""),
                        filename=str(claimed.get("payload", {}).get("filename") or ""),
                    ),
                )
            )
            await asyncio.sleep(error_sleep)
