# backend-python/core/usecases/model_metadata.py
"""Shared helpers for extracting model/runtime metadata from config payloads."""

from __future__ import annotations

from typing import Any


def _to_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return parsed


def extract_model_metadata(config: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    """Normalize model-id, max-token, and reasoning metadata for task records."""
    model_id = config.get("model")
    max_tokens = (
        config.get("max_output_tokens")
        or config.get("max_completion_tokens")
        or config.get("max_tokens")
    )
    reasoning_effort = None
    reasoning = config.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if effort:
            reasoning_effort = str(effort)
    elif config.get("reasoning_effort"):
        reasoning_effort = str(config["reasoning_effort"])
    return (
        str(model_id) if model_id else None,
        _to_positive_int(max_tokens),
        reasoning_effort,
    )
