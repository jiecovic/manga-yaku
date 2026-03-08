# backend-python/tests/core/page_translation/test_page_translation_workflow_events.py
"""Unit tests for workflow attempt-event helpers and merge task utilities.

What is tested:
- Stage event payload mapping into persisted task-attempt events.
- OCR event coercion and prompt-version forwarding.
- Merge-task helper behavior for create and canceled terminal updates.

How it is tested:
- Direct helper invocation with patched workflow-store functions.
- Deterministic payload assertions without DB or worker loops.
"""

from __future__ import annotations

from unittest.mock import patch

from core.workflows.page_translation.persistence.events import (
    append_ocr_attempt_events,
    append_stage_attempt_event,
    coerce_non_negative_int,
)
from core.workflows.page_translation.stages.merge import (
    create_merge_task_run,
    mark_merge_task_canceled,
)


def test_coerce_non_negative_int_handles_types() -> None:
    assert coerce_non_negative_int(12) == 12
    assert coerce_non_negative_int(-4) == 0
    assert coerce_non_negative_int("9") == 9
    assert coerce_non_negative_int("oops") == 0
    assert coerce_non_negative_int(None) == 0


def test_append_stage_attempt_event_uses_merge_prompt_version() -> None:
    with patch(
        "core.workflows.page_translation.persistence.events.persist_task_attempt_event"
    ) as persist_task_attempt_event:
        append_stage_attempt_event(
            task_id="task-1",
            stage_name="merge_state",
            stage_meta={
                "attempt_count": 2,
                "model_id": "gpt-5-mini",
                "finish_reason": "stop",
                "latency_ms": "14",
                "params_snapshot": {"max_output_tokens": 768},
                "token_usage": {"input_tokens": 10, "output_tokens": 5},
            },
            fallback_model_id=None,
        )

    persist_task_attempt_event.assert_called_once()
    kwargs = persist_task_attempt_event.call_args.kwargs
    assert kwargs["task_id"] == "task-1"
    assert kwargs["tool_name"] == "merge_state"
    assert kwargs["prompt_version"] == "page_translation/merge.yml"
    assert kwargs["attempt_event"]["attempt_count"] == 2
    assert kwargs["attempt_event"]["latency_ms"] == "14"


def test_append_ocr_attempt_events_forwards_attempt_payload() -> None:
    events = [
        {
            "attempt": 1,
            "status": "invalid",
            "latency_ms": "22",
            "model_id": "gpt-5-mini",
            "max_output_tokens": 512,
            "reasoning_effort": "low",
            "error_message": "empty OCR output",
        }
    ]
    with patch(
        "core.workflows.page_translation.persistence.events.persist_task_attempt_event"
    ) as persist_task_attempt_event:
        append_ocr_attempt_events(
            task_id="task-ocr",
            prompt_version="ocr_tool_openai_profile_v1",
            attempt_events=events,
        )

    persist_task_attempt_event.assert_called_once()
    kwargs = persist_task_attempt_event.call_args.kwargs
    assert kwargs["task_id"] == "task-ocr"
    assert kwargs["attempt_event"]["attempt"] == 1
    assert kwargs["params_snapshot"] == {
        "max_output_tokens": 512,
        "reasoning_effort": "low",
    }


def test_create_merge_task_run_uses_expected_payload() -> None:
    with patch(
        "core.workflows.page_translation.stages.merge.create_task_run",
        return_value="merge-task-1",
    ) as create_task_run:
        task_id = create_merge_task_run(
            workflow_run_id="wf-1",
            volume_id="vol",
            filename="001.jpg",
            source_language="Japanese",
            target_language="English",
            model_id="gpt-5-mini",
        )

    assert task_id == "merge-task-1"
    kwargs = create_task_run.call_args.kwargs
    assert kwargs["stage"] == "merge_state"
    assert kwargs["profile_id"] == "gpt-5-mini"


def test_mark_merge_task_canceled_writes_terminal_status() -> None:
    with patch("core.workflows.page_translation.stages.merge.update_task_run") as update_task_run:
        mark_merge_task_canceled("merge-task-2", reason="upstream failed")

    update_task_run.assert_called_once()
    kwargs = update_task_run.call_args.kwargs
    assert kwargs["status"] == "canceled"
    assert kwargs["error_code"] == "upstream_failed"
    assert kwargs["error_detail"] == "upstream failed"
