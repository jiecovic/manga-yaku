from __future__ import annotations

import asyncio
import logging
from threading import Event

from infra.db.workflow_store import mark_running_workflows_interrupted
from infra.jobs.db_ocr_worker import run_ocr_db_worker
from infra.jobs.db_translate_worker import run_translate_db_worker
from infra.jobs.store import JobStatus, JobStore
from infra.jobs.worker import job_worker

logger = logging.getLogger(__name__)

_AGENT_WORKFLOW_TYPE = "agent_translate_page"

STORE = JobStore()

_worker_started = False
_worker_task: asyncio.Task | None = None
_db_ocr_worker_task: asyncio.Task | None = None
_db_translate_worker_task: asyncio.Task | None = None
_runtime_lock = asyncio.Lock()


async def _run_ocr_db_worker_supervisor(shutdown_event: Event) -> None:
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
                "OCR DB worker crashed; restarting in %.1fs",
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)


async def _run_translate_db_worker_supervisor(shutdown_event: Event) -> None:
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
                "Translate DB worker crashed; restarting in %.1fs",
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)


def _cancel_running_memory_jobs() -> None:
    for job in list(STORE.jobs.values()):
        if job.status == JobStatus.running:
            STORE.update_job(job, status=JobStatus.canceled, message="Canceled (shutdown)")


async def start_jobs_runtime() -> None:
    global _worker_started, _worker_task, _db_ocr_worker_task, _db_translate_worker_task
    async with _runtime_lock:
        if _worker_started:
            return

        _worker_started = True
        STORE.shutdown_event.clear()

        try:
            mark_running_workflows_interrupted(
                workflow_type=_AGENT_WORKFLOW_TYPE,
                message="Interrupted by backend restart",
            )
        except Exception:
            logger.exception("Failed to mark running workflows interrupted at startup")

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
    global _worker_started, _worker_task, _db_ocr_worker_task, _db_translate_worker_task
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
        _cancel_running_memory_jobs()


def is_jobs_runtime_started() -> bool:
    return _worker_started
