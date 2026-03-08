# backend-python/tests/infra/jobs/test_jobs_worker_repo_adapters.py
"""Unit tests for DB worker adapters over shared workflow repo helpers.

What is tested:
- Claim adapter payload mapping from repository shape to worker-consumable shape.
- Requeue adapter delegation and argument forwarding.

How it is tested:
- Repository functions are patched and assertions target adapter boundaries.
- No real SQL execution is performed in this module.
"""

from __future__ import annotations

from unittest.mock import patch

from infra.jobs import db_ocr_worker, db_translate_worker


def test_ocr_claim_adapter_maps_payload_fields() -> None:
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
    assert claimed["task_id"] == "task-1"
    assert claimed["workflow_id"] == "wf-1"
    assert claimed["profile_id"] == "openai_fast_ocr"
    assert claimed["x"] == 10.0
    assert claimed["y"] == 20.0
    assert claimed["width"] == 30.5
    assert claimed["height"] == 40.0
    claim_mock.assert_called_once()


def test_ocr_requeue_adapter_delegates() -> None:
    with patch(
        "infra.jobs.db_ocr_worker.requeue_stale_running_tasks",
        return_value=3,
    ) as requeue_mock:
        changed = db_ocr_worker._requeue_stale_running_tasks()
    assert changed == 3
    requeue_mock.assert_called_once()


def test_translate_claim_adapter_maps_payload_fields() -> None:
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
    assert claimed["task_id"] == "task-2"
    assert claimed["workflow_id"] == "wf-2"
    assert claimed["box_id"] == 7
    assert claimed["use_page_context"] is True
    claim_mock.assert_called_once()


def test_translate_requeue_adapter_delegates() -> None:
    with patch(
        "infra.jobs.db_translate_worker.requeue_stale_running_tasks",
        return_value=2,
    ) as requeue_mock:
        changed = db_translate_worker._requeue_stale_running_tasks()
    assert changed == 2
    requeue_mock.assert_called_once()
