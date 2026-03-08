# backend-python/core/workflows/page_translation/orchestration/progress.py
"""Progress computation and status formatting for the page-translation workflow."""

from __future__ import annotations

from ..state.types import WorkflowState
from .context import WorkflowRunContext
from .helpers import emit_progress


def emit_workflow_progress(
    ctx: WorkflowRunContext,
    *,
    state: WorkflowState,
    stage: str,
    progress: int,
    message: str,
) -> None:
    """Emit workflow progress."""
    emit_progress(
        state=state,
        stage=stage,
        progress=progress,
        message=message,
        detection_profile_id=ctx.detection_profile_id,
        detected_boxes=ctx.detected_boxes,
        ocr_tasks_total=ctx.ocr_tasks_total,
        ocr_tasks_done=ctx.ocr_tasks_done,
        updated_boxes=ctx.updated_boxes,
        workflow_run_id=ctx.workflow_run_id,
        on_progress=ctx.on_progress,
    )
