# backend-python/core/usecases/agent/settings.py
"""Use-case helpers for agent settings operations."""

from __future__ import annotations

from typing import Any

from config import (
    AGENT_MODEL,
    AGENT_MODELS,
    AGENT_TEMPERATURE,
    AGENT_TRANSLATE_MAX_OUTPUT_TOKENS,
    AGENT_TRANSLATE_REASONING_EFFORT,
)
from infra.db.agent_translate_settings_store import (
    get_agent_translate_settings,
    upsert_agent_translate_settings,
)

REASONING_CHOICES = ("low", "medium", "high")


def agent_translate_defaults() -> dict[str, Any]:
    return {
        "model_id": AGENT_MODEL,
        "max_output_tokens": AGENT_TRANSLATE_MAX_OUTPUT_TOKENS,
        "reasoning_effort": AGENT_TRANSLATE_REASONING_EFFORT,
        "temperature": AGENT_TEMPERATURE,
    }


def resolve_agent_translate_settings() -> dict[str, Any]:
    values = agent_translate_defaults()
    stored = get_agent_translate_settings()
    for key, value in stored.items():
        if value is not None:
            values[key] = value
    return values


def update_agent_translate_settings(values: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise ValueError("values must be an object")

    defaults = agent_translate_defaults()
    model_id = values.get("model_id") or defaults["model_id"]
    model_id = str(model_id).strip()
    if not model_id:
        raise ValueError("model_id is required")
    if AGENT_MODELS and model_id not in AGENT_MODELS:
        raise ValueError(f"model_id must be one of {AGENT_MODELS}")

    reasoning_effort = values.get("reasoning_effort", defaults["reasoning_effort"])
    if reasoning_effort is not None:
        reasoning_effort = str(reasoning_effort).strip().lower()
        if reasoning_effort not in REASONING_CHOICES:
            raise ValueError(f"reasoning_effort must be one of {REASONING_CHOICES}")

    max_output_tokens = values.get("max_output_tokens", defaults["max_output_tokens"])
    if max_output_tokens is not None:
        try:
            max_output_tokens = int(max_output_tokens)
        except (TypeError, ValueError):
            raise ValueError("max_output_tokens must be an integer") from None
        if max_output_tokens < 128:
            raise ValueError("max_output_tokens must be >= 128")

    temperature = values.get("temperature", defaults["temperature"])
    if temperature is not None:
        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            raise ValueError("temperature must be a number") from None
        if temperature < 0 or temperature > 2:
            raise ValueError("temperature must be between 0 and 2")

    payload = {
        "model_id": model_id,
        "reasoning_effort": reasoning_effort,
        "max_output_tokens": max_output_tokens,
        "temperature": temperature,
    }
    upsert_agent_translate_settings(payload)
    return resolve_agent_translate_settings()
