# backend-python/infra/db/store_volume_reset.py
"""Reset helpers that clear derived volume/page processing state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update

from infra.logging.artifacts import agent_debug_dir

from .db import (
    AgentSession,
    Box,
    BoxDetectionRun,
    LlmCallLog,
    Page,
    PageContext,
    TaskAttemptEvent,
    TaskRun,
    VolumeContext,
    WorkflowRun,
    get_session,
)


def _count_task_attempt_events(session, task_ids: list[Any]) -> int:
    if not task_ids:
        return 0
    count = session.execute(
        select(func.count())
        .select_from(TaskAttemptEvent)
        .where(TaskAttemptEvent.task_id.in_(task_ids))
    ).scalar_one()
    return int(count or 0)


def _delete_paths(paths: list[str]) -> int:
    deleted = 0
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            continue
        try:
            path.unlink()
            deleted += 1
        except Exception:
            continue
    return deleted


def _delete_agent_debug_files_for_volume(volume_id: str) -> int:
    target_dir = agent_debug_dir("translate_page", create=False)
    if not target_dir.is_dir():
        return 0

    deleted = 0
    for path in target_dir.glob("*.json"):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            payload = json.loads(raw)
        except Exception:
            continue
        if str(payload.get("volume_id") or "").strip() != volume_id:
            continue
        try:
            path.unlink()
            deleted += 1
        except Exception:
            continue
    return deleted


def clear_volume_derived_data(volume_id: str) -> dict[str, int]:
    volume_key = str(volume_id or "").strip()
    if not volume_key:
        raise ValueError("volume_id is required")

    llm_payload_paths: list[str] = []
    stats: dict[str, int] = {
        "pages_touched": 0,
        "boxes_deleted": 0,
        "detection_runs_deleted": 0,
        "page_context_snapshots_deleted": 0,
        "page_notes_cleared": 0,
        "volume_context_deleted": 0,
        "agent_sessions_deleted": 0,
        "workflow_runs_deleted": 0,
        "task_runs_deleted": 0,
        "task_attempt_events_deleted": 0,
        "llm_call_logs_deleted": 0,
        "llm_payload_files_deleted": 0,
        "agent_debug_files_deleted": 0,
    }

    with get_session() as session:
        active_workflows = session.execute(
            select(func.count())
            .select_from(WorkflowRun)
            .where(
                WorkflowRun.volume_id == volume_key,
                WorkflowRun.status.in_(["queued", "running"]),
            )
        ).scalar_one()
        if int(active_workflows or 0) > 0:
            raise RuntimeError(
                "Cannot clear volume while workflow jobs are queued or running. "
                "Cancel those jobs first."
            )

        page_ids = list(
            session.execute(
                select(Page.id).where(Page.volume_id == volume_key)
            ).scalars().all()
        )
        stats["pages_touched"] = len(page_ids)

        workflow_ids = list(
            session.execute(
                select(WorkflowRun.id).where(WorkflowRun.volume_id == volume_key)
            ).scalars().all()
        )
        workflow_id_text = [str(item) for item in workflow_ids]

        task_ids: list[Any] = []
        if workflow_ids:
            task_ids = list(
                session.execute(
                    select(TaskRun.id).where(TaskRun.workflow_id.in_(workflow_ids))
                ).scalars().all()
            )
        stats["task_runs_deleted"] = len(task_ids)
        stats["task_attempt_events_deleted"] = _count_task_attempt_events(session, task_ids)

        if workflow_id_text:
            llm_rows = session.execute(
                select(LlmCallLog.id, LlmCallLog.payload_path).where(
                    LlmCallLog.workflow_run_id.in_(workflow_id_text)
                )
            ).all()
            llm_log_ids = [row.id for row in llm_rows]
            llm_payload_paths = [
                str(row.payload_path)
                for row in llm_rows
                if isinstance(row.payload_path, str) and row.payload_path.strip()
            ]
            if llm_log_ids:
                stats["llm_call_logs_deleted"] = int(
                    session.execute(
                        delete(LlmCallLog).where(LlmCallLog.id.in_(llm_log_ids))
                    ).rowcount
                    or 0
                )

        if page_ids:
            stats["boxes_deleted"] = int(
                session.execute(delete(Box).where(Box.page_id.in_(page_ids))).rowcount or 0
            )
            stats["detection_runs_deleted"] = int(
                session.execute(
                    delete(BoxDetectionRun).where(BoxDetectionRun.page_id.in_(page_ids))
                ).rowcount
                or 0
            )
            stats["page_context_snapshots_deleted"] = int(
                session.execute(
                    delete(PageContext).where(PageContext.page_id.in_(page_ids))
                ).rowcount
                or 0
            )
            # Keep page records/images, but clear manual page context text.
            stats["page_notes_cleared"] = int(
                session.execute(
                    update(Page).where(Page.id.in_(page_ids)).values(context="")
                ).rowcount
                or 0
            )

        stats["volume_context_deleted"] = int(
            session.execute(
                delete(VolumeContext).where(VolumeContext.volume_id == volume_key)
            ).rowcount
            or 0
        )
        stats["agent_sessions_deleted"] = int(
            session.execute(
                delete(AgentSession).where(AgentSession.volume_id == volume_key)
            ).rowcount
            or 0
        )

        if workflow_ids:
            stats["workflow_runs_deleted"] = int(
                session.execute(
                    delete(WorkflowRun).where(WorkflowRun.id.in_(workflow_ids))
                ).rowcount
                or 0
            )

    stats["llm_payload_files_deleted"] = _delete_paths(llm_payload_paths)
    stats["agent_debug_files_deleted"] = _delete_agent_debug_files_for_volume(volume_key)
    return stats
