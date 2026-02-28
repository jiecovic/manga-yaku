# backend-python/tests/core/agent_translate_page/test_agent_workflow_events.py
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

import unittest
from unittest.mock import patch

from core.workflows.agent_translate_page.events import (
    append_ocr_attempt_events,
    append_stage_attempt_event,
    coerce_non_negative_int,
)
from core.workflows.agent_translate_page.stages.merge import (
    create_merge_task_run,
    mark_merge_task_canceled,
)


class WorkflowEventHelpersTests(unittest.TestCase):
    def test_coerce_non_negative_int_handles_types(self) -> None:
        self.assertEqual(coerce_non_negative_int(12), 12)
        self.assertEqual(coerce_non_negative_int(-4), 0)
        self.assertEqual(coerce_non_negative_int("9"), 9)
        self.assertEqual(coerce_non_negative_int("oops"), 0)
        self.assertEqual(coerce_non_negative_int(None), 0)

    def test_append_stage_attempt_event_uses_merge_prompt_version(self) -> None:
        with patch(
            "core.workflows.agent_translate_page.events.append_task_attempt_event"
        ) as append_task_attempt_event:
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

        append_task_attempt_event.assert_called_once()
        kwargs = append_task_attempt_event.call_args.kwargs
        self.assertEqual(kwargs["task_id"], "task-1")
        self.assertEqual(kwargs["attempt"], 2)
        self.assertEqual(kwargs["tool_name"], "merge_state")
        self.assertEqual(kwargs["prompt_version"], "agent_translate_page_merge.yml")
        self.assertEqual(kwargs["latency_ms"], 14)

    def test_append_ocr_attempt_events_forwards_attempt_payload(self) -> None:
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
            "core.workflows.agent_translate_page.events.append_task_attempt_event"
        ) as append_task_attempt_event:
            append_ocr_attempt_events(
                task_id="task-ocr",
                prompt_version="ocr_tool_openai_profile_v1",
                attempt_events=events,
            )

        append_task_attempt_event.assert_called_once()
        kwargs = append_task_attempt_event.call_args.kwargs
        self.assertEqual(kwargs["task_id"], "task-ocr")
        self.assertEqual(kwargs["attempt"], 1)
        self.assertEqual(kwargs["finish_reason"], "invalid")
        self.assertEqual(kwargs["latency_ms"], 22)


class MergeStageHelpersTests(unittest.TestCase):
    def test_create_merge_task_run_uses_expected_payload(self) -> None:
        with patch(
            "core.workflows.agent_translate_page.stages.merge.create_task_run",
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

        self.assertEqual(task_id, "merge-task-1")
        kwargs = create_task_run.call_args.kwargs
        self.assertEqual(kwargs["stage"], "merge_state")
        self.assertEqual(kwargs["profile_id"], "gpt-5-mini")

    def test_mark_merge_task_canceled_writes_terminal_status(self) -> None:
        with patch(
            "core.workflows.agent_translate_page.stages.merge.update_task_run"
        ) as update_task_run:
            mark_merge_task_canceled("merge-task-2", reason="upstream failed")

        update_task_run.assert_called_once()
        kwargs = update_task_run.call_args.kwargs
        self.assertEqual(kwargs["status"], "canceled")
        self.assertEqual(kwargs["error_code"], "upstream_failed")
        self.assertEqual(kwargs["error_detail"], "upstream failed")
