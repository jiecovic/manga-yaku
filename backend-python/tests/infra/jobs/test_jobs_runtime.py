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
import threading
import time
from unittest.mock import patch

import pytest
import pytest_asyncio
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


async def _call_in_thread(
    func,
    /,
    *args,
    timeout_seconds: float = 5.0,
    **kwargs,
):
    result: dict[str, object] = {}
    done = threading.Event()

    def _runner() -> None:
        try:
            result["value"] = func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - exercised in tests
            result["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()

    deadline = time.monotonic() + timeout_seconds
    while not done.is_set():
        if time.monotonic() >= deadline:
            raise AssertionError("Threaded helper call timed out")
        await asyncio.sleep(0.01)

    error = result.get("error")
    if isinstance(error, Exception):
        raise error
    if error is not None:
        raise RuntimeError(str(error))
    return result.get("value")


@pytest_asyncio.fixture(autouse=True)
async def _runtime_cleanup() -> None:
    await runtime.stop_jobs_runtime()
    _clear_store(runtime.STORE)
    yield
    await runtime.stop_jobs_runtime()
    _clear_store(runtime.STORE)


@pytest.mark.asyncio
async def test_startup_is_idempotent() -> None:
    with (
        patch.object(runtime, "mark_running_workflows_interrupted") as mark_interrupted,
        # Replace worker bodies with wait loops so we can assert lifecycle
        # semantics without touching real DB-backed loops.
        patch.object(runtime, "job_worker", new=_wait_for_store_shutdown),
        patch.object(runtime, "_run_agent_db_worker_supervisor", new=_wait_for_event_shutdown),
        patch.object(runtime, "_run_ocr_db_worker_supervisor", new=_wait_for_event_shutdown),
        patch.object(
            runtime,
            "_run_translate_db_worker_supervisor",
            new=_wait_for_event_shutdown,
        ),
        patch.object(runtime, "_run_utility_db_worker_supervisor", new=_wait_for_event_shutdown),
    ):
        await runtime.start_jobs_runtime()
        first_worker_task = runtime._worker_task
        first_agent_db_worker_task = runtime._db_agent_worker_task
        first_db_worker_task = runtime._db_ocr_worker_task
        first_translate_db_worker_task = runtime._db_translate_worker_task
        first_utility_db_worker_task = runtime._db_utility_worker_task

        await runtime.start_jobs_runtime()

        assert runtime.is_jobs_runtime_started()
        assert first_worker_task is runtime._worker_task
        assert first_agent_db_worker_task is runtime._db_agent_worker_task
        assert first_db_worker_task is runtime._db_ocr_worker_task
        assert first_translate_db_worker_task is runtime._db_translate_worker_task
        assert first_utility_db_worker_task is runtime._db_utility_worker_task
        assert not runtime.STORE.shutdown_event.is_set()
        mark_interrupted.assert_called_once_with(
            workflow_type=runtime.AGENT_WORKFLOW_TYPE,
            message="Interrupted by backend restart",
            include_queued=True,
        )

        await runtime.stop_jobs_runtime()
        assert not runtime.is_jobs_runtime_started()
        assert runtime._worker_task is None
        assert runtime._db_agent_worker_task is None
        assert runtime._db_ocr_worker_task is None
        assert runtime._db_translate_worker_task is None
        assert runtime._db_utility_worker_task is None
        assert runtime.STORE.shutdown_event.is_set()


@pytest.mark.asyncio
async def test_shutdown_marks_running_memory_jobs_canceled() -> None:
    now = runtime.STORE.now()
    runtime.STORE.add_job(
        Job(
            id="running-job",
            type="box_detection",
            status=JobStatus.running,
            created_at=now,
            updated_at=now,
            payload={"volumeId": "v", "filename": "001.jpg"},
        )
    )

    with (
        patch.object(runtime, "mark_running_workflows_interrupted"),
        patch.object(runtime, "job_worker", new=_wait_for_store_shutdown),
        patch.object(runtime, "_run_agent_db_worker_supervisor", new=_wait_for_event_shutdown),
        patch.object(runtime, "_run_ocr_db_worker_supervisor", new=_wait_for_event_shutdown),
        patch.object(
            runtime,
            "_run_translate_db_worker_supervisor",
            new=_wait_for_event_shutdown,
        ),
        patch.object(runtime, "_run_utility_db_worker_supervisor", new=_wait_for_event_shutdown),
    ):
        await runtime.start_jobs_runtime()
        await runtime.stop_jobs_runtime()

    stored = runtime.STORE.get_job("running-job")
    if stored is None:
        raise AssertionError("Expected running job to remain in store")
    assert stored.status == JobStatus.canceled
    assert stored.message == "Canceled (shutdown)"


@pytest.mark.asyncio
async def test_create_and_enqueue_memory_job_from_thread() -> None:
    with (
        patch.object(runtime, "mark_running_workflows_interrupted"),
        patch.object(runtime, "job_worker", new=_wait_for_store_shutdown),
        patch.object(runtime, "_run_agent_db_worker_supervisor", new=_wait_for_event_shutdown),
        patch.object(runtime, "_run_ocr_db_worker_supervisor", new=_wait_for_event_shutdown),
        patch.object(
            runtime,
            "_run_translate_db_worker_supervisor",
            new=_wait_for_event_shutdown,
        ),
        patch.object(runtime, "_run_utility_db_worker_supervisor", new=_wait_for_event_shutdown),
    ):
        await runtime.start_jobs_runtime()

        job_id = await _call_in_thread(
            runtime.create_and_enqueue_memory_job,
            job_type="box_detection",
            payload={"volumeId": "vol", "filename": "001.jpg"},
            message="Queued (test)",
        )

        stored = runtime.STORE.get_job(job_id)
        if stored is None:
            raise AssertionError("Expected job to be present in store")
        assert stored.status == JobStatus.queued
        assert stored.message == "Queued (test)"

        queued_id = runtime.STORE.queue.get_nowait()
        assert queued_id == job_id
        runtime.STORE.queue.task_done()


@pytest.mark.asyncio
async def test_create_and_enqueue_memory_job_marks_failed_when_enqueue_raises() -> None:
    with (
        patch.object(runtime, "mark_running_workflows_interrupted"),
        patch.object(runtime, "job_worker", new=_wait_for_store_shutdown),
        patch.object(runtime, "_run_agent_db_worker_supervisor", new=_wait_for_event_shutdown),
        patch.object(runtime, "_run_ocr_db_worker_supervisor", new=_wait_for_event_shutdown),
        patch.object(
            runtime,
            "_run_translate_db_worker_supervisor",
            new=_wait_for_event_shutdown,
        ),
        patch.object(runtime, "_run_utility_db_worker_supervisor", new=_wait_for_event_shutdown),
    ):
        await runtime.start_jobs_runtime()
        with (
            patch.object(runtime.STORE.queue, "put_nowait", side_effect=RuntimeError("queue down")),
            pytest.raises(RuntimeError, match="queue down"),
        ):
            await _call_in_thread(
                runtime.create_and_enqueue_memory_job,
                job_type="box_detection",
                payload={"volumeId": "vol", "filename": "002.jpg"},
            )

        failed_jobs = [job for job in runtime.STORE.jobs.values() if job.status == JobStatus.failed]
        assert len(failed_jobs) == 1
        failed = failed_jobs[0]
        assert "queue down" in str(failed.error or "")

        queued_jobs = [job for job in runtime.STORE.jobs.values() if job.status == JobStatus.queued]
        assert len(queued_jobs) == 0
