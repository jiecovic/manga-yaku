# backend-python/infra/jobs/workflow_runtime.py
"""Helpers for waiting on persisted workflow runs."""

from __future__ import annotations

import time
from typing import Any

from infra.jobs.workflow_repo import get_workflow_run


def wait_for_workflow_terminal(
    workflow_run_id: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> dict[str, Any] | None:
    """Poll a persisted workflow until it reaches a terminal status or times out."""
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
