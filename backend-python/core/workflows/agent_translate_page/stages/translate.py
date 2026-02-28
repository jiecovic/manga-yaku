"""Workflow stage handler for agent translate page: translate."""

from __future__ import annotations

import asyncio
from threading import Event
from typing import Any

from config import AGENT_TRANSLATE_TIMEOUT_SECONDS
from infra.db.workflow_store import create_task_run, update_task_run

from ..events import append_stage_attempt_event
from .merge import create_merge_task_run, mark_merge_task_canceled


class TranslateStageError(RuntimeError):
    """Raised when the translation stage fails."""


async def run_translate_stage(
    *,
    workflow_run_id: str,
    volume_id: str,
    filename: str,
    source_language: str,
    target_language: str,
    boxes: list[dict[str, Any]],
    ocr_profiles: list[dict[str, Any]],
    prior_context_summary: str,
    prior_characters: list[Any],
    prior_open_threads: list[Any],
    prior_glossary: list[Any],
    model_id: str | None,
    max_output_tokens: int | float | None,
    reasoning_effort: str | None,
    temperature: int | float | None,
    merge_max_output_tokens: int | float | None,
    merge_reasoning_effort: str | None,
) -> dict[str, Any]:
    """Run translate stage."""
    from core.usecases.agent.page_translate import run_agent_translate_page

    resolved_model_id = str(model_id).strip() if isinstance(model_id, str) else ""
    if not resolved_model_id:
        resolved_model_id = None

    translate_task_run_id = create_task_run(
        workflow_id=workflow_run_id,
        stage="translate_page",
        status="queued",
        profile_id=resolved_model_id,
        input_json={
            "volume_id": volume_id,
            "filename": filename,
            "source_language": source_language,
            "target_language": target_language,
            "model_id": resolved_model_id,
        },
    )
    merge_task_run_id = create_merge_task_run(
        workflow_run_id=workflow_run_id,
        volume_id=volume_id,
        filename=filename,
        source_language=source_language,
        target_language=target_language,
        model_id=resolved_model_id,
    )
    stage_task_ids = {
        "translate_page": translate_task_run_id,
        "merge_state": merge_task_run_id,
    }

    stop_event = Event()

    def on_agent_stage_event(
        stage_name: str,
        status_name: str,
        payload_meta: dict[str, Any] | None,
    ) -> None:
        if stop_event.is_set():
            return
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
        warning_detail = str(meta.get("merge_warning") or "").strip() if is_success else ""
        if warning_detail:
            error_detail = warning_detail
        elif not is_success:
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
        model_for_event = str(meta.get("model_id") or "").strip() or resolved_model_id
        append_stage_attempt_event(
            task_id=task_run_id,
            stage_name=stage_name,
            stage_meta={
                **meta,
                "attempt_count": attempt,
                "params_snapshot": params_snapshot,
                "token_usage": token_usage,
                "finish_reason": finish_reason,
            },
            fallback_model_id=model_for_event,
            error_detail=error_detail,
        )

    translation_timeout_seconds = max(30, int(AGENT_TRANSLATE_TIMEOUT_SECONDS))
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                run_agent_translate_page,
                volume_id=volume_id,
                filename=filename,
                boxes=boxes,
                ocr_profiles=ocr_profiles,
                prior_context_summary=prior_context_summary,
                prior_characters=prior_characters,
                prior_open_threads=prior_open_threads,
                prior_glossary=prior_glossary,
                source_language=source_language,
                target_language=target_language,
                model_id=model_id,
                debug_id=workflow_run_id,
                max_output_tokens=(
                    int(max_output_tokens)
                    if isinstance(max_output_tokens, int | float)
                    else None
                ),
                reasoning_effort=(
                    str(reasoning_effort) if isinstance(reasoning_effort, str) else None
                ),
                temperature=(
                    float(temperature) if isinstance(temperature, int | float) else None
                ),
                merge_max_output_tokens=(
                    int(merge_max_output_tokens)
                    if isinstance(merge_max_output_tokens, int | float)
                    else None
                ),
                merge_reasoning_effort=(
                    str(merge_reasoning_effort)
                    if isinstance(merge_reasoning_effort, str)
                    else None
                ),
                on_stage_event=on_agent_stage_event,
                stop_event=stop_event,
            ),
            timeout=float(translation_timeout_seconds),
        )
    except asyncio.TimeoutError:
        stop_event.set()
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
        mark_merge_task_canceled(
            merge_task_run_id,
            reason="Skipped because translate stage failed",
        )
        raise TranslateStageError(error_message) from None
    except Exception as exc:
        stop_event.set()
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
        mark_merge_task_canceled(
            merge_task_run_id,
            reason="Skipped because translate stage failed",
        )
        raise TranslateStageError(error_message) from exc
