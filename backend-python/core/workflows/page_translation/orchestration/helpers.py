# backend-python/core/workflows/page_translation/orchestration/helpers.py
"""Shared helper utilities for the page-translation workflow."""

from __future__ import annotations

from datetime import datetime, timezone

from ..state.types import (
    CancelCheck,
    PageTranslationWorkflowSnapshot,
    ProgressCallback,
    WorkflowState,
)


def utc_now_iso() -> str:
    """Handle utc now iso."""
    return datetime.now(timezone.utc).isoformat()


def emit_progress(
    *,
    state: WorkflowState,
    stage: str,
    progress: int,
    message: str,
    detection_profile_id: str | None,
    detected_boxes: int,
    ocr_tasks_total: int,
    ocr_tasks_done: int,
    updated_boxes: int,
    workflow_run_id: str,
    on_progress: ProgressCallback | None,
) -> None:
    """Emit progress."""
    if on_progress is None:
        return
    on_progress(
        PageTranslationWorkflowSnapshot(
            state=state,
            stage=stage,
            progress=progress,
            message=message,
            detection_profile_id=detection_profile_id,
            detected_boxes=detected_boxes,
            ocr_tasks_total=ocr_tasks_total,
            ocr_tasks_done=ocr_tasks_done,
            updated_boxes=updated_boxes,
            workflow_run_id=workflow_run_id,
        )
    )


def is_canceled(check: CancelCheck | None) -> bool:
    """Return whether canceled."""
    return bool(check and check())
