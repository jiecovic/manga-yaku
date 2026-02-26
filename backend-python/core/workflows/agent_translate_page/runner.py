from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.usecases.agent.page_translate import run_agent_translate_page
from core.usecases.agent.settings import resolve_agent_translate_settings
from core.usecases.box_detection.engine import detect_text_boxes_for_page
from core.usecases.ocr.profile_settings import agent_enabled_ocr_profiles
from core.usecases.ocr.profiles import get_ocr_profile
from core.usecases.ocr.task_runner import OcrTaskOutcome, run_ocr_task_with_retries
from core.usecases.settings.service import (
    resolve_detection_settings,
    resolve_ocr_parallelism_settings,
)
from infra.db.db_store import (
    delete_boxes_by_ids,
    get_page_index,
    get_volume_context,
    load_page,
    set_box_ocr_text_by_id,
    set_box_order_for_type,
    set_box_translation_by_id,
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_detection_profile_id(preferred_profile_id: str | None) -> str | None:
    if preferred_profile_id:
        return preferred_profile_id
    stored_profile_id = resolve_detection_settings().agent_detection_profile_id
    if stored_profile_id:
        return stored_profile_id
    return None


def _resolve_ocr_profiles(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("ocrProfiles")
    requested = [str(item).strip() for item in raw or [] if str(item).strip()]
    profile_ids = requested or agent_enabled_ocr_profiles()
    if not profile_ids:
        profile_ids = ["manga_ocr_default"]

    resolved: list[str] = []
    seen: set[str] = set()
    for profile_id in profile_ids:
        if profile_id in seen:
            continue
        seen.add(profile_id)
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        if not profile.get("enabled", True):
            continue
        resolved.append(profile_id)

    if not resolved:
        try:
            fallback = get_ocr_profile("manga_ocr_default")
            if fallback.get("enabled", True):
                resolved = ["manga_ocr_default"]
        except Exception:
            pass

    if not resolved:
        raise RuntimeError("No enabled OCR profiles configured")

    return resolved


def _resolve_parallel_limits() -> tuple[int, int]:
    settings = resolve_ocr_parallelism_settings()
    return (settings.local, settings.remote)


def _list_text_boxes(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_boxes = page.get("boxes", []) if isinstance(page, dict) else []
    text_boxes = [box for box in raw_boxes if box.get("type") == "text"]
    text_boxes.sort(
        key=lambda box: (
            int(box.get("orderIndex") or 10**9),
            int(box.get("id") or 0),
        )
    )
    return text_boxes


def _emit_progress(
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
    if on_progress is None:
        return
    on_progress(
        AgentTranslateWorkflowSnapshot(
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


def _is_canceled(check: CancelCheck | None) -> bool:
    return bool(check and check())


def _build_ocr_profile_meta(profile_ids: list[str]) -> list[dict[str, Any]]:
    meta: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        cfg = profile.get("config", {}) or {}
        model = cfg.get("model") or cfg.get("model_path") or profile.get("provider")
        meta.append(
            {
                "id": profile_id,
                "model": str(model) if model is not None else "",
                "hint": profile.get("llm_hint", ""),
            }
        )
    return meta


def _build_translation_boxes(
    *,
    text_boxes: list[dict[str, Any]],
    candidates: dict[int, dict[str, str]],
    no_text_candidates: dict[int, set[str]],
    error_candidates: dict[int, set[str]],
    invalid_candidates: dict[int, set[str]],
    llm_profiles: set[str],
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    payload_boxes: list[dict[str, Any]] = []
    box_index_map: dict[int, int] = {}
    next_box_index = 1

    for box in text_boxes:
        box_id = int(box.get("id") or 0)
        ocr_list = [
            {"profile_id": pid, "text": text}
            for pid, text in candidates.get(box_id, {}).items()
            if isinstance(text, str) and text.strip()
        ]
        raw_index = int(box.get("orderIndex") or 0)
        box_index = raw_index if raw_index > 0 else 0
        if box_index <= 0 or box_index in box_index_map:
            box_index = next_box_index
            while box_index in box_index_map:
                box_index += 1
        box_index_map[box_index] = box_id
        next_box_index = max(next_box_index, box_index + 1)
        no_text_profiles = sorted(pid for pid in no_text_candidates.get(box_id, set()))
        error_profiles = sorted(
            pid for pid in error_candidates.get(box_id, set()) if pid not in llm_profiles
        )
        invalid_profiles = sorted(
            pid for pid in invalid_candidates.get(box_id, set()) if pid not in llm_profiles
        )
        payload_box: dict[str, Any] = {
            "box_index": box_index,
            "ocr_candidates": ocr_list,
        }
        if no_text_profiles:
            payload_box["ocr_no_text_profiles"] = no_text_profiles
        if error_profiles:
            payload_box["ocr_error_profiles"] = error_profiles
        if invalid_profiles:
            payload_box["ocr_invalid_profiles"] = invalid_profiles
        payload_boxes.append(payload_box)

    return payload_boxes, box_index_map


def _apply_translation_payload(
    *,
    volume_id: str,
    filename: str,
    text_boxes: list[dict[str, Any]],
    box_index_map: dict[int, int],
    translation_payload: dict[str, Any],
) -> dict[str, Any]:
    translations = translation_payload.get("boxes", [])
    no_text_raw = translation_payload.get("no_text_boxes")
    no_text_box_indices: set[int] = set()
    if isinstance(no_text_raw, list):
        for item in no_text_raw:
            try:
                no_text_box_indices.add(int(item))
            except (TypeError, ValueError):
                continue

    updated = 0
    merged_ids: list[int] = []
    ordered_primary_ids: list[int] = []

    for entry in translations:
        box_ids_raw = entry.get("box_ids")
        if not isinstance(box_ids_raw, list):
            single_id = entry.get("box_id")
            if single_id is None:
                continue
            box_ids_raw = [single_id]

        box_indices: list[int] = []
        for item in box_ids_raw:
            try:
                box_indices.append(int(item))
            except (TypeError, ValueError):
                continue
        if not box_indices:
            continue
        if any(box_index in no_text_box_indices for box_index in box_indices):
            continue

        mapped_ids = [box_index_map.get(box_index) for box_index in box_indices]
        box_ids = [box_id for box_id in mapped_ids if isinstance(box_id, int)]
        if not box_ids:
            continue

        primary_id = box_ids[0]
        ordered_primary_ids.append(primary_id)
        if len(box_ids) > 1:
            merged_ids.extend(box_ids[1:])

        ocr_text = entry.get("ocr_text")
        if isinstance(ocr_text, str):
            set_box_ocr_text_by_id(
                volume_id,
                filename,
                box_id=primary_id,
                ocr_text=ocr_text,
            )

        translation = entry.get("translation")
        if isinstance(translation, str):
            set_box_translation_by_id(
                volume_id,
                filename,
                box_id=primary_id,
                translation=translation,
            )
            updated += 1

    applied_order = False
    current_ids = {int(box.get("id") or 0) for box in text_boxes}
    mentioned_ids = set(ordered_primary_ids) | set(merged_ids)
    orphaned = list(current_ids - mentioned_ids)
    if orphaned:
        delete_boxes_by_ids(volume_id, filename, orphaned)
    if merged_ids:
        delete_boxes_by_ids(volume_id, filename, merged_ids)

    if ordered_primary_ids:
        applied_order = set_box_order_for_type(
            volume_id,
            filename,
            box_type="text",
            ordered_ids=ordered_primary_ids,
        )

    return {
        "updated": updated,
        "orderApplied": applied_order,
        "processed": len(text_boxes),
        "total": len(text_boxes),
    }


async def run_agent_translate_page_workflow(
    *,
    payload: dict[str, Any],
    on_progress: ProgressCallback | None = None,
    is_canceled: CancelCheck | None = None,
) -> dict[str, Any]:
    request = AgentTranslatePageRequest.from_payload(payload)
    state = WorkflowState.queued
    detection_profile_id = _resolve_detection_profile_id(request.detection_profile_id)
    ocr_profiles = _resolve_ocr_profiles(payload)
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
        page_revision=_utc_now_iso(),
    )
    update_workflow_run(
        workflow_run_id,
        result_json={"request": dict(payload)},
    )

    _emit_progress(
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

    if _is_canceled(is_canceled):
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
        _emit_progress(
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
    _emit_progress(
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
        state = transition(state, WorkflowEvent.detect_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message=str(exc),
        )
        raise

    page = load_page(request.volume_id, request.filename)
    text_boxes = _list_text_boxes(page)
    detected_boxes = len(text_boxes)

    if _is_canceled(is_canceled):
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
        _emit_progress(
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
    _emit_progress(
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
    local_parallelism, remote_parallelism = _resolve_parallel_limits()
    local_sem = asyncio.Semaphore(local_parallelism)
    remote_sem = asyncio.Semaphore(remote_parallelism)

    async def run_one_task(spec: _OcrTaskSpec) -> OcrTaskOutcome | None:
        nonlocal ocr_tasks_done
        if _is_canceled(is_canceled):
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
            if _is_canceled(is_canceled):
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
            _emit_progress(
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

    if _is_canceled(is_canceled):
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
        _emit_progress(
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

    state = transition(state, WorkflowEvent.ocr_succeeded)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
    )
    _emit_progress(
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

    payload_boxes, box_index_map = _build_translation_boxes(
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

    agent_settings = resolve_agent_translate_settings()
    model_id = request.model_id or agent_settings.get("model_id")
    max_output_tokens = agent_settings.get("max_output_tokens")
    reasoning_effort = agent_settings.get("reasoning_effort")
    temperature = agent_settings.get("temperature")

    ocr_profile_meta = _build_ocr_profile_meta(ocr_profiles)
    try:
        translation_payload = await asyncio.to_thread(
            run_agent_translate_page,
            volume_id=request.volume_id,
            filename=request.filename,
            boxes=payload_boxes,
            ocr_profiles=ocr_profile_meta,
            prior_context_summary=prior_summary,
            prior_characters=prior_characters,
            prior_open_threads=prior_open_threads,
            prior_glossary=prior_glossary,
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
        )
    except Exception as exc:
        state = transition(state, WorkflowEvent.translate_failed)
        update_workflow_run(
            workflow_run_id,
            state=state.value,
            status="failed",
            error_message=str(exc),
        )
        raise

    state = transition(state, WorkflowEvent.translate_succeeded)
    update_workflow_run(
        workflow_run_id,
        state=state.value,
        status="running",
    )
    _emit_progress(
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
        commit = _apply_translation_payload(
            volume_id=request.volume_id,
            filename=request.filename,
            text_boxes=text_boxes,
            box_index_map=box_index_map,
            translation_payload=translation_payload,
        )
    except Exception as exc:
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
    _emit_progress(
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
