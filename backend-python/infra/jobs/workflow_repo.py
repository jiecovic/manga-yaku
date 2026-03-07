# backend-python/infra/jobs/workflow_repo.py
"""Adapters that expose workflow/task persistence operations."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from infra.db.db import TaskRun, WorkflowRun, get_session
from infra.db.workflow_store import (
    append_task_attempt_event as store_append_task_attempt_event,
)
from infra.db.workflow_store import get_workflow_run as store_get_workflow_run
from infra.db.workflow_store import (
    list_task_runs as store_list_task_runs,
)
from infra.db.workflow_store import (
    mark_running_workflows_interrupted as store_mark_running_workflows_interrupted,
)
from infra.db.workflow_store import update_task_run as store_update_task_run
from infra.db.workflow_store import (
    update_workflow_run as store_update_workflow_run,
)
from sqlalchemy import select


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def claim_next_task(
    *,
    workflow_types: Sequence[str],
    stage: str,
    lease_seconds: int,
) -> dict[str, Any] | None:
    now = _utc_now()
    lease_until = now + timedelta(seconds=max(30, int(lease_seconds)))
    workflow_type_values = tuple(str(item) for item in workflow_types if str(item).strip())
    if not workflow_type_values:
        return None

    with get_session() as session:
        stmt = (
            select(TaskRun, WorkflowRun)
            .join(WorkflowRun, TaskRun.workflow_id == WorkflowRun.id)
            .where(WorkflowRun.workflow_type.in_(workflow_type_values))
            .where(WorkflowRun.status.in_(["queued", "running"]))
            .where(WorkflowRun.cancel_requested.is_(False))
            .where(TaskRun.stage == stage)
            .where(TaskRun.status == "queued")
            .order_by(TaskRun.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = session.execute(stmt).first()
        if row is None:
            return None

        task_row, workflow_row = row
        task_row.status = "running"
        task_row.started_at = task_row.started_at or now
        task_row.updated_at = now
        task_row.lease_until = lease_until
        task_row.error_code = None
        task_row.error_detail = None
        if workflow_row.status == "queued":
            workflow_row.status = "running"
        if workflow_row.state == "queued":
            workflow_row.state = "running"
        workflow_row.updated_at = now

        payload = task_row.input_json if isinstance(task_row.input_json, dict) else {}
        return {
            "task_id": str(task_row.id),
            "workflow_id": str(workflow_row.id),
            "volume_id": str(workflow_row.volume_id),
            "filename": str(workflow_row.filename),
            "box_id": int(task_row.box_id or payload.get("box_id") or 0),
            "profile_id": str(task_row.profile_id or payload.get("profile_id") or ""),
            "input_json": payload,
        }


def requeue_stale_running_tasks(
    *,
    workflow_types: Sequence[str],
    stage: str,
) -> int:
    now = _utc_now()
    changed = 0
    workflow_type_values = tuple(str(item) for item in workflow_types if str(item).strip())
    if not workflow_type_values:
        return 0

    with get_session() as session:
        stmt = (
            select(TaskRun, WorkflowRun)
            .join(WorkflowRun, TaskRun.workflow_id == WorkflowRun.id)
            .where(WorkflowRun.workflow_type.in_(workflow_type_values))
            .where(TaskRun.stage == stage)
            .where(TaskRun.status == "running")
            .where((TaskRun.lease_until.is_(None)) | (TaskRun.lease_until < now))
            .with_for_update(skip_locked=True)
        )
        rows = session.execute(stmt).all()
        for task_row, workflow_row in rows:
            if workflow_row.cancel_requested or workflow_row.status == "canceled":
                task_row.status = "canceled"
                task_row.finished_at = now
                task_row.error_code = "cancel_requested"
                task_row.error_detail = "Canceled"
            else:
                task_row.status = "queued"
                task_row.error_code = "lease_expired"
                task_row.error_detail = "Requeued after worker restart"
            task_row.lease_until = None
            task_row.updated_at = now
            changed += 1
    return changed


def recover_running_tasks_for_startup(
    *,
    workflow_types: Sequence[str],
    stage: str,
) -> int:
    """Reset interrupted running tasks after backend startup."""
    now = _utc_now()
    changed = 0
    workflow_type_values = tuple(str(item) for item in workflow_types if str(item).strip())
    if not workflow_type_values:
        return 0

    with get_session() as session:
        stmt = (
            select(TaskRun, WorkflowRun)
            .join(WorkflowRun, TaskRun.workflow_id == WorkflowRun.id)
            .where(WorkflowRun.workflow_type.in_(workflow_type_values))
            .where(TaskRun.stage == stage)
            .where(TaskRun.status == "running")
            .with_for_update(skip_locked=True)
        )
        rows = session.execute(stmt).all()
        for task_row, workflow_row in rows:
            if workflow_row.cancel_requested or workflow_row.status == "canceled":
                task_row.status = "canceled"
                task_row.finished_at = now
                task_row.error_code = "cancel_requested"
                task_row.error_detail = "Canceled"
                workflow_row.status = "canceled"
                workflow_row.state = "canceled"
            else:
                task_row.status = "queued"
                task_row.error_code = "worker_restart"
                task_row.error_detail = "Requeued after backend restart"
                workflow_row.status = "queued"
                workflow_row.state = "queued"
            task_row.lease_until = None
            task_row.updated_at = now
            workflow_row.updated_at = now
            changed += 1
    return changed


def get_workflow_run(workflow_id: str) -> dict[str, Any] | None:
    return store_get_workflow_run(workflow_id)


def list_task_runs(
    workflow_id: str,
    *,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    return store_list_task_runs(workflow_id, stage=stage)


def update_task_run(
    task_id: str,
    *,
    status: str | None = None,
    attempt: int | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    result_json: dict[str, Any] | None = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    store_update_task_run(
        task_id,
        status=status,
        attempt=attempt,
        error_code=error_code,
        error_detail=error_detail,
        result_json=result_json,
        started=started,
        finished=finished,
    )


def update_workflow_run(
    workflow_id: str,
    *,
    state: str | None = None,
    status: str | None = None,
    error_message: str | None = None,
    result_json: dict[str, Any] | None = None,
) -> None:
    store_update_workflow_run(
        workflow_id,
        state=state,
        status=status,
        error_message=error_message,
        result_json=result_json,
    )


def append_task_attempt_event(
    *,
    task_id: str,
    attempt: int,
    tool_name: str,
    model_id: str | None = None,
    prompt_version: str | None = None,
    params_snapshot: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    latency_ms: int | None = None,
    error_detail: str | None = None,
) -> None:
    store_append_task_attempt_event(
        task_id=task_id,
        attempt=attempt,
        tool_name=tool_name,
        model_id=model_id,
        prompt_version=prompt_version,
        params_snapshot=params_snapshot,
        token_usage=token_usage,
        finish_reason=finish_reason,
        latency_ms=latency_ms,
        error_detail=error_detail,
    )


def mark_running_workflows_interrupted(
    *,
    workflow_type: str | None = None,
    message: str = "Interrupted by backend restart",
    include_queued: bool = False,
) -> int:
    return store_mark_running_workflows_interrupted(
        workflow_type=workflow_type,
        message=message,
        include_queued=include_queued,
    )
