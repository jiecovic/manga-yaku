from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from config import AGENT_TRANSLATE_TIMEOUT_SECONDS
from core.usecases.agent.page_translate import run_agent_translate_page
from core.usecases.agent.settings import resolve_agent_translate_settings
from core.usecases.box_detection.engine import detect_text_boxes_for_page
from core.usecases.ocr.profiles import get_ocr_profile
from core.usecases.ocr.task_runner import OcrTaskOutcome, run_ocr_task_with_retries
from core.usecases.settings.service import get_setting_value
from infra.db.db_store import (
    get_page_index,
    get_volume_context,
    load_page,
    set_box_ocr_text_by_id,
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

from .helpers import (
    apply_translation_payload,
    build_ocr_profile_meta,
    build_translation_boxes,
    emit_progress,
    list_text_boxes,
    resolve_detection_profile_id,
    resolve_ocr_profiles,
    resolve_parallel_limits,
    utc_now_iso,
)
from .helpers import (
    is_canceled as is_cancel_requested,
)
from .state_machine import transition
from .types import (
    AgentTranslatePageRequest,
    AgentTranslateWorkflowSnapshot,
    CancelCheck,
    ProgressCallback,
    WorkflowEvent,
    WorkflowState,
)


@dataclass(frozen=True)
class _OcrTaskSpec:
    task_run_id: str
    box_id: int
    profile_id: str
    x: float
    y: float
    width: float
    height: float


def _get_bool_setting(key: str, *, default: bool) -> bool:
    raw = get_setting_value(key)
    return bool(raw) if isinstance(raw, bool) else default


async def run_agent_translate_page_workflow(
    *,
    payload: dict[str, Any],
    on_progress: ProgressCallback | None = None,
    is_canceled: CancelCheck | None = None,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    run_started_at = loop.time()
    stage_started_at: dict[str, float] = {}
    stage_durations_ms: dict[str, int] = {}

    def mark_stage_started(stage_name: str) -> None:
        stage_started_at[stage_name] = loop.time()

    def mark_stage_finished(stage_name: str) -> None:
        started = stage_started_at.get(stage_name)
        if started is None:
            return
        elapsed_ms = int((loop.time() - started) * 1000)
        stage_durations_ms[stage_name] = max(0, elapsed_ms)

    request = AgentTranslatePageRequest.from_payload(payload)
    state = WorkflowState.queued
    detection_profile_id = resolve_detection_profile_id(request.detection_profile_id)
    ocr_profiles = resolve_ocr_profiles(payload)
    detected_boxes = 0
    ocr_tasks_total = 0
    ocr_tasks_done = 0
    updated_boxes = 0

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

    emit_progress(
        state=state,
        stage="queued",
        progress=0,
        message="Queued",
        detection_profile_id=detection_profile_id,
        detected_boxes=detected_boxes,
        ocr_tasks_total=ocr_tasks_total,
        ocr_tasks_done=ocr_tasks_done,
        updated_boxes=updated_boxes,
        workflow_run_id=workflow_run_id,
        on_progress=on_progress,
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
            detection_profile_id=detection_profile_id,
            detected_boxes=detected_boxes,
            workflow_run_id=workflow_run_id,
        )
        emit_progress(
            state=state,
            stage=snapshot.stage,
            progress=snapshot.progress,
            message=snapshot.message,
            detection_profile_id=detection_profile_id,
            detected_boxes=detected_boxes,
            ocr_tasks_total=ocr_tasks_total,
            ocr_tasks_done=ocr_tasks_done,
            updated_boxes=updated_boxes,
            workflow_run_id=workflow_run_id,
            on_progress=on_progress,
        )
        return snapshot.to_result()

    state = transition(state, WorkflowEvent.start_requested)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
    )
    mark_stage_started("detect")
    emit_progress(
        state=state,
        stage="detect_boxes",
        progress=5,
        message="Detecting text boxes",
        detection_profile_id=detection_profile_id,
        detected_boxes=detected_boxes,
        ocr_tasks_total=ocr_tasks_total,
        ocr_tasks_done=ocr_tasks_done,
        updated_boxes=updated_boxes,
        workflow_run_id=workflow_run_id,
        on_progress=on_progress,
    )

    try:
        await asyncio.to_thread(
            detect_text_boxes_for_page,
            request.volume_id,
            request.filename,
            detection_profile_id,
            replace_existing=True,
        )
    except Exception as exc:
        mark_stage_finished("detect")
        state = transition(state, WorkflowEvent.detect_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message=str(exc),
        )
        raise

    page = load_page(request.volume_id, request.filename)
    text_boxes = list_text_boxes(page)
    detected_boxes = len(text_boxes)
    mark_stage_finished("detect")

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
            detection_profile_id=detection_profile_id,
            detected_boxes=detected_boxes,
            workflow_run_id=workflow_run_id,
        )
        emit_progress(
            state=state,
            stage=snapshot.stage,
            progress=snapshot.progress,
            message=snapshot.message,
            detection_profile_id=detection_profile_id,
            detected_boxes=detected_boxes,
            ocr_tasks_total=ocr_tasks_total,
            ocr_tasks_done=ocr_tasks_done,
            updated_boxes=updated_boxes,
            workflow_run_id=workflow_run_id,
            on_progress=on_progress,
        )
        return snapshot.to_result()

    state = transition(state, WorkflowEvent.detect_succeeded)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
    )
    mark_stage_started("ocr")
    emit_progress(
        state=state,
        stage="ocr_fanout",
        progress=20,
        message=f"Detected {detected_boxes} text boxes",
        detection_profile_id=detection_profile_id,
        detected_boxes=detected_boxes,
        ocr_tasks_total=ocr_tasks_total,
        ocr_tasks_done=ocr_tasks_done,
        updated_boxes=updated_boxes,
        workflow_run_id=workflow_run_id,
        on_progress=on_progress,
    )

    candidates: dict[int, dict[str, str]] = {}
    no_text_candidates: dict[int, set[str]] = {}
    error_candidates: dict[int, set[str]] = {}
    invalid_candidates: dict[int, set[str]] = {}
    llm_profiles: set[str] = set()
    for profile_id in ocr_profiles:
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        if profile.get("provider") in {"llm_ocr", "llm_ocr_chat"}:
            llm_profiles.add(profile_id)

    specs: list[_OcrTaskSpec] = []
    for profile_id in ocr_profiles:
        for box in text_boxes:
            box_id = int(box.get("id") or 0)
            if box_id <= 0:
                continue
            task_run_id = create_task_run(
                workflow_id=workflow_run_id,
                stage="ocr",
                status="queued",
                box_id=box_id,
                profile_id=profile_id,
                input_json={
                    "volume_id": request.volume_id,
                    "filename": request.filename,
                    "box_id": box_id,
                    "profile_id": profile_id,
                    "x": float(box.get("x") or 0.0),
                    "y": float(box.get("y") or 0.0),
                    "width": float(box.get("width") or 0.0),
                    "height": float(box.get("height") or 0.0),
                },
            )
            specs.append(
                _OcrTaskSpec(
                    task_run_id=task_run_id,
                    box_id=box_id,
                    profile_id=profile_id,
                    x=float(box.get("x") or 0.0),
                    y=float(box.get("y") or 0.0),
                    width=float(box.get("width") or 0.0),
                    height=float(box.get("height") or 0.0),
                )
            )

    ocr_tasks_total = len(specs)
    local_parallelism, remote_parallelism = resolve_parallel_limits()
    local_sem = asyncio.Semaphore(local_parallelism)
    remote_sem = asyncio.Semaphore(remote_parallelism)

    async def run_one_task(spec: _OcrTaskSpec) -> OcrTaskOutcome | None:
        nonlocal ocr_tasks_done
        if is_cancel_requested(is_canceled):
            update_task_run(
                spec.task_run_id,
                status="canceled",
                finished=True,
                error_code="cancel_requested",
                error_detail="Canceled before OCR task execution",
            )
            return None

        profile = get_ocr_profile(spec.profile_id)
        sem = (
            remote_sem
            if profile.get("provider") in {"llm_ocr", "llm_ocr_chat"}
            else local_sem
        )
        async with sem:
            if is_cancel_requested(is_canceled):
                update_task_run(
                    spec.task_run_id,
                    status="canceled",
                    finished=True,
                    error_code="cancel_requested",
                    error_detail="Canceled before OCR task execution",
                )
                return None

            update_task_run(
                spec.task_run_id,
                status="running",
                attempt=1,
                started=True,
            )

            attempt_events: list[dict[str, Any]] = []

            def on_attempt(event: dict[str, Any]) -> None:
                attempt_events.append(event)

            outcome = await asyncio.to_thread(
                run_ocr_task_with_retries,
                profile_id=spec.profile_id,
                volume_id=request.volume_id,
                filename=request.filename,
                box_id=spec.box_id,
                x=spec.x,
                y=spec.y,
                width=spec.width,
                height=spec.height,
                on_attempt=on_attempt,
            )

            for event in attempt_events:
                append_task_attempt_event(
                    task_id=spec.task_run_id,
                    attempt=int(event.get("attempt") or 1),
                    tool_name="ocr_tool",
                    model_id=event.get("model_id"),
                    prompt_version="ocr_default.yml",
                    params_snapshot={
                        "max_output_tokens": event.get("max_output_tokens"),
                        "reasoning_effort": event.get("reasoning_effort"),
                    },
                    finish_reason=event.get("status"),
                    latency_ms=int(event.get("latency_ms") or 0),
                    error_detail=event.get("error_message"),
                )

            terminal_status = "completed" if outcome.status in {"ok", "no_text"} else "failed"
            update_task_run(
                spec.task_run_id,
                status=terminal_status,
                attempt=outcome.attempt,
                error_code=None if terminal_status == "completed" else outcome.status,
                error_detail=outcome.error_message,
                result_json=outcome.to_result_json(),
                finished=True,
            )

            ocr_tasks_done += 1
            progress = 20 + int((ocr_tasks_done / max(ocr_tasks_total, 1)) * 50)
            emit_progress(
                state=state,
                stage="ocr_running",
                progress=progress,
                message=f"OCR {ocr_tasks_done}/{ocr_tasks_total}",
                detection_profile_id=detection_profile_id,
                detected_boxes=detected_boxes,
                ocr_tasks_total=ocr_tasks_total,
                ocr_tasks_done=ocr_tasks_done,
                updated_boxes=updated_boxes,
                workflow_run_id=workflow_run_id,
                on_progress=on_progress,
            )
            return outcome

    outcomes: list[OcrTaskOutcome] = []
    if specs:
        raw_outcomes = await asyncio.gather(*(run_one_task(spec) for spec in specs))
        outcomes = [item for item in raw_outcomes if item is not None]

    if is_cancel_requested(is_canceled):
        mark_stage_finished("ocr")
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
            detection_profile_id=detection_profile_id,
            detected_boxes=detected_boxes,
            ocr_tasks_total=ocr_tasks_total,
            ocr_tasks_done=ocr_tasks_done,
            updated_boxes=updated_boxes,
            workflow_run_id=workflow_run_id,
        )
        emit_progress(
            state=state,
            stage=snapshot.stage,
            progress=snapshot.progress,
            message=snapshot.message,
            detection_profile_id=detection_profile_id,
            detected_boxes=detected_boxes,
            ocr_tasks_total=ocr_tasks_total,
            ocr_tasks_done=ocr_tasks_done,
            updated_boxes=updated_boxes,
            workflow_run_id=workflow_run_id,
            on_progress=on_progress,
        )
        return snapshot.to_result()

    usable_ocr = False
    for outcome in outcomes:
        box_id = outcome.box_id
        if outcome.status == "ok":
            candidates.setdefault(box_id, {})[outcome.profile_id] = outcome.text
            usable_ocr = True
        elif outcome.status == "no_text":
            no_text_candidates.setdefault(box_id, set()).add(outcome.profile_id)
            usable_ocr = True
        elif outcome.status == "invalid":
            invalid_candidates.setdefault(box_id, set()).add(outcome.profile_id)
        elif outcome.status == "error":
            error_candidates.setdefault(box_id, set()).add(outcome.profile_id)

    if not usable_ocr and ocr_tasks_total > 0:
        mark_stage_finished("ocr")
        state = transition(state, WorkflowEvent.ocr_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message="OCR failed for all tasks",
        )
        raise RuntimeError("OCR stage failed for all tasks")

    preferred_profile = ocr_profiles[0] if ocr_profiles else ""
    for box in text_boxes:
        box_id = int(box.get("id") or 0)
        per_box = candidates.get(box_id, {})
        chosen = per_box.get(preferred_profile, "") if preferred_profile else ""
        if not chosen:
            for value in per_box.values():
                if value:
                    chosen = value
                    break
        if chosen:
            set_box_ocr_text_by_id(
                request.volume_id,
                request.filename,
                box_id=box_id,
                ocr_text=chosen,
            )

    mark_stage_finished("ocr")
    state = transition(state, WorkflowEvent.ocr_succeeded)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
    )
    mark_stage_started("translate")
    emit_progress(
        state=state,
        stage="translating",
        progress=75,
        message="Translating page",
        detection_profile_id=detection_profile_id,
        detected_boxes=detected_boxes,
        ocr_tasks_total=ocr_tasks_total,
        ocr_tasks_done=ocr_tasks_done,
        updated_boxes=updated_boxes,
        workflow_run_id=workflow_run_id,
        on_progress=on_progress,
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
        mark_stage_finished("translate")
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
        mark_stage_finished("translate")
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

    mark_stage_finished("translate")
    state = transition(state, WorkflowEvent.translate_succeeded)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
    )
    mark_stage_started("commit")
    emit_progress(
        state=state,
        stage="commit",
        progress=90,
        message="Applying translated output",
        detection_profile_id=detection_profile_id,
        detected_boxes=detected_boxes,
        ocr_tasks_total=ocr_tasks_total,
        ocr_tasks_done=ocr_tasks_done,
        updated_boxes=updated_boxes,
        workflow_run_id=workflow_run_id,
        on_progress=on_progress,
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
        mark_stage_finished("commit")
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
    mark_stage_finished("commit")

    updated_boxes = int(commit.get("updated") or 0)
    state = transition(state, WorkflowEvent.commit_succeeded)
    result = {
        "state": state.value,
        "stage": "completed",
        "processed": int(commit.get("processed") or 0),
        "total": int(commit.get("total") or 0),
        "updated": updated_boxes,
        "orderApplied": bool(commit.get("orderApplied")),
        "detectionProfileId": detection_profile_id,
        "workflowRunId": workflow_run_id,
        "characters": characters,
        "imageSummary": image_summary if isinstance(image_summary, str) else None,
        "storySummary": story_summary if isinstance(story_summary, str) else None,
        "openThreads": open_threads,
        "glossary": glossary,
        "duration_ms": max(0, int((loop.time() - run_started_at) * 1000)),
        "stage_durations_ms": dict(stage_durations_ms),
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
    emit_progress(
        state=state,
        stage="completed",
        progress=100,
        message="Agent translation complete",
        detection_profile_id=detection_profile_id,
        detected_boxes=detected_boxes,
        ocr_tasks_total=ocr_tasks_total,
        ocr_tasks_done=ocr_tasks_done,
        updated_boxes=updated_boxes,
        workflow_run_id=workflow_run_id,
        on_progress=on_progress,
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
