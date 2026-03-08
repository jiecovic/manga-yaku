# backend-python/tests/infra/llm/test_model_capabilities.py
"""Unit tests for model capability resolution."""

from __future__ import annotations

from infra.llm.model_capabilities import resolve_model_capability


def test_gpt5_conditional_temperature_is_inactive_in_app() -> None:
    capability = resolve_model_capability("gpt-5.2")

    assert capability.applies_temperature is False
    assert capability.applies_reasoning_effort is True
    assert capability.temperature_support == "reasoning_none_only"
    assert capability.notes


def test_generic_gpt5_prefers_reasoning() -> None:
    capability = resolve_model_capability("gpt-5.4")

    assert capability.applies_temperature is False
    assert capability.applies_reasoning_effort is True
    assert capability.temperature_support == "reasoning_none_only"


def test_non_reasoning_models_keep_temperature() -> None:
    capability = resolve_model_capability("gpt-4.1-mini")

    assert capability.applies_temperature is True
    assert capability.applies_reasoning_effort is False
    assert capability.temperature_support == "always"
