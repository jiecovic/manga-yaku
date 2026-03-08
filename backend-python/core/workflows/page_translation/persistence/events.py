# backend-python/core/workflows/page_translation/persistence/events.py
"""Event payload definitions for the page-translation workflow."""

from __future__ import annotations

from typing import Any

from infra.jobs.task_attempt_events import (
    build_reasoning_params_snapshot,
    persist_task_attempt_event,
)
from infra.jobs.task_attempt_events import (
    coerce_non_negative_int as _coerce_non_negative_int,
)

_PROMPT_VERSION_BY_STAGE = {
    "translate_page": "page_translation/translate.yml",
    "merge_state": "page_translation/merge.yml",
}


def coerce_non_negative_int(value: Any) -> int:
    """Coerce mixed input types into a non-negative integer."""
    return _coerce_non_negative_int(value)


def append_stage_attempt_event(
    *,
    task_id: str,
    stage_name: str,
    stage_meta: dict[str, Any] | None,
    fallback_model_id: str | None,
    error_detail: str | None = None,
) -> None:
    """Handle append stage attempt event."""
    prompt_version = _PROMPT_VERSION_BY_STAGE.get(stage_name, "page_translation/translate.yml")
    persist_task_attempt_event(
        task_id=task_id,
        attempt_event=stage_meta,
        tool_name=stage_name,
        prompt_version=prompt_version,
        fallback_model_id=fallback_model_id,
        error_detail=error_detail,
    )


def append_ocr_attempt_events(
    *,
    task_id: str,
    prompt_version: str,
    attempt_events: list[dict[str, Any]],
) -> None:
    """Handle append ocr attempt events."""
    for event in attempt_events:
        persist_task_attempt_event(
            task_id=task_id,
            attempt_event=event,
            tool_name="ocr_tool",
            prompt_version=prompt_version,
            params_snapshot=build_reasoning_params_snapshot(event),
        )
