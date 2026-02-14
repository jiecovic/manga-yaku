# backend-python/infra/jobs/worker.py
from __future__ import annotations

import logging

from infra.training.job_runner import TrainingCanceled

from .handlers.registry import HANDLERS
from .store import JobStatus, JobStore

logger = logging.getLogger(__name__)


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

            handler = HANDLERS.get(job.type)
            if handler is None:
                raise RuntimeError(f"Unknown job type: {job.type}")

            result = await handler.run(job, store)

            if job.status != JobStatus.canceled:
                store.update_job(job, status=JobStatus.finished, result=result)

        except TrainingCanceled as exc:
            if job.status != JobStatus.canceled:
                store.update_job(job, status=JobStatus.canceled, message=str(exc) or "Canceled")
        except Exception as exc:
            error_text = str(exc).strip() or repr(exc)
            logger.exception("Job failed: %s", error_text)
            if job.status != JobStatus.canceled:
                store.update_job(
                    job,
                    status=JobStatus.failed,
                    error=error_text,
                    message=error_text[:160],
                )
        finally:
            store.queue.task_done()
