# backend-python/infra/jobs/db_page_translation_worker.py
"""Database-backed worker for persisted page-translation workflows."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from threading import Event

from infra.jobs.exceptions import JobCanceled
from infra.jobs.handlers.registry import HANDLERS
from infra.jobs.job_modes import PAGE_TRANSLATION_WORKFLOW_TYPE
from infra.jobs.persisted_job_adapter import (
    PersistedJobStoreAdapter,
    extract_request_payload,
    timestamp_or_now,
)
from infra.jobs.store import Job, JobStatus, JobStore
from infra.jobs.workflow_repo import claim_next_task, get_workflow_run
from infra.logging.correlation import append_correlation, normalize_correlation

logger = logging.getLogger(__name__)

_PAGE_TRANSLATION_STAGE = PAGE_TRANSLATION_WORKFLOW_TYPE
_DEFAULT_LEASE_SECONDS = 60 * 60 * 24
_DEFAULT_IDLE_SLEEP_SECONDS = 0.4
_DEFAULT_ERROR_SLEEP_SECONDS = 1.0


def _page_translation_correlation(
    *,
    component: str,
    workflow_id: str | None = None,
    task_id: str | None = None,
    volume_id: str | None = None,
    filename: str | None = None,
) -> dict[str, str | None]:
    return normalize_correlation(
        {
            "component": component,
            "workflow_run_id": workflow_id,
            "task_run_id": task_id,
            "volume_id": volume_id,
            "filename": filename,
        },
        workflow_type=PAGE_TRANSLATION_WORKFLOW_TYPE,
    )


async def _run_claimed_workflow(
    claimed: dict[str, object],
    *,
    log_store: dict[str, Path],
    shutdown_event: Event,
    signal_store: JobStore,
) -> None:
    workflow_id = str(claimed.get("workflow_id") or "")
    task_id = str(claimed.get("task_id") or "")
    if not workflow_id or not task_id:
        return

    run = get_workflow_run(workflow_id)
    request_payload = extract_request_payload(run)
    payload = claimed.get("input_json")
    if not request_payload and isinstance(payload, dict):
        request_payload = dict(payload)

    created_at = timestamp_or_now(run.get("created_at") if isinstance(run, dict) else None)
    updated_at = timestamp_or_now(run.get("updated_at") if isinstance(run, dict) else None)
    result_json = (
        run.get("result_json")
        if isinstance(run, dict) and isinstance(run.get("result_json"), dict)
        else {}
    )
    job = Job(
        id=workflow_id,
        type=PAGE_TRANSLATION_WORKFLOW_TYPE,
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
        progress=result_json.get("progress")
        if isinstance(result_json.get("progress"), int | float)
        else None,
        message=str(result_json.get("message") or "").strip() or None,
        metrics=result_json.get("metrics")
        if isinstance(result_json.get("metrics"), dict)
        else None,
        warnings=result_json.get("warnings")
        if isinstance(result_json.get("warnings"), list)
        else None,
    )
    adapter = PersistedJobStoreAdapter(
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

    handler = HANDLERS.get(PAGE_TRANSLATION_WORKFLOW_TYPE)
    if handler is None:
        raise RuntimeError("Missing page-translation workflow handler")

    adapter.mark_started()
    if shutdown_event.is_set():
        return
    try:
        result = await handler.run(job, adapter)  # type: ignore[arg-type]
        if shutdown_event.is_set() and not adapter.is_canceled():
            return
        if adapter.is_canceled() or job.status == JobStatus.canceled:
            adapter.finish_canceled(str(job.message or "Canceled"), result=result)
            return
        adapter.finish_success(result if isinstance(result, dict) else {"value": result})
    except JobCanceled as exc:
        if shutdown_event.is_set() and not adapter.is_canceled():
            return
        adapter.finish_canceled(str(exc) or "Canceled")
    except Exception as exc:
        if shutdown_event.is_set() and not adapter.is_canceled():
            return
        error_text = str(exc).strip() or repr(exc)
        logger.exception(
            append_correlation(
                "Page-translation workflow failed",
                _page_translation_correlation(
                    component="jobs.db_page_translation.workflow_error",
                    workflow_id=workflow_id,
                    task_id=task_id,
                    volume_id=str(request_payload.get("volumeId") or ""),
                    filename=str(request_payload.get("filename") or ""),
                ),
                error=error_text,
            )
        )
        adapter.finish_failed(error_text)


async def run_page_translation_db_worker(
    stop_event: Event,
    *,
    log_store: dict[str, Path],
    signal_store: JobStore,
) -> None:
    """Claim and execute queued persisted page-translation workflows."""
    lease_seconds = int(_DEFAULT_LEASE_SECONDS)
    idle_sleep = float(_DEFAULT_IDLE_SLEEP_SECONDS)
    error_sleep = float(_DEFAULT_ERROR_SLEEP_SECONDS)

    while not stop_event.is_set():
        try:
            claimed = await asyncio.to_thread(
                claim_next_task,
                workflow_types=(PAGE_TRANSLATION_WORKFLOW_TYPE,),
                stage=_PAGE_TRANSLATION_STAGE,
                lease_seconds=lease_seconds,
            )
            if claimed is None:
                await asyncio.sleep(idle_sleep)
                continue
            await _run_claimed_workflow(
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
                    "Page-translation DB worker loop failed",
                    _page_translation_correlation(component="jobs.db_page_translation.loop_error"),
                )
            )
            await asyncio.sleep(error_sleep)
