# backend-python/core/usecases/agent/page_translate_prompts.py
"""Use-case helpers for agent page translate prompts operations."""

from __future__ import annotations

import json
from typing import Any

import yaml
from infra.prompts import load_prompt_bundle, render_prompt_bundle


def format_yaml(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict) and not value:
        return ""
    if isinstance(value, list) and not value:
        return ""
    try:
        return yaml.safe_dump(
            value,
            allow_unicode=True,
            sort_keys=False,
        ).strip()
    except Exception:
        return str(value).strip()


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
    bundle = load_prompt_bundle("agent_translate_page.yml")
    input_yaml = yaml.safe_dump(
        {"boxes": boxes},
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    profiles_yaml = yaml.safe_dump(
        {"profiles": ocr_profiles or []},
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    rendered = render_prompt_bundle(
        bundle,
        system_context={
            "SOURCE_LANG": source_language,
            "TARGET_LANG": target_language,
            "PRIOR_CONTEXT_SUMMARY": format_yaml(prior_context_summary),
            "PRIOR_CHARACTERS": format_yaml(prior_characters),
            "PRIOR_OPEN_THREADS": format_yaml(prior_open_threads),
            "PRIOR_GLOSSARY": format_yaml(prior_glossary),
        },
        user_context={
            "INPUT_YAML": input_yaml,
            "OCR_PROFILES_YAML": profiles_yaml,
        },
    )
    return rendered["system"], rendered["user_template"]


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
    bundle = load_prompt_bundle("agent_translate_page_merge.yml")
    page_result_json = json.dumps(stage1_result, ensure_ascii=False, indent=2)
    rendered = render_prompt_bundle(
        bundle,
        system_context={
            "SOURCE_LANG": source_language,
            "TARGET_LANG": target_language,
            "PRIOR_CONTEXT_SUMMARY": format_yaml(prior_context_summary),
            "PRIOR_CHARACTERS": format_yaml(prior_characters),
            "PRIOR_OPEN_THREADS": format_yaml(prior_open_threads),
            "PRIOR_GLOSSARY": format_yaml(prior_glossary),
        },
        user_context={
            "STAGE1_JSON": page_result_json,
        },
    )
    return rendered["system"], rendered["user_template"]
