# backend-python/infra/jobs/utility_workflow_creation.py
"""Creation helpers for persisted single-task utility workflows."""

from __future__ import annotations

from typing import Any

from infra.db.workflow_store import create_workflow_run_with_task
from infra.jobs.job_modes import UTILITY_WORKFLOW_TYPES


def _normalize_location(request_payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(request_payload.get("volumeId") or "").strip(),
        str(request_payload.get("filename") or "").strip(),
    )


def create_persisted_utility_workflow(
    *,
    workflow_type: str,
    request_payload: dict[str, Any],
    message: str = "Queued",
) -> str:
    """Create a persisted utility workflow backed by a single queued task."""
    if workflow_type not in UTILITY_WORKFLOW_TYPES:
        raise ValueError(f"Unsupported utility workflow type: {workflow_type}")

    payload = dict(request_payload or {})
    volume_id, filename = _normalize_location(payload)
    return create_workflow_run_with_task(
        workflow_type=workflow_type,
        volume_id=volume_id,
        filename=filename,
        state="queued",
        status="queued",
        result_json={
            "request": payload,
            "progress": 0,
            "message": str(message),
        },
        stage=workflow_type,
        task_status="queued",
        input_json=payload,
    )
