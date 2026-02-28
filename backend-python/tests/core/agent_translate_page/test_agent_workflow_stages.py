# backend-python/tests/core/agent_translate_page/test_agent_workflow_stages.py
"""Unit tests for extracted agent workflow stage modules.

What is tested:
- Commit stage persistence mapping and normalized output shaping.
- Translate stage success/error paths and stage-specific exception behavior.
- Status/progress side effects emitted by stage handlers.

How it is tested:
- Async stage calls with mocked DB, OCR, and LLM integration boundaries.
- Stage contracts are asserted without running the full workflow loop.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from core.workflows.agent_translate_page.stages.commit import run_commit_stage
from core.workflows.agent_translate_page.stages.translate import (
    TranslateStageError,
    run_translate_stage,
)


class CommitStageTests(unittest.TestCase):
    def test_run_commit_stage_persists_context_and_returns_normalized_result(self) -> None:
        translation_payload = {
            "story_summary": "story",
            "image_summary": "image",
            "characters": {"unexpected": "object"},
            "open_threads": ["thread"],
            "glossary": "unexpected",
        }
        with (
            patch(
                "core.workflows.agent_translate_page.stages.commit.apply_translation_payload",
                return_value={
                    "processed": 3,
                    "total": 3,
                    "updated": 2,
                    "orderApplied": True,
                },
            ),
            patch(
                "core.workflows.agent_translate_page.stages.commit.get_page_index",
                return_value=7.0,
            ),
            patch(
                "core.workflows.agent_translate_page.stages.commit.upsert_volume_context",
            ) as upsert_volume_context,
            patch(
                "core.workflows.agent_translate_page.stages.commit.upsert_page_context",
            ) as upsert_page_context,
        ):
            result = run_commit_stage(
                volume_id="vol",
                filename="001.jpg",
                text_boxes=[{"id": 1}],
                box_index_map={1: 1},
                translation_payload=translation_payload,
                prior_summary="prior",
            )

        self.assertEqual(result.processed, 3)
        self.assertEqual(result.total, 3)
        self.assertEqual(result.updated, 2)
        self.assertTrue(result.order_applied)
        self.assertEqual(result.story_summary, "story")
        self.assertEqual(result.image_summary, "image")
        self.assertEqual(result.characters, [])
        self.assertEqual(result.open_threads, ["thread"])
        self.assertEqual(result.glossary, [])

        upsert_volume_context.assert_called_once()
        upsert_page_context.assert_called_once()


class TranslateStageTests(unittest.TestCase):
    def test_run_translate_stage_success(self) -> None:
        update_calls: list[dict] = []

        def fake_update_task_run(task_id: str, **kwargs: object) -> None:
            update_calls.append({"task_id": task_id, **kwargs})

        async def fake_to_thread(_fn: object, **kwargs: object) -> dict[str, object]:
            # Simulate both stage callbacks to verify event -> task status mapping.
            on_stage_event = kwargs.get("on_stage_event")
            if not callable(on_stage_event):
                raise AssertionError("missing on_stage_event callback")
            stop_event = kwargs.get("stop_event")
            if stop_event is None or not hasattr(stop_event, "is_set"):
                raise AssertionError("missing stop_event")
            on_stage_event("translate_page", "started", {"attempt_count": 1})
            on_stage_event(
                "translate_page",
                "succeeded",
                {
                    "attempt_count": 1,
                    "model_id": "gpt-5-mini",
                    "finish_reason": "stop",
                    "latency_ms": "25",
                    "params_snapshot": {"max_output_tokens": 1024},
                    "token_usage": {"input_tokens": 10, "output_tokens": 5},
                },
            )
            on_stage_event("merge_state", "started", {"attempt_count": 1})
            on_stage_event(
                "merge_state",
                "succeeded",
                {
                    "attempt_count": 1,
                    "finish_reason": "fallback",
                    "latency_ms": 11,
                    "merge_warning": "merge fallback applied",
                },
            )
            return {"boxes": [], "no_text_boxes": []}

        with (
            patch(
                "core.workflows.agent_translate_page.stages.translate.create_task_run",
                return_value="task-translate",
            ) as create_task_run,
            patch(
                "core.workflows.agent_translate_page.stages.translate.create_merge_task_run",
                return_value="task-merge",
            ) as create_merge_task_run,
            patch(
                "core.workflows.agent_translate_page.stages.translate.update_task_run",
                side_effect=fake_update_task_run,
            ),
            patch(
                "core.workflows.agent_translate_page.stages.translate.append_stage_attempt_event",
            ) as append_stage_attempt_event,
            patch(
                "core.workflows.agent_translate_page.stages.translate.asyncio.to_thread",
                side_effect=fake_to_thread,
            ),
        ):
            result = asyncio.run(
                run_translate_stage(
                    workflow_run_id="wf-1",
                    volume_id="vol",
                    filename="001.jpg",
                    source_language="Japanese",
                    target_language="English",
                    boxes=[{"box_index": 1}],
                    ocr_profiles=[{"id": "manga_ocr_default"}],
                    prior_context_summary="",
                    prior_characters=[],
                    prior_open_threads=[],
                    prior_glossary=[],
                    model_id="gpt-5-mini",
                    max_output_tokens=1024,
                    reasoning_effort="low",
                    temperature=None,
                    merge_max_output_tokens=768,
                    merge_reasoning_effort="low",
                )
            )

        self.assertEqual(result, {"boxes": [], "no_text_boxes": []})
        self.assertEqual(create_task_run.call_count, 1)
        create_merge_task_run.assert_called_once()
        self.assertEqual(append_stage_attempt_event.call_count, 2)
        self.assertTrue(
            any(
                call.get("status") == "running" and call.get("task_id") == "task-translate"
                for call in update_calls
            )
        )
        self.assertTrue(
            any(
                call.get("status") == "completed" and call.get("task_id") == "task-merge"
                for call in update_calls
            )
        )
        self.assertTrue(
            any(
                call.get("task_id") == "task-merge"
                and call.get("error_detail") == "merge fallback applied"
                for call in update_calls
            )
        )

    def test_run_translate_stage_failure_marks_merge_canceled(self) -> None:
        # When translate fails, pre-created merge task should be canceled,
        # not left in queued/running state.
        status_by_task: dict[str, list[str]] = {"task-translate": [], "task-merge": []}

        def fake_update_task_run(task_id: str, **kwargs: object) -> None:
            status = kwargs.get("status")
            if isinstance(status, str) and task_id in status_by_task:
                status_by_task[task_id].append(status)

        async def fake_to_thread_failure(_fn: object, **_: object) -> dict[str, object]:
            raise RuntimeError("boom")

        with (
            patch(
                "core.workflows.agent_translate_page.stages.translate.create_task_run",
                return_value="task-translate",
            ),
            patch(
                "core.workflows.agent_translate_page.stages.translate.create_merge_task_run",
                return_value="task-merge",
            ),
            patch(
                "core.workflows.agent_translate_page.stages.translate.update_task_run",
                side_effect=fake_update_task_run,
            ),
            patch("core.workflows.agent_translate_page.stages.translate.append_stage_attempt_event"),
            patch(
                "core.workflows.agent_translate_page.stages.translate.mark_merge_task_canceled",
                side_effect=lambda task_id, **kwargs: fake_update_task_run(
                    task_id, status="canceled", **kwargs
                ),
            ),
            patch(
                "core.workflows.agent_translate_page.stages.translate.asyncio.to_thread",
                side_effect=fake_to_thread_failure,
            ),
        ):
            with self.assertRaises(TranslateStageError):
                asyncio.run(
                    run_translate_stage(
                        workflow_run_id="wf-2",
                        volume_id="vol",
                        filename="001.jpg",
                        source_language="Japanese",
                        target_language="English",
                        boxes=[{"box_index": 1}],
                        ocr_profiles=[{"id": "manga_ocr_default"}],
                        prior_context_summary="",
                        prior_characters=[],
                        prior_open_threads=[],
                        prior_glossary=[],
                        model_id="gpt-5-mini",
                        max_output_tokens=1024,
                        reasoning_effort="low",
                        temperature=None,
                        merge_max_output_tokens=768,
                        merge_reasoning_effort="low",
                    )
                )

        self.assertIn("failed", status_by_task["task-translate"])
        self.assertIn("canceled", status_by_task["task-merge"])
