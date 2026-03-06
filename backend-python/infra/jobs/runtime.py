# backend-python/infra/jobs/runtime.py
"""Jobs runtime lifecycle management and worker startup/shutdown."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Event
from typing import Any, TypeVar
from uuid import uuid4

from infra.jobs.db_ocr_worker import run_ocr_db_worker
from infra.jobs.db_translate_worker import run_translate_db_worker
from infra.jobs.job_modes import AGENT_WORKFLOW_TYPE
from infra.jobs.store import Job, JobStatus, JobStore
from infra.jobs.worker import job_worker
from infra.jobs.workflow_repo import mark_running_workflows_interrupted
from infra.logging.correlation import append_correlation, normalize_correlation

logger = logging.getLogger(__name__)
T = TypeVar("T")

STORE = JobStore()

_worker_started = False
_worker_task: asyncio.Task | None = None
_db_ocr_worker_task: asyncio.Task | None = None
_db_translate_worker_task: asyncio.Task | None = None
_runtime_lock = asyncio.Lock()
_runtime_loop: asyncio.AbstractEventLoop | None = None


async def _run_ocr_db_worker_supervisor(shutdown_event: Event) -> None:
    base_corr = {"component": "jobs.runtime.ocr_supervisor"}
    backoff_seconds = 1.0
    max_backoff_seconds = 10.0
    while not shutdown_event.is_set():
        try:
            await run_ocr_db_worker(shutdown_event)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                append_correlation(
                    "OCR DB worker crashed; restarting",
                    base_corr,
                    backoff_seconds=round(backoff_seconds, 1),
                )
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)


async def _run_translate_db_worker_supervisor(shutdown_event: Event) -> None:
    base_corr = {"component": "jobs.runtime.translate_supervisor"}
    backoff_seconds = 1.0
    max_backoff_seconds = 10.0
    while not shutdown_event.is_set():
        try:
            await run_translate_db_worker(shutdown_event)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                append_correlation(
                    "Translate DB worker crashed; restarting",
                    base_corr,
                    backoff_seconds=round(backoff_seconds, 1),
                )
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)


def _cancel_running_memory_jobs() -> None:
    for job in list(STORE.jobs.values()):
        if job.status == JobStatus.running:
            STORE.update_job(job, status=JobStatus.canceled, message="Canceled (shutdown)")


async def start_jobs_runtime() -> None:
    global _worker_started, _worker_task, _db_ocr_worker_task, _db_translate_worker_task, _runtime_loop
    async with _runtime_lock:
        if _worker_started:
            return

        _worker_started = True
        _runtime_loop = asyncio.get_running_loop()
        STORE.shutdown_event.clear()

        try:
            mark_running_workflows_interrupted(
                workflow_type=AGENT_WORKFLOW_TYPE,
                message="Interrupted by backend restart",
            )
        except Exception:
            logger.exception(
                append_correlation(
                    "Failed to mark running workflows interrupted at startup",
                    {"component": "jobs.runtime.startup"},
                    workflow_type=AGENT_WORKFLOW_TYPE,
                )
            )

        logger.info(
            append_correlation(
                "Jobs runtime started",
                normalize_correlation({"component": "jobs.runtime"}),
            )
        )

        _worker_task = asyncio.create_task(job_worker(STORE), name="jobs-worker")
        _db_ocr_worker_task = asyncio.create_task(
            _run_ocr_db_worker_supervisor(STORE.shutdown_event),
            name="jobs-db-ocr-supervisor",
        )
        _db_translate_worker_task = asyncio.create_task(
            _run_translate_db_worker_supervisor(STORE.shutdown_event),
            name="jobs-db-translate-supervisor",
        )


async def stop_jobs_runtime() -> None:
    global _worker_started, _worker_task, _db_ocr_worker_task, _db_translate_worker_task, _runtime_loop
    async with _runtime_lock:
        if not _worker_started:
            return

        _worker_started = False
        STORE.shutdown_event.set()

        tasks = [
            task
            for task in (_worker_task, _db_ocr_worker_task, _db_translate_worker_task)
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        _worker_task = None
        _db_ocr_worker_task = None
        _db_translate_worker_task = None
        _runtime_loop = None
        _cancel_running_memory_jobs()
        logger.info(
            append_correlation(
                "Jobs runtime stopped",
                normalize_correlation({"component": "jobs.runtime"}),
            )
        )


def is_jobs_runtime_started() -> bool:
    return _worker_started


def _normalize_timeout(timeout_seconds: float) -> float:
    return max(0.1, float(timeout_seconds))


def _runtime_loop_or_raise() -> asyncio.AbstractEventLoop:
    runtime_loop = _runtime_loop
    if runtime_loop is None or not runtime_loop.is_running():
        raise RuntimeError("Jobs runtime is not running")
    return runtime_loop


def _current_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _run_on_runtime_loop(coro: Coroutine[Any, Any, T], *, timeout_seconds: float) -> T:
    runtime_loop = _runtime_loop_or_raise()
    if _current_loop() is runtime_loop:
        raise RuntimeError("Cannot block on jobs runtime loop thread")

    future = asyncio.run_coroutine_threadsafe(coro, runtime_loop)
    try:
        return future.result(timeout=_normalize_timeout(timeout_seconds))
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError("Timed out waiting for jobs runtime operation") from exc


def _clone_job(job: Job | None) -> Job | None:
    if job is None:
        return None
    return job.model_copy(deep=True)


def _create_and_enqueue_memory_job_now(
    *,
    job_type: str,
    payload: dict[str, Any],
    progress: float | None = None,
    message: str | None = None,
) -> str:
    job_id = str(uuid4())
    now = STORE.now()
    job = Job(
        id=job_id,
        type=job_type,
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=dict(payload or {}),
        result=None,
        error=None,
        progress=progress,
        message=message,
        metrics=None,
        warnings=None,
    )
    STORE.add_job(job)

    try:
        STORE.queue.put_nowait(job_id)
    except Exception as exc:
        error_text = str(exc).strip() or "Failed to enqueue memory job"
        STORE.update_job(
            job,
            status=JobStatus.failed,
            error=error_text,
            message=error_text[:160],
        )
        raise RuntimeError(error_text) from exc
    return job_id


async def _create_and_enqueue_memory_job_on_runtime_loop(
    *,
    job_type: str,
    payload: dict[str, Any],
    progress: float | None = None,
    message: str | None = None,
) -> str:
    return _create_and_enqueue_memory_job_now(
        job_type=job_type,
        payload=payload,
        progress=progress,
        message=message,
    )


async def _enqueue_existing_job_on_runtime_loop(job_id: str) -> None:
    if STORE.get_job(job_id) is None:
        raise KeyError(f"Job {job_id} not found")
    STORE.queue.put_nowait(job_id)


async def _wait_for_memory_job_terminal_on_runtime_loop(
    *,
    job_id: str,
    timeout_seconds: float,
    poll_seconds: float,
) -> Job | None:
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    poll_interval = max(0.01, float(poll_seconds))
    job = STORE.get_job(job_id)

    while (
        job is not None
        and job.status in {JobStatus.queued, JobStatus.running}
        and time.monotonic() < deadline
    ):
        await asyncio.sleep(poll_interval)
        job = STORE.get_job(job_id)

    return _clone_job(job)


def enqueue_memory_job_id(job_id: str, *, timeout_seconds: float = 2.0) -> None:
    """
    Enqueue a memory-job ID onto the jobs runtime queue from any thread.

    Agent tools run in a separate runner thread/loop, so direct queue writes can
    bypass the main jobs loop. This helper always schedules onto the runtime loop.
    """
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        raise ValueError("job_id is required")

    runtime_loop = _runtime_loop_or_raise()
    if _current_loop() is runtime_loop:
        if STORE.get_job(normalized_job_id) is None:
            raise KeyError(f"Job {normalized_job_id} not found")
        STORE.queue.put_nowait(normalized_job_id)
        return

    _run_on_runtime_loop(
        _enqueue_existing_job_on_runtime_loop(normalized_job_id),
        timeout_seconds=timeout_seconds,
    )


def create_and_enqueue_memory_job(
    *,
    job_type: str,
    payload: dict[str, Any],
    progress: float | None = None,
    message: str | None = None,
    timeout_seconds: float = 2.0,
) -> str:
    """
    Create and enqueue a memory job atomically on the jobs runtime loop.

    This avoids cross-thread `JobStore` mutations and prevents orphaned queued jobs
    when enqueueing fails.
    """
    runtime_loop = _runtime_loop_or_raise()
    if _current_loop() is runtime_loop:
        return _create_and_enqueue_memory_job_now(
            job_type=job_type,
            payload=payload,
            progress=progress,
            message=message,
        )

    return _run_on_runtime_loop(
        _create_and_enqueue_memory_job_on_runtime_loop(
            job_type=job_type,
            payload=payload,
            progress=progress,
            message=message,
        ),
        timeout_seconds=timeout_seconds,
    )


def wait_for_memory_job_terminal(
    *,
    job_id: str,
    timeout_seconds: float,
    poll_seconds: float = 0.2,
) -> Job | None:
    """
    Wait for a memory job to leave queued/running, returning an immutable snapshot.
    """
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        raise ValueError("job_id is required")
    runtime_loop = _runtime_loop_or_raise()
    if _current_loop() is runtime_loop:
        raise RuntimeError(
            "wait_for_memory_job_terminal cannot be called on the jobs runtime loop thread"
        )

    # Give the cross-thread future a small buffer above the internal wait timeout.
    future_timeout = max(1.0, float(timeout_seconds)) + 1.0
    return _run_on_runtime_loop(
        _wait_for_memory_job_terminal_on_runtime_loop(
            job_id=normalized_job_id,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        ),
        timeout_seconds=future_timeout,
    )
