from __future__ import annotations

import asyncio
from typing import Any

from config import AGENT_TRANSLATE_TIMEOUT_SECONDS
from core.usecases.agent.page_translate import run_agent_translate_page
from core.usecases.agent.settings import resolve_agent_translate_settings
from core.usecases.settings.service import get_setting_value
from infra.db.db_store import (
    get_page_index,
    get_volume_context,
    upsert_page_context,
    upsert_volume_context,
)
from infra.db.workflow_store import (
    append_task_attempt_event,
    create_task_run,
    create_workflow_run,
    update_task_run,
    update_workflow_run,
)

from .context import WorkflowRunContext
from .helpers import (
    apply_translation_payload,
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
from .stages.detect import run_detect_stage
from .stages.ocr_fanout import run_ocr_fanout_stage
from .state_machine import transition
from .types import (
    AgentTranslatePageRequest,
    AgentTranslateWorkflowSnapshot,
    CancelCheck,
    ProgressCallback,
    WorkflowEvent,
    WorkflowState,
)


def _get_bool_setting(key: str, *, default: bool) -> bool:
    raw = get_setting_value(key)
    return bool(raw) if isinstance(raw, bool) else default


async def run_agent_translate_page_workflow(
    *,
    payload: dict[str, Any],
    on_progress: ProgressCallback | None = None,
    is_canceled: CancelCheck | None = None,
) -> dict[str, Any]:
    request = AgentTranslatePageRequest.from_payload(payload)
    state = WorkflowState.queued
    detection_profile_id = resolve_detection_profile_id(request.detection_profile_id)
    ocr_profiles = resolve_ocr_profiles(payload)

    workflow_run_id = create_workflow_run(
        workflow_type="agent_translate_page",
        volume_id=request.volume_id,
        filename=request.filename,
        state=state.value,
        status="queued",
        page_revision=utc_now_iso(),
    )
    update_workflow_run(
        workflow_run_id,
        result_json={"request": dict(payload)},
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
        snapshot = AgentTranslateWorkflowSnapshot(
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
        snapshot = AgentTranslateWorkflowSnapshot(
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
        snapshot = AgentTranslateWorkflowSnapshot(
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
        "agent.translate.include_prior_context_summary",
        default=True,
    )
    include_prior_characters = _get_bool_setting(
        "agent.translate.include_prior_characters",
        default=True,
    )
    include_prior_open_threads = _get_bool_setting(
        "agent.translate.include_prior_open_threads",
        default=True,
    )
    include_prior_glossary = _get_bool_setting(
        "agent.translate.include_prior_glossary",
        default=True,
    )
    agent_settings = resolve_agent_translate_settings()
    model_id = request.model_id or agent_settings.get("model_id")
    max_output_tokens = agent_settings.get("max_output_tokens")
    reasoning_effort = agent_settings.get("reasoning_effort")
    temperature = agent_settings.get("temperature")
    resolved_model_id = str(model_id).strip() if isinstance(model_id, str) else ""
    if not resolved_model_id:
        resolved_model_id = None

    translate_task_run_id = create_task_run(
        workflow_id=workflow_run_id,
        stage="translate_page",
        status="queued",
        profile_id=resolved_model_id,
        input_json={
            "volume_id": request.volume_id,
            "filename": request.filename,
            "source_language": request.source_language,
            "target_language": request.target_language,
            "model_id": resolved_model_id,
        },
    )
    merge_task_run_id = create_task_run(
        workflow_id=workflow_run_id,
        stage="merge_state",
        status="queued",
        profile_id=resolved_model_id,
        input_json={
            "volume_id": request.volume_id,
            "filename": request.filename,
            "source_language": request.source_language,
            "target_language": request.target_language,
            "model_id": resolved_model_id,
        },
    )
    stage_task_ids = {
        "translate_page": translate_task_run_id,
        "merge_state": merge_task_run_id,
    }

    def on_agent_stage_event(
        stage_name: str,
        status_name: str,
        payload_meta: dict[str, Any] | None,
    ) -> None:
        task_run_id = stage_task_ids.get(stage_name)
        if not task_run_id:
            return

        meta = payload_meta if isinstance(payload_meta, dict) else {}
        raw_attempt = meta.get("attempt_count", 1)
        try:
            attempt = max(1, int(raw_attempt))
        except (TypeError, ValueError):
            attempt = 1

        if status_name == "started":
            update_task_run(
                task_run_id,
                status="running",
                attempt=attempt,
                started=True,
            )
            return

        is_success = status_name == "succeeded"
        finish_status = "completed" if is_success else "failed"
        error_detail = None
        if not is_success:
            raw_error = meta.get("error")
            error_detail = str(raw_error).strip() if raw_error is not None else ""
            if not error_detail:
                error_detail = f"{stage_name} failed"

        update_task_run(
            task_run_id,
            status=finish_status,
            attempt=attempt,
            error_code=None if is_success else "stage_failed",
            error_detail=error_detail,
            result_json=meta or None,
            finished=True,
        )

        params_snapshot = meta.get("params_snapshot")
        if not isinstance(params_snapshot, dict):
            params_snapshot = None
        token_usage = meta.get("token_usage")
        if not isinstance(token_usage, dict):
            token_usage = None
        raw_finish_reason = meta.get("finish_reason")
        finish_reason = (
            str(raw_finish_reason).strip()
            if isinstance(raw_finish_reason, str)
            else finish_status
        )
        raw_latency = meta.get("latency_ms")
        latency_ms = 0
        if isinstance(raw_latency, int):
            latency_ms = max(0, raw_latency)
        elif isinstance(raw_latency, float):
            latency_ms = max(0, int(raw_latency))
        elif isinstance(raw_latency, str):
            try:
                latency_ms = max(0, int(raw_latency.strip()))
            except ValueError:
                latency_ms = 0
        raw_model = meta.get("model_id")
        model_for_event = str(raw_model).strip() if isinstance(raw_model, str) else None
        if not model_for_event:
            model_for_event = resolved_model_id
        prompt_version = (
            "agent_translate_page_merge.yml"
            if stage_name == "merge_state"
            else "agent_translate_page.yml"
        )
        append_task_attempt_event(
            task_id=task_run_id,
            attempt=attempt,
            tool_name=stage_name,
            model_id=model_for_event,
            prompt_version=prompt_version,
            params_snapshot=params_snapshot,
            token_usage=token_usage,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            error_detail=error_detail,
        )

    ocr_profile_meta = build_ocr_profile_meta(ocr_profiles)
    translation_timeout_seconds = max(30, int(AGENT_TRANSLATE_TIMEOUT_SECONDS))
    try:
        translation_payload = await asyncio.wait_for(
            asyncio.to_thread(
                run_agent_translate_page,
                volume_id=request.volume_id,
                filename=request.filename,
                boxes=payload_boxes,
                ocr_profiles=ocr_profile_meta,
                prior_context_summary=prior_summary if include_prior_summary else "",
                prior_characters=prior_characters if include_prior_characters else [],
                prior_open_threads=prior_open_threads if include_prior_open_threads else [],
                prior_glossary=prior_glossary if include_prior_glossary else [],
                source_language=request.source_language,
                target_language=request.target_language,
                model_id=model_id,
                debug_id=workflow_run_id,
                max_output_tokens=(
                    int(max_output_tokens)
                    if isinstance(max_output_tokens, int | float)
                    else None
                ),
                reasoning_effort=(
                    str(reasoning_effort)
                    if isinstance(reasoning_effort, str)
                    else None
                ),
                temperature=(
                    float(temperature) if isinstance(temperature, int | float) else None
                ),
                on_stage_event=on_agent_stage_event,
            ),
            timeout=float(translation_timeout_seconds),
        )
    except asyncio.TimeoutError:
        run_ctx.finish_stage("translate")
        error_message = f"Agent translation timed out after {translation_timeout_seconds}s"
        update_task_run(
            translate_task_run_id,
            status="failed",
            attempt=1,
            error_code="timeout",
            error_detail=error_message,
            result_json={
                "stage": "translate_page",
                "status": "failed",
                "message": error_message,
                "error": error_message,
            },
            finished=True,
        )
        update_task_run(
            merge_task_run_id,
            status="canceled",
            attempt=1,
            error_code="upstream_failed",
            error_detail="Skipped because translate stage failed",
            result_json={
                "stage": "merge_state",
                "status": "canceled",
                "message": "Skipped because translate stage failed",
            },
            finished=True,
        )
        state = transition(state, WorkflowEvent.translate_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message=error_message,
        )
        raise RuntimeError(error_message) from None
    except Exception as exc:
        run_ctx.finish_stage("translate")
        error_message = str(exc)
        update_task_run(
            translate_task_run_id,
            status="failed",
            attempt=1,
            error_code="translate_failed",
            error_detail=error_message,
            result_json={
                "stage": "translate_page",
                "status": "failed",
                "message": "Translate stage failed",
                "error": error_message,
            },
            finished=True,
        )
        update_task_run(
            merge_task_run_id,
            status="canceled",
            attempt=1,
            error_code="upstream_failed",
            error_detail="Skipped because translate stage failed",
            result_json={
                "stage": "merge_state",
                "status": "canceled",
                "message": "Skipped because translate stage failed",
            },
            finished=True,
        )
        state = transition(state, WorkflowEvent.translate_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message=error_message,
        )
        raise

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
        commit = apply_translation_payload(
            volume_id=request.volume_id,
            filename=request.filename,
            text_boxes=text_boxes,
            box_index_map=box_index_map,
            translation_payload=translation_payload,
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

    story_summary = translation_payload.get("story_summary")
    image_summary = translation_payload.get("image_summary")
    characters = translation_payload.get("characters", [])
    open_threads = translation_payload.get("open_threads", [])
    glossary = translation_payload.get("glossary", [])
    if not isinstance(characters, list):
        characters = []
    if not isinstance(open_threads, list):
        open_threads = []
    if not isinstance(glossary, list):
        glossary = []

    rolling_summary = (
        story_summary if isinstance(story_summary, str) and story_summary.strip() else prior_summary
    )
    page_summary = story_summary if isinstance(story_summary, str) else ""
    page_image_summary = image_summary if isinstance(image_summary, str) else ""
    page_index = get_page_index(request.volume_id, request.filename)
    upsert_volume_context(
        request.volume_id,
        rolling_summary=rolling_summary,
        active_characters=characters,
        open_threads=open_threads,
        glossary=glossary,
        last_page_index=page_index,
    )
    upsert_page_context(
        request.volume_id,
        request.filename,
        page_summary=page_summary,
        image_summary=page_image_summary,
        characters_snapshot=characters,
        open_threads_snapshot=open_threads,
        glossary_snapshot=glossary,
    )
    run_ctx.finish_stage("commit")

    run_ctx.updated_boxes = int(commit.get("updated") or 0)
    state = transition(state, WorkflowEvent.commit_succeeded)
    result = {
        "state": state.value,
        "stage": "completed",
        "processed": int(commit.get("processed") or 0),
        "total": int(commit.get("total") or 0),
        "updated": run_ctx.updated_boxes,
        "orderApplied": bool(commit.get("orderApplied")),
        "detectionProfileId": run_ctx.detection_profile_id,
        "workflowRunId": workflow_run_id,
        "characters": characters,
        "imageSummary": image_summary if isinstance(image_summary, str) else None,
        "storySummary": story_summary if isinstance(story_summary, str) else None,
        "openThreads": open_threads,
        "glossary": glossary,
        "duration_ms": run_ctx.total_duration_ms(),
        "stage_durations_ms": dict(run_ctx.stage_durations_ms),
        "message": "Agent translation complete",
    }
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
        message="Agent translation complete",
    )
    return result


async def run_agent_translate_page_detect_stage(
    *,
    payload: dict[str, Any],
    on_progress: ProgressCallback | None = None,
    is_canceled: CancelCheck | None = None,
) -> dict[str, Any]:
    # Backward-compatible entrypoint name while the handler/API wiring is unchanged.
    return await run_agent_translate_page_workflow(
        payload=payload,
        on_progress=on_progress,
        is_canceled=is_canceled,
    )
