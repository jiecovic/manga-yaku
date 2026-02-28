# backend-python/core/workflows/agent_translate_page/stages/merge.py
"""Workflow stage handler for agent translate page: merge."""

from __future__ import annotations

from infra.db.workflow_store import create_task_run, update_task_run


def create_merge_task_run(
    *,
    workflow_run_id: str,
    volume_id: str,
    filename: str,
    source_language: str,
    target_language: str,
    model_id: str | None,
) -> str:
    return create_task_run(
        workflow_id=workflow_run_id,
        stage="merge_state",
        status="queued",
        profile_id=model_id,
        input_json={
            "volume_id": volume_id,
            "filename": filename,
            "source_language": source_language,
            "target_language": target_language,
            "model_id": model_id,
        },
    )


def mark_merge_task_canceled(task_run_id: str, *, reason: str) -> None:
    message = reason.strip() or "Skipped because translate stage failed"
    update_task_run(
        task_run_id,
        status="canceled",
        attempt=1,
        error_code="upstream_failed",
        error_detail=message,
        result_json={
            "stage": "merge_state",
            "status": "canceled",
            "message": message,
        },
        finished=True,
    )
