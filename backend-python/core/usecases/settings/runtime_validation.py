# backend-python/core/usecases/settings/runtime_validation.py
"""Shared validation helpers for typed runtime/model settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ModelRuntimeSettings

REASONING_CHOICES = ("low", "medium", "high")


def build_model_runtime_settings(
    *,
    model_id: Any,
    max_output_tokens: Any,
    reasoning_effort: Any,
    temperature: Any,
    require_model_id: bool,
    min_max_output_tokens: int,
) -> ModelRuntimeSettings:
    """Validate and normalize a runtime-settings payload into one typed object."""
    normalized_model_id = _normalize_model_id(model_id)
    if require_model_id and not normalized_model_id:
        raise ValueError("model_id is required")

    return ModelRuntimeSettings(
        model_id=normalized_model_id,
        max_output_tokens=_normalize_max_output_tokens(
            max_output_tokens,
            min_value=min_max_output_tokens,
        ),
        reasoning_effort=_normalize_reasoning_effort(reasoning_effort),
        temperature=_normalize_temperature(temperature),
    )


def default_model_runtime_settings(profile_config: Mapping[str, Any]) -> ModelRuntimeSettings:
    """Build defaults from a static provider profile config."""
    return build_model_runtime_settings(
        model_id=profile_config.get("model"),
        max_output_tokens=profile_config.get("max_tokens")
        or profile_config.get("max_completion_tokens"),
        reasoning_effort=None,
        temperature=profile_config.get("temperature"),
        require_model_id=False,
        min_max_output_tokens=1,
    )


def apply_model_runtime_patch(
    current: ModelRuntimeSettings,
    values: Mapping[str, Any],
    *,
    require_model_id: bool,
    min_max_output_tokens: int,
) -> ModelRuntimeSettings:
    """Apply a partial patch onto a typed settings object and revalidate once."""
    next_model_id = current.model_id
    next_max_output_tokens = current.max_output_tokens
    next_reasoning_effort = current.reasoning_effort
    next_temperature = current.temperature

    if "model_id" in values:
        next_model_id = _normalize_model_id(values.get("model_id"))
    if "max_output_tokens" in values:
        next_max_output_tokens = _normalize_max_output_tokens(
            values.get("max_output_tokens"),
            min_value=min_max_output_tokens,
        )
    if "reasoning_effort" in values:
        next_reasoning_effort = _normalize_reasoning_effort(values.get("reasoning_effort"))
    if "temperature" in values:
        next_temperature = _normalize_temperature(values.get("temperature"))

    return build_model_runtime_settings(
        model_id=next_model_id,
        max_output_tokens=next_max_output_tokens,
        reasoning_effort=next_reasoning_effort,
        temperature=next_temperature,
        require_model_id=require_model_id,
        min_max_output_tokens=min_max_output_tokens,
    )


def _normalize_model_id(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_max_output_tokens(value: Any, *, min_value: int) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("max_output_tokens must be an integer") from None
    if parsed < min_value:
        raise ValueError(f"max_output_tokens must be >= {min_value}")
    return parsed


def _normalize_reasoning_effort(value: Any) -> str | None:
    if value is None or value == "":
        return None
    normalized = str(value).strip().lower()
    if normalized not in REASONING_CHOICES:
        raise ValueError(f"reasoning_effort must be one of {REASONING_CHOICES}")
    return normalized


def _normalize_temperature(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError("temperature must be a number") from None
    if parsed < 0 or parsed > 2:
        raise ValueError("temperature must be between 0 and 2")
    return parsed
