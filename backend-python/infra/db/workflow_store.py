# backend-python/infra/db/workflow_store.py
"""Database CRUD for workflow runs and task runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from .db import TaskAttemptEvent, TaskRun, WorkflowRun, get_session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def create_workflow_run(
    *,
    workflow_type: str,
    volume_id: str,
    filename: str,
    state: str,
    status: str,
    page_revision: str | None = None,
    deadline_at: datetime | None = None,
) -> str:
    now = _utc_now()
    with get_session() as session:
        row = WorkflowRun(
            workflow_type=workflow_type,
            volume_id=volume_id,
            filename=filename,
            page_revision=page_revision,
            state=state,
            status=status,
            deadline_at=deadline_at,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        return str(row.id)


def update_workflow_run(
    workflow_id: str | UUID,
    *,
    state: str | None = None,
    status: str | None = None,
    page_revision: str | None = None,
    cancel_requested: bool | None = None,
    error_message: str | None = None,
    result_json: dict[str, Any] | None = None,
) -> None:
    with get_session() as session:
        row = session.execute(
            select(WorkflowRun).where(WorkflowRun.id == _to_uuid(workflow_id))
        ).scalar_one_or_none()
        if row is None:
            return
        if state is not None:
            row.state = state
        if status is not None:
            row.status = status
        if page_revision is not None:
            row.page_revision = page_revision
        if cancel_requested is not None:
            row.cancel_requested = bool(cancel_requested)
        if error_message is not None:
            row.error_message = error_message
        if result_json is not None:
            row.result_json = result_json
        row.updated_at = _utc_now()


def create_task_run(
    *,
    workflow_id: str | UUID,
    stage: str,
    status: str = "queued",
    box_id: int | None = None,
    profile_id: str | None = None,
    input_json: dict[str, Any] | None = None,
) -> str:
    now = _utc_now()
    with get_session() as session:
        row = TaskRun(
            workflow_id=_to_uuid(workflow_id),
            stage=stage,
            box_id=box_id,
            profile_id=profile_id,
            status=status,
            input_json=input_json,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        return str(row.id)


def create_task_runs(
    *,
    workflow_id: str | UUID,
    stage: str,
    tasks: list[dict[str, Any]],
) -> int:
    if not tasks:
        return 0

    now = _utc_now()
    workflow_uuid = _to_uuid(workflow_id)
    rows: list[TaskRun] = []
    for task in tasks:
        rows.append(
            TaskRun(
                workflow_id=workflow_uuid,
                stage=stage,
                box_id=task.get("box_id"),
                profile_id=task.get("profile_id"),
                status=str(task.get("status") or "queued"),
                input_json=task.get("input_json")
                if isinstance(task.get("input_json"), dict)
                else None,
                created_at=now,
                updated_at=now,
            )
        )

    with get_session() as session:
        session.add_all(rows)

    return len(rows)


def update_task_run(
    task_id: str | UUID,
    *,
    status: str | None = None,
    attempt: int | None = None,
    lease_until: datetime | None = None,
    next_retry_at: datetime | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    result_json: dict[str, Any] | None = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    with get_session() as session:
        row = session.execute(
            select(TaskRun).where(TaskRun.id == _to_uuid(task_id))
        ).scalar_one_or_none()
        if row is None:
            return
        if status is not None:
            row.status = status
        if attempt is not None:
            row.attempt = max(0, int(attempt))
        if lease_until is not None:
            row.lease_until = lease_until
        if next_retry_at is not None:
            row.next_retry_at = next_retry_at
        if error_code is not None:
            row.error_code = error_code
        if error_detail is not None:
            row.error_detail = error_detail
        if result_json is not None:
            row.result_json = result_json
        if started:
            row.started_at = _utc_now()
        if finished:
            row.finished_at = _utc_now()
        row.updated_at = _utc_now()


def append_task_attempt_event(
    *,
    task_id: str | UUID,
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
    with get_session() as session:
        row = TaskAttemptEvent(
            task_id=_to_uuid(task_id),
            attempt=max(1, int(attempt)),
            tool_name=tool_name,
            model_id=model_id,
            prompt_version=prompt_version,
            params_snapshot=params_snapshot,
            token_usage=token_usage,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            error_detail=error_detail,
            created_at=_utc_now(),
        )
        session.add(row)


def list_task_runs(
    workflow_id: str | UUID,
    *,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = (
            select(TaskRun)
            .where(TaskRun.workflow_id == _to_uuid(workflow_id))
            .order_by(TaskRun.created_at.asc())
        )
        if stage:
            stmt = stmt.where(TaskRun.stage == stage)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": str(row.id),
                "stage": row.stage,
                "box_id": row.box_id,
                "profile_id": row.profile_id,
                "status": row.status,
                "attempt": int(row.attempt or 0),
                "error_code": row.error_code,
                "result_json": row.result_json,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]


def list_task_attempt_events(task_ids: list[str | UUID]) -> dict[str, list[dict[str, Any]]]:
    if not task_ids:
        return {}

    parsed_ids: list[UUID] = []
    for task_id in task_ids:
        try:
            parsed_ids.append(_to_uuid(task_id))
        except Exception:
            continue
    if not parsed_ids:
        return {}

    with get_session() as session:
        rows = (
            session.execute(
                select(TaskAttemptEvent)
                .where(TaskAttemptEvent.task_id.in_(parsed_ids))
                .order_by(
                    TaskAttemptEvent.task_id.asc(),
                    TaskAttemptEvent.attempt.asc(),
                    TaskAttemptEvent.created_at.asc(),
                )
            )
            .scalars()
            .all()
        )
        out: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = str(row.task_id)
            out.setdefault(key, []).append(
                {
                    "id": int(row.id),
                    "attempt": int(row.attempt),
                    "tool_name": row.tool_name,
                    "model_id": row.model_id,
                    "prompt_version": row.prompt_version,
                    "params_snapshot": row.params_snapshot,
                    "token_usage": row.token_usage,
                    "finish_reason": row.finish_reason,
                    "latency_ms": row.latency_ms,
                    "error_detail": row.error_detail,
                    "created_at": row.created_at,
                }
            )
        return out


def get_workflow_run(workflow_id: str | UUID) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.execute(
            select(WorkflowRun).where(WorkflowRun.id == _to_uuid(workflow_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": str(row.id),
            "workflow_type": row.workflow_type,
            "volume_id": row.volume_id,
            "filename": row.filename,
            "page_revision": row.page_revision,
            "state": row.state,
            "status": row.status,
            "cancel_requested": bool(row.cancel_requested),
            "error_message": row.error_message,
            "result_json": row.result_json,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


def list_workflow_runs(
    *,
    workflow_type: str | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(max(1, limit))
        if workflow_type:
            stmt = stmt.where(WorkflowRun.workflow_type == workflow_type)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": str(row.id),
                "workflow_type": row.workflow_type,
                "volume_id": row.volume_id,
                "filename": row.filename,
                "page_revision": row.page_revision,
                "state": row.state,
                "status": row.status,
                "cancel_requested": bool(row.cancel_requested),
                "error_message": row.error_message,
                "result_json": row.result_json,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]


def mark_running_workflows_interrupted(
    *,
    workflow_type: str | None = None,
    message: str = "Interrupted by backend restart",
) -> int:
    changed = 0
    with get_session() as session:
        stmt = select(WorkflowRun).where(WorkflowRun.status == "running")
        if workflow_type:
            stmt = stmt.where(WorkflowRun.workflow_type == workflow_type)
        rows = session.execute(stmt).scalars().all()
        for row in rows:
            row.status = "failed"
            row.state = "failed"
            row.error_message = message
            row.updated_at = _utc_now()
            changed += 1
    return changed


def cancel_workflow_run(
    workflow_id: str | UUID,
    *,
    message: str = "Canceled",
) -> bool:
    with get_session() as session:
        row = session.execute(
            select(WorkflowRun).where(WorkflowRun.id == _to_uuid(workflow_id))
        ).scalar_one_or_none()
        if row is None:
            return False
        row.cancel_requested = True
        if row.status not in {"completed", "failed", "canceled"}:
            row.status = "canceled"
            row.state = "canceled"
        if not row.error_message:
            row.error_message = message
        row.updated_at = _utc_now()
        return True


def delete_workflow_run(workflow_id: str | UUID) -> bool:
    with get_session() as session:
        row = session.execute(
            select(WorkflowRun).where(WorkflowRun.id == _to_uuid(workflow_id))
        ).scalar_one_or_none()
        if row is None:
            return False
        session.delete(row)
        return True


def delete_terminal_workflow_runs(*, workflow_type: str | None = None) -> int:
    with get_session() as session:
        stmt = delete(WorkflowRun).where(
            WorkflowRun.status.in_(["completed", "failed", "canceled"])
        )
        if workflow_type:
            stmt = stmt.where(WorkflowRun.workflow_type == workflow_type)
        result = session.execute(stmt)
        return int(result.rowcount or 0)
