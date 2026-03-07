# backend-python/infra/jobs/task_attempt_events.py
"""Shared task-attempt event persistence helpers for workers and workflows."""

from __future__ import annotations

from typing import Any

from infra.db.workflow_store import append_task_attempt_event, update_task_run


def coerce_non_negative_int(value: Any) -> int:
    """Coerce mixed input types into a non-negative integer."""
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


def coerce_attempt_number(value: Any) -> int:
    """Coerce an attempt number and clamp it to the persisted minimum of 1."""
    return max(1, coerce_non_negative_int(value) or 1)


def build_reasoning_params_snapshot(attempt_event: dict[str, Any] | None) -> dict[str, Any]:
    """Build the shared params snapshot shape used by OCR/translation attempts."""
    event = attempt_event if isinstance(attempt_event, dict) else {}
    max_output_raw = event.get("max_output_tokens")
    max_output_tokens = None
    if max_output_raw is not None:
        max_output_tokens = coerce_non_negative_int(max_output_raw) or None
    return {
        "max_output_tokens": max_output_tokens,
        "reasoning_effort": event.get("reasoning_effort"),
    }


def _coerce_optional_mapping(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return dict(value)


def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def persist_task_attempt_event(
    *,
    task_id: str,
    attempt_event: dict[str, Any] | None,
    tool_name: str,
    prompt_version: str,
    fallback_model_id: str | None = None,
    params_snapshot: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    error_detail: str | None = None,
    update_attempt_counter: bool = True,
) -> int:
    """Persist one task-attempt event and optionally mirror the attempt on the task row."""
    event = attempt_event if isinstance(attempt_event, dict) else {}
    attempt = coerce_attempt_number(event.get("attempt_count", event.get("attempt", 1)))

    normalized_params_snapshot = (
        dict(params_snapshot)
        if isinstance(params_snapshot, dict)
        else _coerce_optional_mapping(event.get("params_snapshot"))
    )
    normalized_token_usage = (
        dict(token_usage)
        if isinstance(token_usage, dict)
        else _coerce_optional_mapping(event.get("token_usage"))
    )
    normalized_finish_reason = _coerce_optional_text(finish_reason)
    if normalized_finish_reason is None:
        normalized_finish_reason = _coerce_optional_text(event.get("finish_reason"))
    if normalized_finish_reason is None:
        normalized_finish_reason = _coerce_optional_text(event.get("status"))
    normalized_error_detail = _coerce_optional_text(error_detail)
    if normalized_error_detail is None:
        normalized_error_detail = _coerce_optional_text(event.get("error_message"))
    if normalized_finish_reason is None:
        normalized_finish_reason = "error" if normalized_error_detail else "completed"

    append_task_attempt_event(
        task_id=task_id,
        attempt=attempt,
        tool_name=tool_name,
        model_id=str(event.get("model_id") or "").strip() or fallback_model_id,
        prompt_version=prompt_version,
        params_snapshot=normalized_params_snapshot,
        token_usage=normalized_token_usage,
        finish_reason=normalized_finish_reason,
        latency_ms=coerce_non_negative_int(event.get("latency_ms")),
        error_detail=normalized_error_detail,
    )
    if update_attempt_counter:
        update_task_run(task_id, attempt=attempt)
    return attempt
