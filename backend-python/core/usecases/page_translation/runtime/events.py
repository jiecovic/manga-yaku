# backend-python/core/usecases/page_translation/runtime/events.py
"""Stage event and debug artifact helpers for page-translation runtime."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from config import DEBUG_PROMPTS
from infra.logging.artifacts import (
    page_translation_debug_dir,
    timestamped_artifact_name,
    write_json_artifact,
)
from infra.logging.correlation import append_correlation, with_correlation

logger = logging.getLogger(__name__)

StageEventCallback = Callable[[str, str, dict[str, Any] | None], None]


def _coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _coerce_non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _extract_reasoning_effort(params: dict[str, Any] | None) -> str | None:
    if not isinstance(params, dict):
        return None
    reasoning = params.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if isinstance(effort, str):
            normalized = effort.strip()
            if normalized:
                return normalized
    return None


def build_stage_event_payload(
    *,
    stage: str,
    status: str,
    message: str,
    cfg: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    params = diagnostics.get("params") if isinstance(diagnostics, dict) else None
    max_output_tokens = None
    if isinstance(params, dict):
        max_output_tokens = _coerce_positive_int(params.get("max_output_tokens"))
    if max_output_tokens is None:
        max_output_tokens = _coerce_positive_int(cfg.get("max_output_tokens"))
    reasoning_effort = _extract_reasoning_effort(params)
    if reasoning_effort is None:
        reasoning_effort = _extract_reasoning_effort(cfg)

    token_usage = diagnostics.get("token_usage") if isinstance(diagnostics, dict) else None
    if not isinstance(token_usage, dict):
        token_usage = None

    payload: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "message": message,
        "model_id": (
            str(
                (diagnostics.get("model") if isinstance(diagnostics, dict) else None)
                or cfg.get("model")
                or ""
            ).strip()
            or None
        ),
        "attempt_count": max(
            1,
            _coerce_non_negative_int(
                diagnostics.get("attempt_count") if isinstance(diagnostics, dict) else 1
            ),
        ),
        "latency_ms": _coerce_non_negative_int(
            diagnostics.get("latency_ms") if isinstance(diagnostics, dict) else 0
        ),
        "finish_reason": (
            str(diagnostics.get("finish_reason") or "").strip()
            if isinstance(diagnostics, dict)
            else ""
        )
        or ("error" if error else "completed"),
        "params_snapshot": {
            "max_output_tokens": max_output_tokens,
            "reasoning_effort": reasoning_effort,
        },
        "token_usage": token_usage,
    }
    if error:
        payload["error"] = error
    warnings = diagnostics.get("warnings") if isinstance(diagnostics, dict) else None
    if isinstance(warnings, list):
        normalized_warnings = [str(item).strip() for item in warnings if str(item).strip()]
        if normalized_warnings:
            payload["warnings"] = normalized_warnings
    coverage = diagnostics.get("coverage") if isinstance(diagnostics, dict) else None
    if isinstance(coverage, dict):
        payload["coverage_summary"] = {
            "expected_box_count": _coerce_non_negative_int(coverage.get("expected_box_count")),
            "covered_box_count": _coerce_non_negative_int(coverage.get("covered_box_count")),
            "missing_box_ids": [
                value
                for value in (
                    _coerce_positive_int(item) for item in (coverage.get("missing_box_ids") or [])
                )
                if value is not None
            ],
            "unexpected_box_ids": [
                value
                for value in (
                    _coerce_positive_int(item)
                    for item in (coverage.get("unexpected_box_ids") or [])
                )
                if value is not None
            ],
            "duplicate_box_ids": [
                value
                for value in (
                    _coerce_positive_int(item) for item in (coverage.get("duplicate_box_ids") or [])
                )
                if value is not None
            ],
            "is_complete": bool(coverage.get("is_complete")),
        }
    return payload


def emit_stage_event(
    callback: StageEventCallback | None,
    *,
    stage: str,
    status: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if callback is None:
        return
    try:
        callback(stage, status, payload)
    except Exception as exc:
        logger.warning(
            append_correlation(
                f"Stage event callback failed ({stage}/{status}): {exc}",
                payload.get("correlation") if isinstance(payload, dict) else None,
                component_name=stage,
                status_name=status,
            )
        )


def write_debug_snapshot(
    *,
    debug_id: str | None,
    payload: dict[str, Any],
) -> None:
    if not DEBUG_PROMPTS:
        return
    try:
        write_json_artifact(
            directory=page_translation_debug_dir(),
            filename=timestamped_artifact_name(prefix=debug_id or "page_translation"),
            payload=with_correlation(payload, payload.get("correlation")),
        )
    except Exception as exc:
        logger.warning(
            append_correlation(
                f"Failed to write agent debug snapshot: {exc}",
                payload.get("correlation") if isinstance(payload, dict) else None,
            )
        )
