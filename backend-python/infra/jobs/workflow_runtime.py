# backend-python/infra/jobs/workflow_runtime.py
"""Helpers for polling persisted workflow runs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from infra.jobs.workflow_repo import get_workflow_run

_TERMINAL_WORKFLOW_STATUSES = frozenset({"completed", "failed", "canceled", "timed_out"})


# Normalizes the raw workflow row so polling callers can share one small contract
# instead of each re-parsing dict|None results and result_json/status fields.
@dataclass(frozen=True)
class WorkflowRunSnapshot:
    """Latest observed persisted workflow state after polling."""

    workflow_run_id: str
    status: str
    result_json: dict[str, Any]
    run: dict[str, Any] | None

    @property
    def found(self) -> bool:
        """Return whether a backing workflow row was found."""
        return self.run is not None

    @property
    def terminal(self) -> bool:
        """Return whether the observed workflow state is terminal."""
        return self.status in _TERMINAL_WORKFLOW_STATUSES


def poll_workflow_run(
    workflow_run_id: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> dict[str, Any] | None:
    """Poll a workflow until terminal status or timeout and return the latest run."""
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    safe_poll_seconds = max(0.05, float(poll_seconds))
    run = get_workflow_run(workflow_run_id)
    while (
        run is not None
        and str(run.get("status") or "").strip().lower() in {"queued", "running"}
        and time.monotonic() < deadline
    ):
        time.sleep(safe_poll_seconds)
        run = get_workflow_run(workflow_run_id)
    if run is not None:
        return run
    return None


def wait_for_workflow_snapshot(
    workflow_run_id: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> WorkflowRunSnapshot:
    """Return the latest observed workflow row after polling for terminal state."""
    run = poll_workflow_run(
        workflow_run_id,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )
    if run is None:
        run = get_workflow_run(workflow_run_id)
    return build_workflow_snapshot(
        workflow_run_id=workflow_run_id,
        run=run,
    )


def build_workflow_snapshot(
    *,
    workflow_run_id: str,
    run: dict[str, Any] | None,
) -> WorkflowRunSnapshot:
    """Build a normalized snapshot for a workflow row."""
    resolved_workflow_run_id = workflow_run_id
    if isinstance(run, dict):
        candidate_id = str(run.get("id") or "").strip()
        if candidate_id:
            resolved_workflow_run_id = candidate_id
    return WorkflowRunSnapshot(
        workflow_run_id=resolved_workflow_run_id,
        status=workflow_run_status(run),
        result_json=workflow_result_json(run),
        run=run if isinstance(run, dict) else None,
    )


def workflow_run_status(run: dict[str, Any] | None) -> str:
    """Normalize a workflow run status string."""
    if not isinstance(run, dict):
        return "missing"
    return str(run.get("status") or "").strip().lower() or "missing"


def workflow_result_json(run: dict[str, Any] | None) -> dict[str, Any]:
    """Return a workflow row's normalized result payload."""
    raw = run.get("result_json") if isinstance(run, dict) else None
    if isinstance(raw, dict):
        return dict(raw)
    return {}
