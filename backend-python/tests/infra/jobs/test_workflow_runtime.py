# backend-python/tests/infra/jobs/test_workflow_runtime.py
"""Unit tests for persisted workflow runtime polling helpers."""

from __future__ import annotations

from unittest.mock import patch

from infra.jobs.workflow_runtime import wait_for_workflow_snapshot


def test_wait_for_workflow_snapshot_uses_latest_observed_run() -> None:
    run = {
        "id": "wf-123",
        "status": "running",
        "result_json": {"message": "Working"},
    }
    with patch(
        "infra.jobs.workflow_runtime.poll_workflow_run",
        return_value=run,
    ) as wait_mock:
        snapshot = wait_for_workflow_snapshot(
            "wf-123",
            timeout_seconds=1.0,
            poll_seconds=0.1,
        )

    wait_mock.assert_called_once_with(
        "wf-123",
        timeout_seconds=1.0,
        poll_seconds=0.1,
    )
    assert snapshot.found
    assert not snapshot.terminal
    assert snapshot.workflow_run_id == "wf-123"
    assert snapshot.status == "running"
    assert snapshot.result_json == {"message": "Working"}


def test_wait_for_workflow_snapshot_refreshes_when_poll_returns_none() -> None:
    refreshed_run = {
        "id": "wf-456",
        "status": "completed",
        "result_json": {"progress": 100},
    }
    with (
        patch(
            "infra.jobs.workflow_runtime.poll_workflow_run",
            return_value=None,
        ),
        patch(
            "infra.jobs.workflow_runtime.get_workflow_run",
            return_value=refreshed_run,
        ) as get_mock,
    ):
        snapshot = wait_for_workflow_snapshot(
            "wf-456",
            timeout_seconds=1.0,
            poll_seconds=0.1,
        )

    get_mock.assert_called_once_with("wf-456")
    assert snapshot.found
    assert snapshot.terminal
    assert snapshot.workflow_run_id == "wf-456"
    assert snapshot.status == "completed"
    assert snapshot.result_json == {"progress": 100}


def test_wait_for_workflow_snapshot_marks_missing_run() -> None:
    with (
        patch(
            "infra.jobs.workflow_runtime.poll_workflow_run",
            return_value=None,
        ),
        patch(
            "infra.jobs.workflow_runtime.get_workflow_run",
            return_value=None,
        ),
    ):
        snapshot = wait_for_workflow_snapshot(
            "wf-missing",
            timeout_seconds=1.0,
            poll_seconds=0.1,
        )

    assert not snapshot.found
    assert not snapshot.terminal
    assert snapshot.workflow_run_id == "wf-missing"
    assert snapshot.status == "missing"
    assert snapshot.result_json == {}
