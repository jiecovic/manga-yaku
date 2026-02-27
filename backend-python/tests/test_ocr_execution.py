"""Unit tests for shared OCR async execution helper behavior.

These tests validate attempt callback forwarding and timeout handling used by
both persisted OCR DB workers and workflow OCR fanout stages.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from core.usecases.ocr.execution import resolve_ocr_prompt_version, run_ocr_task_async
from core.usecases.ocr.task_runner import OcrTaskOutcome


class OcrExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_ocr_task_async_forwards_attempts_and_result(self) -> None:
        events: list[dict] = []

        def fake_run(*args, **kwargs):
            on_attempt = kwargs.get("on_attempt")
            if callable(on_attempt):
                on_attempt({"attempt": 1, "status": "invalid", "latency_ms": 12})
                on_attempt({"attempt": 2, "status": "ok", "latency_ms": 25, "text": "abc"})
            return OcrTaskOutcome(
                box_id=7,
                profile_id="p1",
                status="ok",
                text="abc",
                attempt=2,
                latency_ms=25,
                model_id="m",
                max_output_tokens=256,
                reasoning_effort=None,
            )

        async def fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with (
            patch("core.usecases.ocr.execution.run_ocr_task_with_retries", side_effect=fake_run),
            patch("core.usecases.ocr.execution.asyncio.to_thread", side_effect=fake_to_thread),
        ):
            outcome = await run_ocr_task_async(
                profile_id="p1",
                volume_id="vol",
                filename="001.jpg",
                box_id=7,
                x=1.0,
                y=2.0,
                width=3.0,
                height=4.0,
                on_attempt=events.append,
            )

        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.text, "abc")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["attempt"], 1)
        self.assertEqual(events[1]["attempt"], 2)

    async def test_run_ocr_task_async_emits_timeout_once(self) -> None:
        events: list[dict] = []

        async def fake_wait_for(awaitable, timeout):
            close = getattr(awaitable, "close", None)
            if callable(close):
                close()
            raise asyncio.TimeoutError

        with (
            patch(
                "core.usecases.ocr.execution.asyncio.wait_for",
                new=AsyncMock(side_effect=fake_wait_for),
            ),
            patch(
                "core.usecases.ocr.execution.get_ocr_profile",
                return_value={"config": {"model": "m", "max_output_tokens": 256}},
            ),
        ):
            outcome = await run_ocr_task_async(
                profile_id="p1",
                volume_id="vol",
                filename="001.jpg",
                box_id=9,
                x=1.0,
                y=2.0,
                width=3.0,
                height=4.0,
                timeout_seconds=1,
                on_attempt=events.append,
            )

        self.assertEqual(outcome.status, "error")
        self.assertIn("timed out", str(outcome.error_message or "").lower())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "timed_out")

    def test_resolve_ocr_prompt_version_uses_profile_prompt_file(self) -> None:
        with patch(
            "core.usecases.ocr.execution.get_ocr_profile",
            return_value={"config": {"prompt_file": "ocr_quality.yml"}},
        ):
            prompt_version = resolve_ocr_prompt_version("openai_quality_ocr")
        self.assertEqual(prompt_version, "ocr_quality.yml")

    def test_resolve_ocr_prompt_version_falls_back_default(self) -> None:
        with patch("core.usecases.ocr.execution.get_ocr_profile", side_effect=RuntimeError("x")):
            prompt_version = resolve_ocr_prompt_version("missing")
        self.assertEqual(prompt_version, "ocr_default.yml")
