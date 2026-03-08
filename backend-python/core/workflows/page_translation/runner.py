# backend-python/core/workflows/page_translation/runner.py
"""Workflow runner orchestration for the page-translation workflow."""

from __future__ import annotations

from typing import Any

from .context import WorkflowRunContext
from .helpers import is_canceled as is_cancel_requested
from .helpers import utc_now_iso
from .lifecycle import advance_running_state, ensure_workflow_run
from .outcomes import cancel_workflow, complete_workflow, fail_workflow
from .payloads import build_ocr_profile_meta, build_translation_boxes
from .prior_context import load_prior_context
from .progress import emit_workflow_progress
from .resolution import resolve_detection_profile_id, resolve_ocr_profiles
from .stages.commit import run_commit_stage
from .stages.detect import run_detect_stage
from .stages.ocr_fanout import run_ocr_fanout_stage
from .stages.translate import TranslateStageError, run_translate_stage
from .state_machine import transition
from .types import (
    CancelCheck,
    PageTranslationRequest,
    ProgressCallback,
    WorkflowEvent,
    WorkflowState,
)
from .workflow_settings import resolve_page_translation_workflow_settings


async def run_page_translation_workflow(
    *,
    payload: dict[str, Any],
    on_progress: ProgressCallback | None = None,
    is_canceled: CancelCheck | None = None,
) -> dict[str, Any]:
    """Run the page-translation workflow."""
    request_payload = dict(payload)
    request_payload.pop("workflowRunId", None)
    request_payload.pop("taskRunId", None)
    request_payload.pop("workflowStage", None)
    request = PageTranslationRequest.from_payload(request_payload)
    state = WorkflowState.queued
    detection_profile_id = resolve_detection_profile_id(request.detection_profile_id)
    ocr_profiles = resolve_ocr_profiles(request_payload)

    workflow_run_id = ensure_workflow_run(
        workflow_run_id=str(payload.get("workflowRunId") or "").strip(),
        volume_id=request.volume_id,
        filename=request.filename,
        state=state,
        request_payload=request_payload,
        page_revision=utc_now_iso(),
    )

    run_ctx = WorkflowRunContext(
        workflow_run_id=workflow_run_id,
        detection_profile_id=detection_profile_id,
        on_progress=on_progress,
    )

    emit_workflow_progress(
        run_ctx,
        state=state,
        stage="queued",
        progress=0,
        message="Queued",
    )

    if is_cancel_requested(is_canceled):
        state = transition(state, WorkflowEvent.cancel_requested)
        return cancel_workflow(
            workflow_run_id=workflow_run_id,
            run_ctx=run_ctx,
            state=state,
            stage="queued",
        )

    state = advance_running_state(
        workflow_run_id=workflow_run_id,
        state=state,
        event=WorkflowEvent.start_requested,
    )
    run_ctx.start_stage("detect")
    emit_workflow_progress(
        run_ctx,
        state=state,
        stage="detect_boxes",
        progress=5,
        message="Detecting text boxes",
    )

    try:
        text_boxes = await run_detect_stage(
            volume_id=request.volume_id,
            filename=request.filename,
            detection_profile_id=detection_profile_id,
            preserve_existing_boxes=request.preserve_existing_boxes,
        )
    except Exception as exc:
        run_ctx.finish_stage("detect")
        state = transition(state, WorkflowEvent.detect_failed)
        fail_workflow(
            workflow_run_id=workflow_run_id,
            state=state,
            error_message=str(exc),
        )
        raise

    run_ctx.detected_boxes = len(text_boxes)
    run_ctx.finish_stage("detect")

    if is_cancel_requested(is_canceled):
        state = transition(state, WorkflowEvent.cancel_requested)
        return cancel_workflow(
            workflow_run_id=workflow_run_id,
            run_ctx=run_ctx,
            state=state,
            stage="detect_boxes",
        )

    state = advance_running_state(
        workflow_run_id=workflow_run_id,
        state=state,
        event=WorkflowEvent.detect_succeeded,
    )
    run_ctx.start_stage("ocr")
    emit_workflow_progress(
        run_ctx,
        state=state,
        stage="ocr_fanout",
        progress=20,
        message=f"Detected {run_ctx.detected_boxes} text boxes",
    )

    ocr_stage = await run_ocr_fanout_stage(
        workflow_run_id=workflow_run_id,
        volume_id=request.volume_id,
        filename=request.filename,
        text_boxes=text_boxes,
        ocr_profiles=ocr_profiles,
        preferred_profile_id=ocr_profiles[0] if ocr_profiles else None,
        run_ctx=run_ctx,
        state=state,
        is_canceled=lambda: is_cancel_requested(is_canceled),
    )

    if is_cancel_requested(is_canceled):
        run_ctx.finish_stage("ocr")
        state = transition(state, WorkflowEvent.cancel_requested)
        return cancel_workflow(
            workflow_run_id=workflow_run_id,
            run_ctx=run_ctx,
            state=state,
            stage="ocr_running",
        )

    candidates = ocr_stage.candidates
    no_text_candidates = ocr_stage.no_text_candidates
    error_candidates = ocr_stage.error_candidates
    invalid_candidates = ocr_stage.invalid_candidates
    llm_profiles = ocr_stage.llm_profiles

    if not ocr_stage.usable_ocr and run_ctx.ocr_tasks_total > 0:
        run_ctx.finish_stage("ocr")
        state = transition(state, WorkflowEvent.ocr_failed)
        fail_workflow(
            workflow_run_id=workflow_run_id,
            state=state,
            error_message="OCR failed for all tasks",
        )
        raise RuntimeError("OCR stage failed for all tasks")

    run_ctx.finish_stage("ocr")
    state = advance_running_state(
        workflow_run_id=workflow_run_id,
        state=state,
        event=WorkflowEvent.ocr_succeeded,
    )
    run_ctx.start_stage("translate")
    emit_workflow_progress(
        run_ctx,
        state=state,
        stage="translating",
        progress=75,
        message="Translating page",
    )

    payload_boxes, box_index_map = build_translation_boxes(
        text_boxes=text_boxes,
        candidates=candidates,
        no_text_candidates=no_text_candidates,
        error_candidates=error_candidates,
        invalid_candidates=invalid_candidates,
        llm_profiles=llm_profiles,
    )

    prior_context = load_prior_context(request.volume_id)
    workflow_settings = resolve_page_translation_workflow_settings(
        request_model_id=request.model_id
    )
    ocr_profile_meta = build_ocr_profile_meta(ocr_profiles)
    try:
        translation_payload = await run_translate_stage(
            workflow_run_id=workflow_run_id,
            volume_id=request.volume_id,
            filename=request.filename,
            source_language=request.source_language,
            target_language=request.target_language,
            boxes=payload_boxes,
            ocr_profiles=ocr_profile_meta,
            prior_context_summary=(
                prior_context.summary if workflow_settings.include_prior_summary else ""
            ),
            prior_characters=(
                prior_context.characters if workflow_settings.include_prior_characters else []
            ),
            prior_open_threads=(
                prior_context.open_threads if workflow_settings.include_prior_open_threads else []
            ),
            prior_glossary=(
                prior_context.glossary if workflow_settings.include_prior_glossary else []
            ),
            model_id=workflow_settings.model_id,
            max_output_tokens=workflow_settings.max_output_tokens
            if isinstance(workflow_settings.max_output_tokens, int | float)
            else None,
            reasoning_effort=(
                str(workflow_settings.reasoning_effort)
                if isinstance(workflow_settings.reasoning_effort, str)
                else None
            ),
            temperature=(
                float(workflow_settings.temperature)
                if isinstance(workflow_settings.temperature, int | float)
                else None
            ),
            merge_max_output_tokens=workflow_settings.merge_max_output_tokens,
            merge_reasoning_effort=workflow_settings.merge_reasoning_effort,
        )
    except TranslateStageError as exc:
        run_ctx.finish_stage("translate")
        error_message = str(exc).strip() or "Translate stage failed"
        state = transition(state, WorkflowEvent.translate_failed)
        fail_workflow(
            workflow_run_id=workflow_run_id,
            state=state,
            error_message=error_message,
        )
        raise RuntimeError(error_message) from None

    run_ctx.finish_stage("translate")
    state = advance_running_state(
        workflow_run_id=workflow_run_id,
        state=state,
        event=WorkflowEvent.translate_succeeded,
    )
    run_ctx.start_stage("commit")
    emit_workflow_progress(
        run_ctx,
        state=state,
        stage="commit",
        progress=90,
        message="Applying translated output",
    )

    try:
        commit_result = run_commit_stage(
            volume_id=request.volume_id,
            filename=request.filename,
            text_boxes=text_boxes,
            box_index_map=box_index_map,
            translation_payload=translation_payload,
            prior_summary=prior_context.summary,
        )
    except Exception as exc:
        run_ctx.finish_stage("commit")
        state = transition(state, WorkflowEvent.commit_failed)
        fail_workflow(
            workflow_run_id=workflow_run_id,
            state=state,
            error_message=str(exc),
        )
        raise

    run_ctx.finish_stage("commit")

    run_ctx.updated_boxes = commit_result.updated
    state = transition(state, WorkflowEvent.commit_succeeded)
    return complete_workflow(
        workflow_run_id=workflow_run_id,
        run_ctx=run_ctx,
        state=state,
        commit_result=commit_result,
        translation_payload=translation_payload,
        request_payload=payload,
    )
