# backend-python/infra/jobs/worker.py
"""Main async worker loop that executes queued in-memory jobs."""

from __future__ import annotations

import logging
from typing import Any

from infra.jobs.exceptions import JobCanceled
from infra.jobs.job_modes import PERSISTED_WORKFLOW_TYPES
from infra.jobs.workflow_repo import update_workflow_run
from infra.logging.correlation import append_correlation, normalize_correlation

from .handlers.registry import HANDLERS
from .store import Job, JobStatus, JobStore

logger = logging.getLogger(__name__)


def _job_correlation(job: Job, *, workflow_run_id: str | None = None) -> dict[str, Any]:
    return normalize_correlation(
        {
            "component": "jobs.worker",
            "job_id": job.id,
            "workflow_run_id": workflow_run_id or _extract_workflow_run_id(job),
            "volume_id": job.payload.get("volumeId") or job.payload.get("volume_id"),
            "filename": job.payload.get("filename"),
        }
    )


def _extract_workflow_run_id(job: Job, result: dict[str, Any] | None = None) -> str | None:
    payload = dict(job.payload or {})
    workflow_run_id = payload.get("workflowRunId")
    if isinstance(workflow_run_id, str) and workflow_run_id.strip():
        return workflow_run_id.strip()
    if isinstance(result, dict):
        result_workflow_id = result.get("workflowRunId")
        if isinstance(result_workflow_id, str) and result_workflow_id.strip():
            return result_workflow_id.strip()
    return None


def _sync_terminal_workflow_status(
    *,
    job: Job,
    terminal_status: str,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    if job.type not in PERSISTED_WORKFLOW_TYPES:
        return
    workflow_run_id = _extract_workflow_run_id(job, result=result)
    if not workflow_run_id:
        return

    try:
        update_workflow_run(
            workflow_run_id,
            state=terminal_status,
            status=terminal_status,
            error_message=error_message,
        )
    except Exception:
        logger.exception(
            append_correlation(
                "Failed to sync workflow terminal status",
                normalize_correlation(
                    {
                        "component": "jobs.worker.workflow_sync",
                        "workflow_run_id": workflow_run_id,
                        "job_id": job.id,
                    }
                ),
            )
        )


async def job_worker(store: JobStore) -> None:
    """
    In-process worker that pulls job IDs from the store queue
    and processes them one by one.
    """
    while True:
        job_id = await store.queue.get()
        job = store.get_job(job_id)
        if job is None:
            store.queue.task_done()
            continue
        if job.status == JobStatus.canceled:
            store.queue.task_done()
            continue

        try:
            store.update_job(job, status=JobStatus.running)
            logger.info(
                append_correlation(
                    "Job started",
                    _job_correlation(job),
                    job_type=job.type,
                )
            )

            handler = HANDLERS.get(job.type)
            if handler is None:
                raise RuntimeError(f"Unknown job type: {job.type}")

            result = await handler.run(job, store)

            if job.status != JobStatus.canceled:
                store.update_job(job, status=JobStatus.finished, result=result)
                logger.info(
                    append_correlation(
                        "Job finished",
                        _job_correlation(
                            job, workflow_run_id=_extract_workflow_run_id(job, result)
                        ),
                        job_type=job.type,
                    )
                )
                _sync_terminal_workflow_status(
                    job=job,
                    terminal_status="completed",
                    result=result if isinstance(result, dict) else None,
                )
            else:
                _sync_terminal_workflow_status(
                    job=job,
                    terminal_status="canceled",
                    result=result if isinstance(result, dict) else None,
                    error_message="Canceled",
                )

        except JobCanceled as exc:
            if job.status != JobStatus.canceled:
                store.update_job(job, status=JobStatus.canceled, message=str(exc) or "Canceled")
            logger.warning(
                append_correlation(
                    "Job canceled",
                    _job_correlation(job),
                    job_type=job.type,
                )
            )
            _sync_terminal_workflow_status(
                job=job,
                terminal_status="canceled",
                error_message=str(exc) or "Canceled",
            )
        except Exception as exc:
            error_text = str(exc).strip() or repr(exc)
            logger.exception(
                append_correlation(
                    f"Job failed: {error_text}",
                    _job_correlation(job),
                    job_type=job.type,
                )
            )
            if job.status != JobStatus.canceled:
                store.update_job(
                    job,
                    status=JobStatus.failed,
                    error=error_text,
                    message=error_text[:160],
                )
                _sync_terminal_workflow_status(
                    job=job,
                    terminal_status="failed",
                    error_message=error_text,
                )
            else:
                _sync_terminal_workflow_status(
                    job=job,
                    terminal_status="canceled",
                    error_message="Canceled",
                )
        finally:
            store.queue.task_done()
