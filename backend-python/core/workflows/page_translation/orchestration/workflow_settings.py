# backend-python/core/workflows/page_translation/orchestration/workflow_settings.py
"""Workflow setting resolution for page-translation orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from core.usecases.page_translation.settings import resolve_page_translation_settings
from core.usecases.settings.service import get_setting_value


def _get_bool_setting(key: str, *, default: bool) -> bool:
    raw = get_setting_value(key)
    return bool(raw) if isinstance(raw, bool) else default


def _get_int_setting(
    key: str,
    *,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = get_setting_value(key)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    return value


def _get_str_choice_setting(
    key: str,
    *,
    default: str,
    choices: tuple[str, ...],
) -> str:
    raw = get_setting_value(key)
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in choices:
            return normalized
    return default


@dataclass(frozen=True)
class PageTranslationWorkflowSettings:
    include_prior_summary: bool
    include_prior_characters: bool
    include_prior_open_threads: bool
    include_prior_glossary: bool
    merge_max_output_tokens: int
    merge_reasoning_effort: str
    model_id: str | None
    max_output_tokens: int | float | None
    reasoning_effort: str | None
    temperature: float | int | None


def resolve_page_translation_workflow_settings(
    *,
    request_model_id: str | None,
) -> PageTranslationWorkflowSettings:
    page_translation_settings = resolve_page_translation_settings()
    return PageTranslationWorkflowSettings(
        include_prior_summary=_get_bool_setting(
            "page_translation.include_prior_context_summary",
            default=True,
        ),
        include_prior_characters=_get_bool_setting(
            "page_translation.include_prior_characters",
            default=True,
        ),
        include_prior_open_threads=_get_bool_setting(
            "page_translation.include_prior_open_threads",
            default=True,
        ),
        include_prior_glossary=_get_bool_setting(
            "page_translation.include_prior_glossary",
            default=True,
        ),
        merge_max_output_tokens=_get_int_setting(
            "page_translation.merge.max_output_tokens",
            default=768,
            min_value=128,
            max_value=4096,
        ),
        merge_reasoning_effort=_get_str_choice_setting(
            "page_translation.merge.reasoning_effort",
            default="low",
            choices=("low", "medium", "high"),
        ),
        model_id=request_model_id or page_translation_settings.model_id,
        max_output_tokens=page_translation_settings.max_output_tokens,
        reasoning_effort=page_translation_settings.reasoning_effort,
        temperature=page_translation_settings.temperature,
    )
