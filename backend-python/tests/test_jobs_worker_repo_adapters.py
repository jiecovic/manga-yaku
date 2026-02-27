# backend-python/tests/test_jobs_worker_repo_adapters.py
"""Unit tests for worker adapters around shared workflow repository helpers.

These tests verify per-worker payload shaping stays stable while claim/requeue
SQL access is delegated to infra.jobs.workflow_repo.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from infra.jobs import db_ocr_worker, db_translate_worker


class OcrWorkerRepoAdapterTests(unittest.TestCase):
    def test_claim_adapter_maps_payload_fields(self) -> None:
        # Adapter should coerce DB payload numerics into worker-friendly floats.
        with patch(
            "infra.jobs.db_ocr_worker.claim_next_task",
            return_value={
                "task_id": "task-1",
                "workflow_id": "wf-1",
                "volume_id": "vol",
                "filename": "001.jpg",
                "box_id": 12,
                "profile_id": "openai_fast_ocr",
                "input_json": {
                    "x": "10",
                    "y": 20,
                    "width": "30.5",
                    "height": 40,
                },
            },
        ) as claim_mock:
            claimed = db_ocr_worker._claim_next_task(lease_seconds=180)

        if claimed is None:
            raise AssertionError("Expected claimed task")
        self.assertEqual(claimed["task_id"], "task-1")
        self.assertEqual(claimed["workflow_id"], "wf-1")
        self.assertEqual(claimed["profile_id"], "openai_fast_ocr")
        self.assertEqual(claimed["x"], 10.0)
        self.assertEqual(claimed["y"], 20.0)
        self.assertEqual(claimed["width"], 30.5)
        self.assertEqual(claimed["height"], 40.0)
        claim_mock.assert_called_once()

    def test_requeue_adapter_delegates(self) -> None:
        with patch(
            "infra.jobs.db_ocr_worker.requeue_stale_running_tasks",
            return_value=3,
        ) as requeue_mock:
            changed = db_ocr_worker._requeue_stale_running_tasks(lease_seconds=180)
        self.assertEqual(changed, 3)
        requeue_mock.assert_called_once()


class TranslateWorkerRepoAdapterTests(unittest.TestCase):
    def test_claim_adapter_maps_payload_fields(self) -> None:
        with patch(
            "infra.jobs.db_translate_worker.claim_next_task",
            return_value={
                "task_id": "task-2",
                "workflow_id": "wf-2",
                "volume_id": "vol",
                "filename": "002.jpg",
                "box_id": 7,
                "profile_id": "openai_fast_translate",
                "input_json": {"use_page_context": True},
            },
        ) as claim_mock:
            claimed = db_translate_worker._claim_next_task(lease_seconds=180)

        if claimed is None:
            raise AssertionError("Expected claimed task")
        self.assertEqual(claimed["task_id"], "task-2")
        self.assertEqual(claimed["workflow_id"], "wf-2")
        self.assertEqual(claimed["box_id"], 7)
        self.assertTrue(claimed["use_page_context"])
        claim_mock.assert_called_once()

    def test_requeue_adapter_delegates(self) -> None:
        with patch(
            "infra.jobs.db_translate_worker.requeue_stale_running_tasks",
            return_value=2,
        ) as requeue_mock:
            changed = db_translate_worker._requeue_stale_running_tasks(lease_seconds=180)
        self.assertEqual(changed, 2)
        requeue_mock.assert_called_once()
