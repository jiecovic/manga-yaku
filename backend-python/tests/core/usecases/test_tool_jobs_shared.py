# backend-python/tests/core/usecases/test_tool_jobs_shared.py
"""Unit tests for shared agent job-tool workflow observation helpers."""

from __future__ import annotations

from unittest.mock import patch

from core.usecases.agent.tool_jobs_shared import wait_for_agent_workflow


def test_wait_for_agent_workflow_normalizes_completed_snapshot() -> None:
    with patch(
        "core.usecases.agent.tool_jobs_shared.wait_for_workflow_snapshot",
        return_value=type(
            "Snapshot",
            (),
            {
                "workflow_run_id": "wf-1",
                "status": "completed",
                "result_json": {"message": "done"},
                "run": {"id": "wf-1", "status": "completed"},
                "found": True,
            },
        )(),
    ):
        observation = wait_for_agent_workflow(
            workflow_run_id="wf-1",
            timeout_seconds=10,
            poll_seconds=0.2,
            wait_error_message="failed",
        )

    assert observation.workflow_run_id == "wf-1"
    assert observation.workflow_status == "completed"
    assert observation.result_json == {"message": "done"}
    assert observation.found is True
    assert observation.wait_error is None
    assert observation.error_message is None


def test_wait_for_agent_workflow_returns_wait_error_on_exception() -> None:
    with patch(
        "core.usecases.agent.tool_jobs_shared.wait_for_workflow_snapshot",
        side_effect=RuntimeError("boom"),
    ):
        observation = wait_for_agent_workflow(
            workflow_run_id="wf-2",
            timeout_seconds=10,
            poll_seconds=0.2,
            wait_error_message="failed while waiting",
        )

    assert observation.workflow_run_id == "wf-2"
    assert observation.workflow_status == "wait_error"
    assert observation.found is False
    assert observation.wait_error == "boom"
    assert observation.error_message == "boom"
