"""Queued task-runner logic for ocr jobs."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .profiles import get_ocr_profile


def _is_blank_ocr_text(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return True
    return cleaned in {'""', "''"}


def _is_repetitive_ocr(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 60:
        return False
    counts: dict[str, int] = {}
    for ch in cleaned:
        counts[ch] = counts.get(ch, 0) + 1
    most_common = max(counts.values()) if counts else 0
    return most_common / max(len(cleaned), 1) >= 0.7


def _sanitize_ocr_text(value: Any, *, llm: bool) -> tuple[str, str]:
    if not isinstance(value, str):
        return "", "invalid"
    cleaned = value.strip()
    if cleaned.upper() == "NO_TEXT":
        return "", "no_text"
    if _is_blank_ocr_text(cleaned):
        return "", "invalid" if llm else "no_text"
    if _is_repetitive_ocr(cleaned):
        return "", "invalid"
    return cleaned, "ok"


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
    bump = min(max(current_limit * (2 ** (attempt - 1)), current_limit + 128), 1536)
    if "max_output_tokens" in base_cfg:
        out["max_output_tokens"] = bump
    elif "max_completion_tokens" in base_cfg:
        out["max_completion_tokens"] = bump
    else:
        out["max_tokens"] = bump

    model_id = str(base_cfg.get("model") or "")
    if model_id.startswith("gpt-5"):
        if attempt == 2:
            out["reasoning"] = {"effort": "medium"}
        elif attempt >= 3:
            out["reasoning"] = {"effort": "high"}
    return out


def _extract_model_metadata(config: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    model_id = config.get("model")
    max_tokens = config.get("max_output_tokens") or config.get("max_completion_tokens") or config.get("max_tokens")
    reasoning_effort = None
    reasoning = config.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if effort:
            reasoning_effort = str(effort)
    return (
        str(model_id) if model_id else None,
        _to_int(max_tokens),
        reasoning_effort,
    )


@dataclass(frozen=True)
class OcrTaskOutcome:
    box_id: int
    profile_id: str
    status: str
    text: str
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
            "text": self.text,
            "attempt": self.attempt,
            "latency_ms": self.latency_ms,
            "model_id": self.model_id,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
            "error_message": self.error_message,
        }


def run_ocr_task_with_retries(
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
    on_attempt: Callable[[dict[str, Any]], None] | None = None,
) -> OcrTaskOutcome:
    from .engine import run_ocr_box

    profile = get_ocr_profile(profile_id)
    provider = str(profile.get("provider") or "")
    is_llm = provider in {"llm_ocr", "llm_ocr_chat"}
    attempts = max(1, max_attempts_llm if is_llm else 1)

    base_cfg = dict(profile.get("config", {}) or {})

    last_error: str | None = None
    for attempt in range(1, attempts + 1):
        override = _build_retry_override(base_cfg, attempt=attempt)
        merged_cfg = dict(base_cfg)
        merged_cfg.update(override)
        model_id, max_tokens, reasoning_effort = _extract_model_metadata(merged_cfg)
        started = time.monotonic()
        try:
            text = run_ocr_box(
                profile_id,
                volume_id,
                filename,
                box_id,
                x,
                y,
                width,
                height,
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
            return OcrTaskOutcome(
                box_id=box_id,
                profile_id=profile_id,
                status="error",
                text="",
                attempt=attempt,
                latency_ms=latency_ms,
                model_id=model_id,
                max_output_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                error_message=last_error,
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        cleaned, status = _sanitize_ocr_text(text, llm=is_llm)
        if on_attempt is not None:
            on_attempt(
                {
                    "attempt": attempt,
                    "status": status,
                    "latency_ms": latency_ms,
                    "model_id": model_id,
                    "max_output_tokens": max_tokens,
                    "reasoning_effort": reasoning_effort,
                    "text": cleaned if status == "ok" else "",
                }
            )
        if status in {"ok", "no_text"}:
            return OcrTaskOutcome(
                box_id=box_id,
                profile_id=profile_id,
                status=status,
                text=cleaned,
                attempt=attempt,
                latency_ms=latency_ms,
                model_id=model_id,
                max_output_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        if attempt >= attempts:
            return OcrTaskOutcome(
                box_id=box_id,
                profile_id=profile_id,
                status=status,
                text="",
                attempt=attempt,
                latency_ms=latency_ms,
                model_id=model_id,
                max_output_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                error_message=last_error,
            )

    return OcrTaskOutcome(
        box_id=box_id,
        profile_id=profile_id,
        status="error",
        text="",
        attempt=attempts,
        latency_ms=0,
        model_id=None,
        max_output_tokens=None,
        reasoning_effort=None,
        error_message=last_error or "unknown OCR failure",
    )
