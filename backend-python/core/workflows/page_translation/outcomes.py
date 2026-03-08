# backend-python/core/workflows/page_translation/outcomes.py
"""Terminal outcome helpers for the page-translation workflow."""

from __future__ import annotations

from typing import Any

from infra.db.workflow_store import update_workflow_run

from .context import WorkflowRunContext
from .progress import emit_workflow_progress
from .stages.commit import CommitStageResult
from .types import PageTranslationWorkflowSnapshot, WorkflowState


def cancel_workflow(
    *,
    workflow_run_id: str,
    run_ctx: WorkflowRunContext,
    state: WorkflowState,
    stage: str,
) -> dict[str, Any]:
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="canceled",
        cancel_requested=True,
    )
    snapshot = PageTranslationWorkflowSnapshot(
        state=state,
        stage=stage,
        progress=100,
        message="Canceled",
        detection_profile_id=run_ctx.detection_profile_id,
        detected_boxes=run_ctx.detected_boxes,
        ocr_tasks_total=run_ctx.ocr_tasks_total,
        ocr_tasks_done=run_ctx.ocr_tasks_done,
        updated_boxes=run_ctx.updated_boxes,
        workflow_run_id=run_ctx.workflow_run_id,
    )
    emit_workflow_progress(
        run_ctx,
        state=state,
        stage=snapshot.stage,
        progress=snapshot.progress,
        message=snapshot.message,
    )
    return snapshot.to_result()


def fail_workflow(
    *,
    workflow_run_id: str,
    state: WorkflowState,
    error_message: str,
) -> None:
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="failed",
        error_message=error_message,
    )


def complete_workflow(
    *,
    workflow_run_id: str,
    run_ctx: WorkflowRunContext,
    state: WorkflowState,
    commit_result: CommitStageResult,
    translation_payload: dict[str, Any],
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    merge_warning = str(translation_payload.get("merge_warning") or "").strip()
    coverage_warning = str(commit_result.coverage_warning or "").strip()
    completion_message = "Agent translation complete"
    if merge_warning:
        completion_message = "Agent translation complete (merge fallback applied)"
    if coverage_warning:
        completion_message = "Agent translation complete (partial stage-1 coverage)"

    result = {
        "state": state.value,
        "stage": "completed",
        "processed": commit_result.processed,
        "total": commit_result.total,
        "updated": run_ctx.updated_boxes,
        "orderApplied": commit_result.order_applied,
        "detectionProfileId": run_ctx.detection_profile_id,
        "workflowRunId": workflow_run_id,
        "characters": commit_result.characters,
        "imageSummary": commit_result.image_summary,
        "storySummary": commit_result.story_summary,
        "openThreads": commit_result.open_threads,
        "glossary": commit_result.glossary,
        "duration_ms": run_ctx.total_duration_ms(),
        "stage_durations_ms": dict(run_ctx.stage_durations_ms),
        "message": completion_message,
    }
    if merge_warning:
        result["mergeWarning"] = merge_warning
    if coverage_warning:
        result["coverageWarning"] = coverage_warning

    persisted = dict(result)
    persisted["request"] = dict(request_payload)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="completed",
        result_json=persisted,
    )
    emit_workflow_progress(
        run_ctx,
        state=state,
        stage="completed",
        progress=100,
        message=completion_message,
    )
    return result
