# backend-python/core/usecases/agent/page_translate_helpers.py
"""Use-case helpers for agent page translate helpers operations."""

from __future__ import annotations

from typing import Any

from . import page_translate_schema as _schema
from .page_translate_call import (
    build_model_cfg as _build_model_cfg,
)
from .page_translate_call import (
    run_structured_call as _run_structured_call,
)
from .page_translate_prompts import (
    build_state_merge_prompt_payload as _build_state_merge_prompt_payload,
)
from .page_translate_prompts import (
    build_translate_stage_prompt_payload as _build_translate_stage_prompt_payload,
)
from .page_translate_prompts import format_yaml as _format_yaml

JsonParser = _schema.JsonParser
apply_no_text_consensus_guard = _schema.apply_no_text_consensus_guard
build_state_merge_text_format = _schema.build_state_merge_text_format
build_translate_stage_text_format = _schema.build_translate_stage_text_format
coerce_positive_int = _schema.coerce_positive_int
extract_json = _schema.extract_json
json_result_validator = _schema.json_result_validator
normalize_state_merge_result = _schema.normalize_state_merge_result
normalize_translate_stage_result = _schema.normalize_translate_stage_result
should_retry = _schema.should_retry


def format_yaml(value: Any) -> str:
    """Backward-compatible wrapper; use `page_translate_prompts.format_yaml` directly."""
    return _format_yaml(value)


def build_translate_stage_prompt_payload(
    *,
    source_language: str,
    target_language: str,
    boxes: list[dict[str, Any]],
    ocr_profiles: list[dict[str, Any]] | None,
    prior_context_summary: str | None,
    prior_characters: list[dict[str, Any]] | None,
    prior_open_threads: list[str] | None,
    prior_glossary: list[dict[str, Any]] | None,
) -> tuple[str, str]:
    """Backward-compatible wrapper; use `page_translate_prompts` directly."""
    return _build_translate_stage_prompt_payload(
        source_language=source_language,
        target_language=target_language,
        boxes=boxes,
        ocr_profiles=ocr_profiles,
        prior_context_summary=prior_context_summary,
        prior_characters=prior_characters,
        prior_open_threads=prior_open_threads,
        prior_glossary=prior_glossary,
    )


def build_state_merge_prompt_payload(
    *,
    source_language: str,
    target_language: str,
    prior_context_summary: str | None,
    prior_characters: list[dict[str, Any]] | None,
    prior_open_threads: list[str] | None,
    prior_glossary: list[dict[str, Any]] | None,
    stage1_result: dict[str, Any],
) -> tuple[str, str]:
    """Backward-compatible wrapper; use `page_translate_prompts` directly."""
    return _build_state_merge_prompt_payload(
        source_language=source_language,
        target_language=target_language,
        prior_context_summary=prior_context_summary,
        prior_characters=prior_characters,
        prior_open_threads=prior_open_threads,
        prior_glossary=prior_glossary,
        stage1_result=stage1_result,
    )


def build_model_cfg(
    *,
    model_id: str | None,
    max_output_tokens: int | None,
    reasoning_effort: str | None,
    temperature: float | None,
) -> dict[str, Any]:
    """Backward-compatible wrapper; use `page_translate_call` directly."""
    return _build_model_cfg(
        model_id=model_id,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
    )


def run_structured_call(
    *,
    client: Any,
    model_cfg: dict[str, Any],
    input_payload: list[dict[str, Any]],
    text_format: dict[str, Any],
    parser: JsonParser,
    component: str,
    repair_component: str,
    log_context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Backward-compatible wrapper; use `page_translate_call` directly."""
    return _run_structured_call(
        client=client,
        model_cfg=model_cfg,
        input_payload=input_payload,
        text_format=text_format,
        parser=parser,
        component=component,
        repair_component=repair_component,
        log_context=log_context,
    )
