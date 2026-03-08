# backend-python/core/usecases/translation/tasks/runner.py
"""Queued task-runner logic for translation jobs."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.domain.pages import set_box_translation_by_id
from core.usecases.model_metadata import extract_model_metadata
from infra.llm.model_capabilities import model_applies_reasoning_effort

from ..profiles.registry import get_translation_profile


def _to_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return parsed


def _build_retry_override(base_cfg: dict[str, Any], *, attempt: int) -> dict[str, Any]:
    if attempt <= 1:
        return {}

    out: dict[str, Any] = {}
    current_limit = (
        _to_int(base_cfg.get("max_output_tokens"))
        or _to_int(base_cfg.get("max_completion_tokens"))
        or _to_int(base_cfg.get("max_tokens"))
        or 256
    )
    bump = min(max(current_limit * (2 ** (attempt - 1)), current_limit + 128), 2048)
    if "max_output_tokens" in base_cfg:
        out["max_output_tokens"] = bump
    elif "max_completion_tokens" in base_cfg:
        out["max_completion_tokens"] = bump
    else:
        out["max_tokens"] = bump

    model_id = str(base_cfg.get("model") or "")
    if model_applies_reasoning_effort(model_id):
        if attempt == 2:
            out["reasoning"] = {"effort": "medium"}
        elif attempt >= 3:
            out["reasoning"] = {"effort": "high"}
    return out


def _normalize_translation_result(result: Any) -> tuple[str, str]:
    if not isinstance(result, dict):
        return "invalid", ""
    status = str(result.get("status") or "").strip().lower()
    translation = str(result.get("translation") or "").strip()
    if status == "ok":
        return ("ok", translation) if translation else ("invalid", "")
    if status == "no_text":
        return "no_text", ""
    return "invalid", ""


@dataclass(frozen=True)
class TranslationTaskOutcome:
    box_id: int
    profile_id: str
    status: str
    translation: str
    attempt: int
    latency_ms: int
    model_id: str | None
    max_output_tokens: int | None
    reasoning_effort: str | None
    error_message: str | None = None

    def to_result_json(self) -> dict[str, Any]:
        return {
            "box_id": self.box_id,
            "profile_id": self.profile_id,
            "status": self.status,
            "translation": self.translation,
            "attempt": self.attempt,
            "latency_ms": self.latency_ms,
            "model_id": self.model_id,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
            "error_message": self.error_message,
        }


def run_translation_task_with_retries(
    *,
    profile_id: str,
    volume_id: str,
    filename: str,
    box_id: int,
    use_page_context: bool,
    max_attempts_llm: int = 3,
    on_attempt: Callable[[dict[str, Any]], None] | None = None,
) -> TranslationTaskOutcome:
    from ..runtime.engine import run_translate_box_with_context_structured

    profile = get_translation_profile(profile_id)
    provider = str(profile.get("provider") or "")
    is_llm = provider == "openai_chat"
    attempts = max(1, max_attempts_llm if is_llm else 1)

    base_cfg = dict(profile.get("config", {}) or {})

    last_error: str | None = None
    for attempt in range(1, attempts + 1):
        override = _build_retry_override(base_cfg, attempt=attempt)
        merged_cfg = dict(base_cfg)
        merged_cfg.update(override)
        model_id, max_tokens, reasoning_effort = extract_model_metadata(merged_cfg)
        started = time.monotonic()
        try:
            result = run_translate_box_with_context_structured(
                profile_id=profile_id,
                volume_id=volume_id,
                filename=filename,
                box_id=box_id,
                use_page_context=use_page_context,
                persist=False,
                config_override=override or None,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            last_error = str(exc).strip() or repr(exc)
            if on_attempt is not None:
                on_attempt(
                    {
                        "attempt": attempt,
                        "status": "error",
                        "latency_ms": latency_ms,
                        "model_id": model_id,
                        "max_output_tokens": max_tokens,
                        "reasoning_effort": reasoning_effort,
                        "error_message": last_error,
                    }
                )
            if attempt < attempts:
                continue
            return TranslationTaskOutcome(
                box_id=box_id,
                profile_id=profile_id,
                status="error",
                translation="",
                attempt=attempt,
                latency_ms=latency_ms,
                model_id=model_id,
                max_output_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                error_message=last_error,
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        status, translation = _normalize_translation_result(result)
        if on_attempt is not None:
            on_attempt(
                {
                    "attempt": attempt,
                    "status": status,
                    "latency_ms": latency_ms,
                    "model_id": model_id,
                    "max_output_tokens": max_tokens,
                    "reasoning_effort": reasoning_effort,
                    "translation": translation if status == "ok" else "",
                }
            )
        if status == "ok":
            set_box_translation_by_id(
                volume_id=volume_id,
                filename=filename,
                box_id=box_id,
                translation=translation,
            )
            return TranslationTaskOutcome(
                box_id=box_id,
                profile_id=profile_id,
                status=status,
                translation=translation,
                attempt=attempt,
                latency_ms=latency_ms,
                model_id=model_id,
                max_output_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        if status == "no_text":
            return TranslationTaskOutcome(
                box_id=box_id,
                profile_id=profile_id,
                status=status,
                translation="",
                attempt=attempt,
                latency_ms=latency_ms,
                model_id=model_id,
                max_output_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        if attempt >= attempts:
            return TranslationTaskOutcome(
                box_id=box_id,
                profile_id=profile_id,
                status=status,
                translation="",
                attempt=attempt,
                latency_ms=latency_ms,
                model_id=model_id,
                max_output_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                error_message=last_error,
            )

    return TranslationTaskOutcome(
        box_id=box_id,
        profile_id=profile_id,
        status="error",
        translation="",
        attempt=attempts,
        latency_ms=0,
        model_id=None,
        max_output_tokens=None,
        reasoning_effort=None,
        error_message=last_error or "unknown translation failure",
    )
