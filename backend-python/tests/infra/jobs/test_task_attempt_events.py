# backend-python/tests/infra/jobs/test_task_attempt_events.py
"""Unit tests for shared task-attempt event persistence helpers."""

from __future__ import annotations

from unittest.mock import patch

from infra.jobs.task_attempt_events import (
    build_reasoning_params_snapshot,
    persist_task_attempt_event,
)


def test_build_reasoning_params_snapshot_coerces_numeric_limit() -> None:
    snapshot = build_reasoning_params_snapshot(
        {
            "max_output_tokens": "1024",
            "reasoning_effort": "medium",
        }
    )

    assert snapshot == {
        "max_output_tokens": 1024,
        "reasoning_effort": "medium",
    }


def test_persist_task_attempt_event_uses_event_defaults_and_updates_attempt() -> None:
    with (
        patch(
            "infra.jobs.task_attempt_events.append_task_attempt_event"
        ) as append_task_attempt_event,
        patch("infra.jobs.task_attempt_events.update_task_run") as update_task_run,
    ):
        attempt = persist_task_attempt_event(
            task_id="task-1",
            attempt_event={
                "attempt_count": "2",
                "model_id": "gpt-5-mini",
                "finish_reason": "stop",
                "latency_ms": "14",
                "params_snapshot": {"max_output_tokens": 768},
                "token_usage": {"input_tokens": 10, "output_tokens": 5},
            },
            tool_name="merge_state",
            prompt_version="page_translation_merge.yml",
        )

    assert attempt == 2
    append_task_attempt_event.assert_called_once()
    kwargs = append_task_attempt_event.call_args.kwargs
    assert kwargs["task_id"] == "task-1"
    assert kwargs["attempt"] == 2
    assert kwargs["tool_name"] == "merge_state"
    assert kwargs["model_id"] == "gpt-5-mini"
    assert kwargs["prompt_version"] == "page_translation_merge.yml"
    assert kwargs["params_snapshot"] == {"max_output_tokens": 768}
    assert kwargs["token_usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert kwargs["finish_reason"] == "stop"
    assert kwargs["latency_ms"] == 14
    update_task_run.assert_called_once_with("task-1", attempt=2)


def test_persist_task_attempt_event_uses_error_defaults_without_counter_update() -> None:
    with (
        patch(
            "infra.jobs.task_attempt_events.append_task_attempt_event"
        ) as append_task_attempt_event,
        patch("infra.jobs.task_attempt_events.update_task_run") as update_task_run,
    ):
        attempt = persist_task_attempt_event(
            task_id="task-2",
            attempt_event={
                "attempt": 0,
                "status": "invalid",
                "latency_ms": 22,
                "error_message": "bad output",
            },
            tool_name="translate_tool",
            prompt_version="translate_v1",
            params_snapshot={"max_output_tokens": None, "reasoning_effort": "low"},
            update_attempt_counter=False,
        )

    assert attempt == 1
    append_task_attempt_event.assert_called_once()
    kwargs = append_task_attempt_event.call_args.kwargs
    assert kwargs["attempt"] == 1
    assert kwargs["finish_reason"] == "invalid"
    assert kwargs["error_detail"] == "bad output"
    assert kwargs["params_snapshot"] == {
        "max_output_tokens": None,
        "reasoning_effort": "low",
    }
    update_task_run.assert_not_called()
