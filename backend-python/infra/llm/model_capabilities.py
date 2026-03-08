# backend-python/infra/llm/model_capabilities.py
"""Model capability helpers for runtime tuning controls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

TemperatureSupport = Literal["always", "never", "reasoning_none_only"]

# OpenAI documents a conditional temperature exception for these GPT-5 variants.
_GPT5_CONDITIONAL_TEMPERATURE = ("gpt-5.1", "gpt-5.2", "gpt-5.4")
_REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


@dataclass(frozen=True)
class ModelCapability:
    """Effective model-control capabilities exposed by this app."""

    model_id: str
    applies_temperature: bool
    applies_reasoning_effort: bool
    temperature_support: TemperatureSupport
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return dict(asdict(self))


def resolve_model_capability(model_id: str | None) -> ModelCapability:
    """
    Return the effective runtime-control support for one model id.

    OpenAI's GPT-5.x family is increasingly reasoning-first. The current app does
    not expose a "reasoning: none" mode, so temperature is treated as inactive for
    GPT-5 models even where OpenAI documents a conditional exception.
    """

    normalized = str(model_id or "").strip()
    lowered = normalized.lower()
    if not normalized:
        return ModelCapability(
            model_id="",
            applies_temperature=True,
            applies_reasoning_effort=False,
            temperature_support="always",
        )

    if lowered.startswith(("gpt-5.1-pro", "gpt-5.2-pro")):
        return ModelCapability(
            model_id=normalized,
            applies_temperature=False,
            applies_reasoning_effort=True,
            temperature_support="never",
            notes=("Reasoning-first GPT-5 Pro models ignore temperature in this app.",),
        )

    if lowered.startswith(_GPT5_CONDITIONAL_TEMPERATURE):
        return ModelCapability(
            model_id=normalized,
            applies_temperature=False,
            applies_reasoning_effort=True,
            temperature_support="reasoning_none_only",
            notes=(
                "OpenAI allows temperature only when reasoning effort is none; "
                "this app does not expose that mode, so temperature stays inactive here.",
            ),
        )

    if lowered.startswith(_REASONING_MODEL_PREFIXES):
        return ModelCapability(
            model_id=normalized,
            applies_temperature=False,
            applies_reasoning_effort=True,
            temperature_support="never",
            notes=("This model uses reasoning effort instead of temperature here.",),
        )

    return ModelCapability(
        model_id=normalized,
        applies_temperature=True,
        applies_reasoning_effort=False,
        temperature_support="always",
        notes=("Temperature applies to this model; reasoning effort does not.",),
    )


def resolve_model_capability_map(model_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Return serialized capabilities for a list of selectable model ids."""

    result: dict[str, dict[str, Any]] = {}
    for model_id in model_ids:
        normalized = str(model_id).strip()
        if not normalized:
            continue
        result[normalized] = resolve_model_capability(normalized).to_payload()
    return result


def model_applies_temperature(model_id: str | None) -> bool:
    """Return whether temperature is an active tuning knob for this model."""

    return resolve_model_capability(model_id).applies_temperature


def model_applies_reasoning_effort(model_id: str | None) -> bool:
    """Return whether reasoning effort is an active tuning knob for this model."""

    return resolve_model_capability(model_id).applies_reasoning_effort
