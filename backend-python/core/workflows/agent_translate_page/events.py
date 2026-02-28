# backend-python/core/workflows/agent_translate_page/events.py
"""Event payload definitions for the agent translate page workflow."""

from __future__ import annotations

from typing import Any

from infra.db.workflow_store import append_task_attempt_event

_PROMPT_VERSION_BY_STAGE = {
    "translate_page": "agent_translate_page.yml",
    "merge_state": "agent_translate_page_merge.yml",
}


def coerce_non_negative_int(value: Any) -> int:
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0


def append_stage_attempt_event(
    *,
    task_id: str,
    stage_name: str,
    stage_meta: dict[str, Any] | None,
    fallback_model_id: str | None,
    error_detail: str | None = None,
) -> None:
    meta = stage_meta if isinstance(stage_meta, dict) else {}
    raw_attempt = meta.get("attempt_count", 1)
    try:
        attempt = max(1, int(raw_attempt))
    except (TypeError, ValueError):
        attempt = 1

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
        else ""
    ) or ("error" if error_detail else "completed")

    model_for_event = str(meta.get("model_id") or "").strip() or fallback_model_id
    prompt_version = _PROMPT_VERSION_BY_STAGE.get(stage_name, "agent_translate_page.yml")

    append_task_attempt_event(
        task_id=task_id,
        attempt=attempt,
        tool_name=stage_name,
        model_id=model_for_event,
        prompt_version=prompt_version,
        params_snapshot=params_snapshot,
        token_usage=token_usage,
        finish_reason=finish_reason,
        latency_ms=coerce_non_negative_int(meta.get("latency_ms")),
        error_detail=error_detail,
    )


def append_ocr_attempt_events(
    *,
    task_id: str,
    prompt_version: str,
    attempt_events: list[dict[str, Any]],
) -> None:
    for event in attempt_events:
        append_task_attempt_event(
            task_id=task_id,
            attempt=max(1, coerce_non_negative_int(event.get("attempt")) or 1),
            tool_name="ocr_tool",
            model_id=event.get("model_id"),
            prompt_version=prompt_version,
            params_snapshot={
                "max_output_tokens": event.get("max_output_tokens"),
                "reasoning_effort": event.get("reasoning_effort"),
            },
            finish_reason=event.get("status"),
            latency_ms=coerce_non_negative_int(event.get("latency_ms")),
            error_detail=event.get("error_message"),
        )
