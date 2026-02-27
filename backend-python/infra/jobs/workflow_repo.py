from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from infra.db.db import TaskRun, WorkflowRun, get_session


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
