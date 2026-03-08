# backend-python/core/workflows/page_translation/runner.py
"""Workflow runner orchestration for the page-translation workflow."""

from __future__ import annotations

from typing import Any

from core.usecases.page_translation.settings import resolve_page_translation_settings
from core.usecases.settings.service import get_setting_value
from infra.db.store_context import get_volume_context
from infra.db.workflow_store import (
    create_workflow_run,
    update_workflow_run,
)

from .context import WorkflowRunContext
from .helpers import (
    build_ocr_profile_meta,
    build_translation_boxes,
    resolve_detection_profile_id,
    resolve_ocr_profiles,
    utc_now_iso,
)
from .helpers import (
    is_canceled as is_cancel_requested,
)
from .progress import emit_workflow_progress
from .stages.commit import run_commit_stage
from .stages.detect import run_detect_stage
from .stages.ocr_fanout import run_ocr_fanout_stage
from .stages.translate import TranslateStageError, run_translate_stage
from .state_machine import transition
from .types import (
    CancelCheck,
    PageTranslationRequest,
    PageTranslationWorkflowSnapshot,
    ProgressCallback,
    WorkflowEvent,
    WorkflowState,
)


def _get_bool_setting(key: str, *, default: bool) -> bool:
    raw = get_setting_value(key)
    return bool(raw) if isinstance(raw, bool) else default


def _get_int_setting(
    key: str,
    *,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = get_setting_value(key)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    return value


def _get_str_choice_setting(
    key: str,
    *,
    default: str,
    choices: tuple[str, ...],
) -> str:
    raw = get_setting_value(key)
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in choices:
            return normalized
    return default


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

    workflow_run_id = str(payload.get("workflowRunId") or "").strip()
    if not workflow_run_id:
        workflow_run_id = create_workflow_run(
            workflow_type="page_translation",
            volume_id=request.volume_id,
            filename=request.filename,
            state=state.value,
            status="queued",
            page_revision=utc_now_iso(),
        )
    update_workflow_run(
        workflow_run_id,
        result_json={"request": request_payload},
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
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="canceled",
            cancel_requested=True,
        )
        snapshot = PageTranslationWorkflowSnapshot(
            state=state,
            stage="queued",
            progress=100,
            message="Canceled",
            detection_profile_id=run_ctx.detection_profile_id,
            detected_boxes=run_ctx.detected_boxes,
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

    state = transition(state, WorkflowEvent.start_requested)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
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
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message=str(exc),
        )
        raise

    run_ctx.detected_boxes = len(text_boxes)
    run_ctx.finish_stage("detect")

    if is_cancel_requested(is_canceled):
        state = transition(state, WorkflowEvent.cancel_requested)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="canceled",
            cancel_requested=True,
        )
        snapshot = PageTranslationWorkflowSnapshot(
            state=state,
            stage="detect_boxes",
            progress=100,
            message="Canceled",
            detection_profile_id=run_ctx.detection_profile_id,
            detected_boxes=run_ctx.detected_boxes,
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

    state = transition(state, WorkflowEvent.detect_succeeded)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
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
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="canceled",
            cancel_requested=True,
        )
        snapshot = PageTranslationWorkflowSnapshot(
            state=state,
            stage="ocr_running",
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

    candidates = ocr_stage.candidates
    no_text_candidates = ocr_stage.no_text_candidates
    error_candidates = ocr_stage.error_candidates
    invalid_candidates = ocr_stage.invalid_candidates
    llm_profiles = ocr_stage.llm_profiles

    if not ocr_stage.usable_ocr and run_ctx.ocr_tasks_total > 0:
        run_ctx.finish_stage("ocr")
        state = transition(state, WorkflowEvent.ocr_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message="OCR failed for all tasks",
        )
        raise RuntimeError("OCR stage failed for all tasks")

    run_ctx.finish_stage("ocr")
    state = transition(state, WorkflowEvent.ocr_succeeded)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
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

    volume_context = get_volume_context(request.volume_id) or {}
    prior_summary = str(volume_context.get("rolling_summary") or "")
    prior_characters = volume_context.get("active_characters")
    if not isinstance(prior_characters, list):
        prior_characters = []
    prior_open_threads = volume_context.get("open_threads")
    if not isinstance(prior_open_threads, list):
        prior_open_threads = []
    prior_glossary = volume_context.get("glossary")
    if not isinstance(prior_glossary, list):
        prior_glossary = []

    include_prior_summary = _get_bool_setting(
        "page_translation.include_prior_context_summary",
        default=True,
    )
    include_prior_characters = _get_bool_setting(
        "page_translation.include_prior_characters",
        default=True,
    )
    include_prior_open_threads = _get_bool_setting(
        "page_translation.include_prior_open_threads",
        default=True,
    )
    include_prior_glossary = _get_bool_setting(
        "page_translation.include_prior_glossary",
        default=True,
    )
    merge_max_output_tokens = _get_int_setting(
        "page_translation.merge.max_output_tokens",
        default=768,
        min_value=128,
        max_value=4096,
    )
    merge_reasoning_effort = _get_str_choice_setting(
        "page_translation.merge.reasoning_effort",
        default="low",
        choices=("low", "medium", "high"),
    )
    page_translation_settings = resolve_page_translation_settings()
    model_id = request.model_id or page_translation_settings.model_id
    max_output_tokens = page_translation_settings.max_output_tokens
    reasoning_effort = page_translation_settings.reasoning_effort
    temperature = page_translation_settings.temperature
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
            prior_context_summary=prior_summary if include_prior_summary else "",
            prior_characters=prior_characters if include_prior_characters else [],
            prior_open_threads=prior_open_threads if include_prior_open_threads else [],
            prior_glossary=prior_glossary if include_prior_glossary else [],
            model_id=model_id,
            max_output_tokens=max_output_tokens
            if isinstance(max_output_tokens, int | float)
            else None,
            reasoning_effort=str(reasoning_effort) if isinstance(reasoning_effort, str) else None,
            temperature=float(temperature) if isinstance(temperature, int | float) else None,
            merge_max_output_tokens=merge_max_output_tokens,
            merge_reasoning_effort=merge_reasoning_effort,
        )
    except TranslateStageError as exc:
        run_ctx.finish_stage("translate")
        error_message = str(exc).strip() or "Translate stage failed"
        state = transition(state, WorkflowEvent.translate_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message=error_message,
        )
        raise RuntimeError(error_message) from None

    run_ctx.finish_stage("translate")
    state = transition(state, WorkflowEvent.translate_succeeded)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
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
            prior_summary=prior_summary,
        )
    except Exception as exc:
        run_ctx.finish_stage("commit")
        state = transition(state, WorkflowEvent.commit_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message=str(exc),
        )
        raise

    run_ctx.finish_stage("commit")

    run_ctx.updated_boxes = commit_result.updated
    state = transition(state, WorkflowEvent.commit_succeeded)
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
    persisted["request"] = dict(payload)
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
