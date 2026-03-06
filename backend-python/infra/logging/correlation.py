# backend-python/infra/logging/correlation.py
"""Shared helpers for normalizing and formatting log correlation metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "component": ("component",),
    "job_id": ("job_id", "jobId", "debug_id"),
    "workflow_run_id": ("workflow_run_id", "workflowRunId"),
    "task_run_id": ("task_run_id", "taskRunId"),
    "session_id": ("session_id", "sessionId"),
    "volume_id": ("volume_id", "volumeId"),
    "filename": ("filename", "file_name", "current_filename", "currentFilename"),
    "request_id": ("request_id", "requestId"),
    "model_id": ("model_id", "modelId"),
    "attempt": ("attempt",),
}

_ORDER = (
    "component",
    "job_id",
    "workflow_run_id",
    "task_run_id",
    "session_id",
    "volume_id",
    "filename",
    "request_id",
    "model_id",
    "attempt",
)


def _coerce_scalar(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    text = str(value).strip()
    return text or None


def _normalize_generic_map(values: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, raw_value in values.items():
        cleaned_key = str(key or "").strip()
        if not cleaned_key:
            continue
        coerced = _coerce_scalar(raw_value)
        if coerced is None:
            continue
        normalized[cleaned_key] = coerced
    return normalized


def normalize_correlation(
    value: Mapping[str, Any] | None = None,
    /,
    **overrides: Any,
) -> dict[str, Any]:
    source = dict(value or {})
    if overrides:
        source.update(overrides)

    normalized: dict[str, Any] = {}
    consumed_keys: set[str] = set()
    for canonical_key, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias not in source:
                continue
            consumed_keys.add(alias)
            coerced = _coerce_scalar(source.get(alias))
            if coerced is not None:
                normalized[canonical_key] = coerced
            break
    for key, raw_value in source.items():
        cleaned_key = str(key or "").strip()
        if not cleaned_key or cleaned_key in consumed_keys:
            continue
        coerced = _coerce_scalar(raw_value)
        if coerced is None:
            continue
        normalized[cleaned_key] = coerced
    return normalized


def append_correlation(
    message: str,
    correlation: Mapping[str, Any] | None = None,
    /,
    **extras: Any,
) -> str:
    normalized = normalize_correlation(correlation)
    generic = _normalize_generic_map(extras)
    if not normalized and not generic:
        return message

    parts: list[str] = []
    for key in _ORDER:
        if key in normalized:
            parts.append(f"{key}={normalized[key]}")
    for key in sorted(normalized):
        if key in _ORDER:
            continue
        parts.append(f"{key}={normalized[key]}")
    for key in sorted(generic):
        if key in normalized:
            continue
        parts.append(f"{key}={generic[key]}")
    suffix = " ".join(parts)
    return f"{message} | {suffix}" if suffix else message


def with_correlation(
    payload: Mapping[str, Any],
    correlation: Mapping[str, Any] | None = None,
    /,
    **overrides: Any,
) -> dict[str, Any]:
    enriched = dict(payload)
    normalized = normalize_correlation(correlation, **overrides)
    if normalized:
        enriched["correlation"] = normalized
    return enriched
