# backend-python/tests/infra/jobs/test_jobs_runtime.py
"""Unit tests for jobs runtime startup/shutdown lifecycle.

What is tested:
- Runtime startup is idempotent and launches expected worker tasks.
- Shutdown toggles termination signals and allows tasks to drain.

How it is tested:
- Worker loops are patched with controllable async stubs.
- Assertions focus on runtime state flags and task lifecycle behavior.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from infra.jobs import runtime
from infra.jobs.store import Job, JobStatus, JobStore


async def _wait_for_store_shutdown(store: JobStore) -> None:
    while not store.shutdown_event.is_set():
        await asyncio.sleep(0.01)


async def _wait_for_event_shutdown(event) -> None:
    while not event.is_set():
        await asyncio.sleep(0.01)


def _clear_store(store: JobStore) -> None:
    store.jobs.clear()
    store.logs.clear()
    store.subscribers.clear()
    while True:
        try:
            store.queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    store.shutdown_event.clear()


class JobsRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await runtime.stop_jobs_runtime()
        _clear_store(runtime.STORE)

    async def asyncTearDown(self) -> None:
        await runtime.stop_jobs_runtime()
        _clear_store(runtime.STORE)

    async def test_startup_is_idempotent(self) -> None:
        with (
            patch.object(runtime, "mark_running_workflows_interrupted") as mark_interrupted,
            # Replace worker bodies with wait loops so we can assert lifecycle
            # semantics without touching real DB-backed loops.
            patch.object(runtime, "job_worker", new=_wait_for_store_shutdown),
            patch.object(runtime, "_run_ocr_db_worker_supervisor", new=_wait_for_event_shutdown),
            patch.object(
                runtime,
                "_run_translate_db_worker_supervisor",
                new=_wait_for_event_shutdown,
            ),
        ):
            await runtime.start_jobs_runtime()
            first_worker_task = runtime._worker_task
            first_db_worker_task = runtime._db_ocr_worker_task
            first_translate_db_worker_task = runtime._db_translate_worker_task

            await runtime.start_jobs_runtime()

            self.assertTrue(runtime.is_jobs_runtime_started())
            self.assertIs(first_worker_task, runtime._worker_task)
            self.assertIs(first_db_worker_task, runtime._db_ocr_worker_task)
            self.assertIs(first_translate_db_worker_task, runtime._db_translate_worker_task)
            self.assertFalse(runtime.STORE.shutdown_event.is_set())
            mark_interrupted.assert_called_once()

            await runtime.stop_jobs_runtime()
            self.assertFalse(runtime.is_jobs_runtime_started())
            self.assertIsNone(runtime._worker_task)
            self.assertIsNone(runtime._db_ocr_worker_task)
            self.assertIsNone(runtime._db_translate_worker_task)
            self.assertTrue(runtime.STORE.shutdown_event.is_set())

    async def test_shutdown_marks_running_memory_jobs_canceled(self) -> None:
        now = runtime.STORE.now()
        runtime.STORE.add_job(
            Job(
                id="running-job",
                type="agent_translate_page",
                status=JobStatus.running,
                created_at=now,
                updated_at=now,
                payload={"volumeId": "v", "filename": "001.jpg"},
            )
        )

        with (
            patch.object(runtime, "mark_running_workflows_interrupted"),
            patch.object(runtime, "job_worker", new=_wait_for_store_shutdown),
            patch.object(runtime, "_run_ocr_db_worker_supervisor", new=_wait_for_event_shutdown),
            patch.object(
                runtime,
                "_run_translate_db_worker_supervisor",
                new=_wait_for_event_shutdown,
            ),
        ):
            await runtime.start_jobs_runtime()
            await runtime.stop_jobs_runtime()

        stored = runtime.STORE.get_job("running-job")
        if stored is None:
            raise AssertionError("Expected running job to remain in store")
        self.assertEqual(stored.status, JobStatus.canceled)
        self.assertEqual(stored.message, "Canceled (shutdown)")
