# backend-python/tests/core/usecases/translation/test_translation_execution.py
"""Unit tests for shared translation async execution helper behavior.

What is tested:
- Attempt callback forwarding from translation runner internals.
- Timeout and exception handling around async execution wrapper.
- Prompt-version resolution fallback behavior.

How it is tested:
- Async helper execution with patched runner/timeout dependencies.
- Deterministic synthetic `TranslationTaskOutcome` payloads.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from core.usecases.translation.execution import (
    resolve_translation_prompt_version,
    run_translation_task_async,
)
from core.usecases.translation.task_runner import TranslationTaskOutcome


@pytest.mark.asyncio
async def test_run_translation_task_async_forwards_attempts_and_result() -> None:
    events: list[dict] = []

    def fake_run(*args, **kwargs):
        on_attempt = kwargs.get("on_attempt")
        if callable(on_attempt):
            on_attempt({"attempt": 1, "status": "invalid", "latency_ms": 12})
            on_attempt({"attempt": 2, "status": "ok", "latency_ms": 25, "translation": "hello"})
        return TranslationTaskOutcome(
            box_id=7,
            profile_id="p1",
            status="ok",
            translation="hello",
            attempt=2,
            latency_ms=25,
            model_id="m",
            max_output_tokens=256,
            reasoning_effort=None,
        )

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch(
            "core.usecases.translation.execution.run_translation_task_with_retries",
            side_effect=fake_run,
        ),
        patch("core.usecases.translation.execution.asyncio.to_thread", side_effect=fake_to_thread),
    ):
        outcome = await run_translation_task_async(
            profile_id="p1",
            volume_id="vol",
            filename="001.jpg",
            box_id=7,
            use_page_context=True,
            on_attempt=events.append,
        )

    assert outcome.status == "ok"
    assert outcome.translation == "hello"
    assert len(events) == 2
    assert events[0]["attempt"] == 1
    assert events[1]["attempt"] == 2


@pytest.mark.asyncio
async def test_run_translation_task_async_emits_timeout_once() -> None:
    events: list[dict] = []

    async def fake_wait_for(awaitable, timeout):
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
        raise asyncio.TimeoutError

    with (
        patch(
            "core.usecases.translation.execution.asyncio.wait_for",
            new=AsyncMock(side_effect=fake_wait_for),
        ),
        patch(
            "core.usecases.translation.execution.get_translation_profile",
            return_value={"config": {"model": "m", "max_output_tokens": 256}},
        ),
    ):
        outcome = await run_translation_task_async(
            profile_id="p1",
            volume_id="vol",
            filename="001.jpg",
            box_id=9,
            use_page_context=False,
            timeout_seconds=1,
            on_attempt=events.append,
        )

    assert outcome.status == "error"
    assert "timed out" in str(outcome.error_message or "").lower()
    assert len(events) == 1
    assert events[0]["status"] == "timed_out"


def test_resolve_translation_prompt_version_uses_profile_prompt_file() -> None:
    with patch(
        "core.usecases.translation.execution.get_translation_profile",
        return_value={"config": {"prompt_file": "translation/single_box/quality.yml"}},
    ):
        prompt_version = resolve_translation_prompt_version("openai_quality_translate")
    assert prompt_version == "translation/single_box/quality.yml"


def test_resolve_translation_prompt_version_falls_back_default() -> None:
    with patch(
        "core.usecases.translation.execution.get_translation_profile",
        side_effect=RuntimeError("x"),
    ):
        prompt_version = resolve_translation_prompt_version("missing")
    assert prompt_version == "translation/single_box/fast.yml"
