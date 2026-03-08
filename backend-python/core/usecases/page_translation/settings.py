# backend-python/core/usecases/page_translation/settings.py
"""Use-case helpers for page-translation settings operations."""

from __future__ import annotations

from typing import Any

from config import (
    AGENT_MODEL,
    AGENT_MODELS,
    AGENT_TEMPERATURE,
    PAGE_TRANSLATION_MAX_OUTPUT_TOKENS,
    PAGE_TRANSLATION_REASONING_EFFORT,
)
from core.usecases.settings.models import PageTranslationRuntimeSettings
from core.usecases.settings.runtime_validation import (
    apply_model_runtime_patch,
    build_model_runtime_settings,
)
from infra.db.page_translation_settings_store import (
    get_page_translation_settings,
    upsert_page_translation_settings,
)


def page_translation_defaults() -> PageTranslationRuntimeSettings:
    settings = build_model_runtime_settings(
        model_id=AGENT_MODEL,
        max_output_tokens=PAGE_TRANSLATION_MAX_OUTPUT_TOKENS,
        reasoning_effort=PAGE_TRANSLATION_REASONING_EFFORT,
        temperature=AGENT_TEMPERATURE,
        require_model_id=True,
        min_max_output_tokens=128,
    )
    return PageTranslationRuntimeSettings(**settings.to_payload())


def resolve_page_translation_settings() -> PageTranslationRuntimeSettings:
    current = page_translation_defaults()
    stored = get_page_translation_settings()
    resolved = apply_model_runtime_patch(
        current,
        {key: value for key, value in stored.items() if value is not None},
        require_model_id=True,
        min_max_output_tokens=128,
    )
    return PageTranslationRuntimeSettings(**resolved.to_payload())


def update_page_translation_settings(values: dict[str, Any]) -> PageTranslationRuntimeSettings:
    if not isinstance(values, dict):
        raise ValueError("values must be an object")

    current = resolve_page_translation_settings()
    next_settings = apply_model_runtime_patch(
        current,
        values,
        require_model_id=True,
        min_max_output_tokens=128,
    )
    if AGENT_MODELS and next_settings.model_id not in AGENT_MODELS:
        raise ValueError(f"model_id must be one of {AGENT_MODELS}")

    upsert_page_translation_settings(next_settings.to_payload())
    return resolve_page_translation_settings()
