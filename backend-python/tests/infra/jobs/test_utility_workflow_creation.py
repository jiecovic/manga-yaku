# backend-python/tests/infra/jobs/test_utility_workflow_creation.py
"""Tests for atomic utility workflow creation helpers."""

from __future__ import annotations

from unittest.mock import patch

from infra.jobs.utility_workflow_creation import create_persisted_utility_workflow


def test_create_persisted_utility_workflow_uses_atomic_helper() -> None:
    with patch(
        "infra.jobs.utility_workflow_creation.create_workflow_run_with_task",
        return_value="wf-utility-1",
    ) as create_mock:
        workflow_id = create_persisted_utility_workflow(
            workflow_type="box_detection",
            request_payload={"volumeId": "vol-a", "filename": "001.jpg"},
            message="Queued",
        )

    assert workflow_id == "wf-utility-1"
    create_mock.assert_called_once_with(
        workflow_type="box_detection",
        volume_id="vol-a",
        filename="001.jpg",
        state="queued",
        status="queued",
        result_json={
            "request": {"volumeId": "vol-a", "filename": "001.jpg"},
            "progress": 0,
            "message": "Queued",
        },
        stage="box_detection",
        task_status="queued",
        input_json={"volumeId": "vol-a", "filename": "001.jpg"},
    )
