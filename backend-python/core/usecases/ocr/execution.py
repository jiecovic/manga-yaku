# backend-python/core/usecases/ocr/execution.py
"""Execution helpers for ocr operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from infra.logging.correlation import append_correlation

from .profiles import get_ocr_profile
from .task_runner import OcrTaskOutcome, run_ocr_task_with_retries

logger = logging.getLogger(__name__)


def _to_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return parsed


def _extract_profile_runtime_metadata(profile_id: str) -> tuple[str | None, int | None]:
    try:
        profile = get_ocr_profile(profile_id)
    except Exception:
        return None, None
    cfg = dict(profile.get("config", {}) or {})
    model_id = cfg.get("model")
    max_tokens = (
        cfg.get("max_output_tokens") or cfg.get("max_completion_tokens") or cfg.get("max_tokens")
    )
    return (str(model_id) if model_id else None, _to_int(max_tokens))


def resolve_ocr_prompt_version(profile_id: str) -> str:
    try:
        profile = get_ocr_profile(profile_id)
    except Exception:
        return "ocr_default.yml"
    cfg = dict(profile.get("config", {}) or {})
    prompt_file = str(cfg.get("prompt_file") or "").strip()
    return prompt_file or "ocr_default.yml"


async def run_ocr_task_async(
    *,
    profile_id: str,
    volume_id: str,
    filename: str,
    box_id: int,
    x: float,
    y: float,
    width: float,
    height: float,
    max_attempts_llm: int = 3,
    timeout_seconds: int | None = None,
    on_attempt: Callable[[dict[str, Any]], None] | None = None,
) -> OcrTaskOutcome:
    stopped = False
    last_attempt = 0

    def emit_attempt(event: dict[str, Any], *, force: bool = False) -> None:
        nonlocal last_attempt
        parsed_attempt = _to_int(event.get("attempt")) or 1
        last_attempt = max(last_attempt, max(1, parsed_attempt))
        if stopped and not force:
            return
        if on_attempt is None:
            return
        try:
            on_attempt(event)
        except Exception:
            logger.exception(
                append_correlation(
                    "OCR attempt callback failed",
                    {
                        "component": "ocr.execution.attempt_callback",
                        "volume_id": volume_id,
                        "filename": filename,
                    },
                    profile_id=profile_id,
                    box_id=box_id,
                )
            )

    task = asyncio.to_thread(
        run_ocr_task_with_retries,
        profile_id=profile_id,
        volume_id=volume_id,
        filename=filename,
        box_id=box_id,
        x=x,
        y=y,
        width=width,
        height=height,
        max_attempts_llm=max_attempts_llm,
        on_attempt=lambda event: emit_attempt(event),
    )

    loop = asyncio.get_running_loop()
    started = loop.time()
    resolved_timeout = int(timeout_seconds or 0)
    if resolved_timeout <= 0:
        try:
            outcome = await task
            stopped = True
            return outcome
        except Exception as exc:
            stopped = True
            latency_ms = int((loop.time() - started) * 1000)
            error_text = str(exc).strip() or repr(exc)
            error_attempt = max(1, last_attempt + 1)
            model_id, max_output_tokens = _extract_profile_runtime_metadata(profile_id)
            emit_attempt(
                {
                    "attempt": error_attempt,
                    "status": "error",
                    "latency_ms": latency_ms,
                    "model_id": model_id,
                    "max_output_tokens": max_output_tokens,
                    "reasoning_effort": None,
                    "error_message": error_text,
                },
                force=True,
            )
            return OcrTaskOutcome(
                box_id=box_id,
                profile_id=profile_id,
                status="error",
                text="",
                attempt=error_attempt,
                latency_ms=latency_ms,
                model_id=model_id,
                max_output_tokens=max_output_tokens,
                reasoning_effort=None,
                error_message=error_text,
            )

    try:
        outcome = await asyncio.wait_for(task, timeout=float(resolved_timeout))
        stopped = True
        return outcome
    except asyncio.TimeoutError:
        stopped = True
        latency_ms = int((loop.time() - started) * 1000)
        timeout_attempt = max(1, last_attempt + 1)
        timeout_message = f"OCR task timed out after {resolved_timeout}s"
        model_id, max_output_tokens = _extract_profile_runtime_metadata(profile_id)
        emit_attempt(
            {
                "attempt": timeout_attempt,
                "status": "timed_out",
                "latency_ms": latency_ms,
                "model_id": model_id,
                "max_output_tokens": max_output_tokens,
                "reasoning_effort": None,
                "error_message": timeout_message,
            },
            force=True,
        )
        return OcrTaskOutcome(
            box_id=box_id,
            profile_id=profile_id,
            status="error",
            text="",
            attempt=timeout_attempt,
            latency_ms=latency_ms,
            model_id=model_id,
            max_output_tokens=max_output_tokens,
            reasoning_effort=None,
            error_message=timeout_message,
        )
    except Exception as exc:
        stopped = True
        latency_ms = int((loop.time() - started) * 1000)
        error_text = str(exc).strip() or repr(exc)
        error_attempt = max(1, last_attempt + 1)
        model_id, max_output_tokens = _extract_profile_runtime_metadata(profile_id)
        emit_attempt(
            {
                "attempt": error_attempt,
                "status": "error",
                "latency_ms": latency_ms,
                "model_id": model_id,
                "max_output_tokens": max_output_tokens,
                "reasoning_effort": None,
                "error_message": error_text,
            },
            force=True,
        )
        return OcrTaskOutcome(
            box_id=box_id,
            profile_id=profile_id,
            status="error",
            text="",
            attempt=error_attempt,
            latency_ms=latency_ms,
            model_id=model_id,
            max_output_tokens=max_output_tokens,
            reasoning_effort=None,
            error_message=error_text,
        )
