# backend-python/core/workflows/page_translation/orchestration/lifecycle.py
"""Workflow row lifecycle helpers for page-translation orchestration."""

from __future__ import annotations

from typing import Any

from infra.db.workflow_store import create_workflow_run, update_workflow_run

from ..state.state_machine import transition
from ..state.types import WorkflowEvent, WorkflowState


def ensure_workflow_run(
    *,
    workflow_run_id: str,
    volume_id: str,
    filename: str,
    state: WorkflowState,
    request_payload: dict[str, Any],
    page_revision: str,
) -> str:
    """Ensure the persisted workflow row exists before stage execution starts.

    New runs create a queued workflow row here. Existing runs reuse the provided
    id and refresh the normalized request payload so retries and inspection use
    the same stored source of truth.
    """
    resolved_workflow_run_id = workflow_run_id
    if not resolved_workflow_run_id:
        resolved_workflow_run_id = create_workflow_run(
            workflow_type="page_translation",
            volume_id=volume_id,
            filename=filename,
            state=state.value,
            status="queued",
            page_revision=page_revision,
        )
    update_workflow_run(
        resolved_workflow_run_id,
        result_json={"request": request_payload},
        page_revision=page_revision,
    )
    return resolved_workflow_run_id


def advance_running_state(
    *,
    workflow_run_id: str,
    state: WorkflowState,
    event: WorkflowEvent,
) -> WorkflowState:
    """Advance the workflow state machine and persist the new running state."""
    next_state = transition(state, event)
    update_workflow_run(
        workflow_run_id,
        state=next_state.value,
        status="running",
    )
    return next_state
