# backend-python/tests/infra/jobs/test_jobs_infra.py
"""Unit tests for in-memory jobs store and generic worker behavior.

What is tested:
- Job serialization remains SSE/JSON safe.
- Unknown job handlers fail deterministically with expected job status updates.

How it is tested:
- In-process async worker loop with short-lived test jobs.
- Uses only the in-memory store; no database-backed queue access.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import unittest

from infra.jobs.store import Job, JobStatus, JobStore
from infra.jobs.worker import job_worker


async def _run_unknown_job() -> Job:
    store = JobStore()
    now = store.now()
    job = Job(
        id="test-job",
        type="unknown_job",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload={},
        result=None,
        error=None,
    )
    store.add_job(job)
    worker_task = asyncio.create_task(job_worker(store))
    stored: Job | None = None
    try:
        await store.queue.put(job.id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 2.0
        while loop.time() < deadline:
            await asyncio.sleep(0.01)
            stored = store.get_job(job.id)
            # Poll to avoid race with async worker update timing.
            if stored and stored.status in (JobStatus.failed, JobStatus.finished):
                break
        if not stored or stored.status not in (JobStatus.failed, JobStatus.finished):
            raise AssertionError("Job did not finish in time")
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
    if stored is None:
        raise AssertionError("Job missing from store")
    return stored


class JobStoreTests(unittest.TestCase):
    def test_format_sse_sanitizes_nonfinite(self) -> None:
        store = JobStore()
        payload = {
            "value": float("nan"),
            "items": [float("inf"), 1.0],
            "nested": {"neg_inf": float("-inf")},
        }
        data = store.format_sse(payload)
        self.assertTrue(data.startswith("data: "))
        json_text = data.replace("data: ", "", 1).strip()
        parsed = json.loads(json_text)
        self.assertIsNone(parsed["value"])
        self.assertIsNone(parsed["items"][0])
        self.assertEqual(parsed["items"][1], 1.0)
        self.assertIsNone(parsed["nested"]["neg_inf"])


class JobWorkerTests(unittest.TestCase):
    def test_unknown_job_type_fails(self) -> None:
        result_job = asyncio.run(_run_unknown_job())
        self.assertEqual(result_job.status, JobStatus.failed)
        self.assertIn("Unknown job type", result_job.error or "")
