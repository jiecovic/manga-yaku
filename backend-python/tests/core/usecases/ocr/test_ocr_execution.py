# backend-python/tests/core/usecases/ocr/test_ocr_execution.py
"""Unit tests for shared OCR async execution helper behavior.

What is tested:
- Attempt callback forwarding from runner internals to caller hooks.
- Timeout and exception propagation semantics.
- Prompt-version resolution fallback behavior.

How it is tested:
- Async helper execution with patched runner/timeout dependencies.
- Deterministic outcomes via synthetic `OcrTaskOutcome` payloads.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.usecases.ocr.execution import resolve_ocr_prompt_version, run_ocr_task_async
from core.usecases.ocr.task_runner import OcrTaskOutcome


@pytest.mark.asyncio
async def test_run_ocr_task_async_forwards_attempts_and_result() -> None:
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

    assert outcome.status == "ok"
    assert outcome.text == "abc"
    assert len(events) == 2
    assert events[0]["attempt"] == 1
    assert events[1]["attempt"] == 2


@pytest.mark.asyncio
async def test_run_ocr_task_async_emits_timeout_once() -> None:
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

    assert outcome.status == "error"
    assert "timed out" in str(outcome.error_message or "").lower()
    assert len(events) == 1
    assert events[0]["status"] == "timed_out"


def test_resolve_ocr_prompt_version_uses_profile_prompt_file() -> None:
    with patch(
        "core.usecases.ocr.execution.get_ocr_profile",
        return_value={"config": {"prompt_file": "ocr_quality.yml"}},
    ):
        prompt_version = resolve_ocr_prompt_version("openai_quality_ocr")
    assert prompt_version == "ocr_quality.yml"


def test_resolve_ocr_prompt_version_falls_back_default() -> None:
    with patch("core.usecases.ocr.execution.get_ocr_profile", side_effect=RuntimeError("x")):
        prompt_version = resolve_ocr_prompt_version("missing")
    assert prompt_version == "ocr_default.yml"
