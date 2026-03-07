# backend-python/tests/infra/jobs/test_db_utility_worker.py
"""Unit tests for the persisted utility workflow worker."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from infra.jobs import db_utility_worker
from infra.jobs.store import JobStore


class _FakeHandler:
    async def run(self, job, store):
        store.update_job(job, progress=55, message="Working")
        return {"count": 4}


class UtilityDbWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_claimed_task_persists_progress_and_terminal_result(self) -> None:
        signal_store = JobStore()
        claimed = {
            "workflow_id": "wf-box-1",
            "task_id": "task-box-1",
            "workflow_type": "box_detection",
            "payload": {"volumeId": "vol-a", "filename": "001.jpg"},
        }
        run_record = {
            "id": "wf-box-1",
            "workflow_type": "box_detection",
            "volume_id": "vol-a",
            "filename": "001.jpg",
            "status": "running",
            "cancel_requested": False,
            "created_at": None,
            "updated_at": None,
            "result_json": {
                "request": {"volumeId": "vol-a", "filename": "001.jpg"},
                "progress": 0,
                "message": "Queued",
            },
        }

        with (
            patch.object(
                db_utility_worker,
                "HANDLERS",
                {"box_detection": _FakeHandler()},
            ),
            patch.object(
                db_utility_worker,
                "get_workflow_run",
                return_value=run_record,
            ),
            patch.object(db_utility_worker, "update_task_run") as update_task_mock,
            patch.object(db_utility_worker, "update_workflow_run") as update_workflow_mock,
        ):
            await db_utility_worker._run_claimed_task(
                claimed,
                log_store={},
                shutdown_event=threading.Event(),
                signal_store=signal_store,
            )

        self.assertGreaterEqual(update_task_mock.call_count, 2)
        self.assertGreaterEqual(update_workflow_mock.call_count, 2)
        final_task_call = update_task_mock.call_args_list[-1]
        self.assertEqual(final_task_call.kwargs["status"], "completed")
        self.assertEqual(final_task_call.kwargs["result_json"]["count"], 4)

        final_workflow_call = update_workflow_mock.call_args_list[-1]
        self.assertEqual(final_workflow_call.kwargs["status"], "completed")
        self.assertEqual(final_workflow_call.kwargs["result_json"]["request"]["volumeId"], "vol-a")
        self.assertEqual(final_workflow_call.kwargs["result_json"]["count"], 4)
