# backend-python/core/usecases/agent/page_translate_prompts.py
"""Use-case helpers for agent page translate prompts operations."""

from __future__ import annotations

import json
from typing import Any

import yaml
from infra.prompts import load_prompt_bundle, render_prompt_bundle

_MAX_MERGE_SUMMARY_CHARS = 2_400
_MAX_MERGE_CHARACTERS_CHARS = 3_000
_MAX_MERGE_THREADS_CHARS = 1_800
_MAX_MERGE_GLOSSARY_CHARS = 2_400
_MAX_MERGE_STAGE1_BOXES = 120
_MAX_MERGE_STAGE1_NO_TEXT = 240
_MAX_MERGE_STAGE1_EVENTS = 20
_MAX_MERGE_STAGE1_CHARS = 40


def _truncate_text(value: str, *, max_chars: int) -> str:
    text = value.strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3].rstrip()}..."


def _compact_stage1_for_merge(stage1_result: dict[str, Any]) -> dict[str, Any]:
    boxes_out: list[dict[str, Any]] = []
    raw_boxes = stage1_result.get("boxes")
    if isinstance(raw_boxes, list):
        for raw_box in raw_boxes[:_MAX_MERGE_STAGE1_BOXES]:
            if not isinstance(raw_box, dict):
                continue
            raw_ids = raw_box.get("box_ids")
            box_ids: list[int] = []
            if isinstance(raw_ids, list):
                for value in raw_ids:
                    try:
                        parsed = int(value)
                    except (TypeError, ValueError):
                        continue
                    if parsed > 0:
                        box_ids.append(parsed)
            boxes_out.append(
                {
                    "box_ids": box_ids,
                    "ocr_profile_id": _truncate_text(
                        str(raw_box.get("ocr_profile_id") or ""),
                        max_chars=64,
                    ),
                    "ocr_text": _truncate_text(
                        str(raw_box.get("ocr_text") or ""),
                        max_chars=220,
                    ),
                    "speaker_id": _truncate_text(
                        str(raw_box.get("speaker_id") or "unknown"),
                        max_chars=48,
                    ),
                    "addressee_id": _truncate_text(
                        str(raw_box.get("addressee_id") or ""),
                        max_chars=48,
                    ),
                    "speaker_gender": _truncate_text(
                        str(raw_box.get("speaker_gender") or "unknown"),
                        max_chars=16,
                    ),
                    "speaker_visual_cues": _truncate_text(
                        str(raw_box.get("speaker_visual_cues") or ""),
                        max_chars=180,
                    ),
                    "translation": _truncate_text(
                        str(raw_box.get("translation") or ""),
                        max_chars=220,
                    ),
                }
            )

    no_text_out: list[int] = []
    raw_no_text = stage1_result.get("no_text_boxes")
    if isinstance(raw_no_text, list):
        seen: set[int] = set()
        for value in raw_no_text:
            if len(no_text_out) >= _MAX_MERGE_STAGE1_NO_TEXT:
                break
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed <= 0 or parsed in seen:
                continue
            seen.add(parsed)
            no_text_out.append(parsed)

    events_out: list[str] = []
    raw_events = stage1_result.get("page_events")
    if isinstance(raw_events, list):
        for value in raw_events[:_MAX_MERGE_STAGE1_EVENTS]:
            text = _truncate_text(str(value or ""), max_chars=220)
            if text:
                events_out.append(text)

    detected_out: list[dict[str, str]] = []
    raw_detected = stage1_result.get("page_characters_detected")
    if isinstance(raw_detected, list):
        for value in raw_detected[:_MAX_MERGE_STAGE1_CHARS]:
            if not isinstance(value, dict):
                continue
            detected_out.append(
                {
                    "speaker_id": _truncate_text(
                        str(value.get("speaker_id") or "unknown"),
                        max_chars=48,
                    ),
                    "speaker_gender": _truncate_text(
                        str(value.get("speaker_gender") or "unknown"),
                        max_chars=16,
                    ),
                    "speaker_visual_cues": _truncate_text(
                        str(value.get("speaker_visual_cues") or ""),
                        max_chars=180,
                    ),
                }
            )

    return {
        "boxes": boxes_out,
        "no_text_boxes": no_text_out,
        "image_summary": _truncate_text(
            str(stage1_result.get("image_summary") or ""),
            max_chars=900,
        ),
        "page_events": events_out,
        "page_characters_detected": detected_out,
    }


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
    compact_stage1_result = _compact_stage1_for_merge(stage1_result)
    page_result_json = json.dumps(compact_stage1_result, ensure_ascii=False, indent=2)
    rendered = render_prompt_bundle(
        bundle,
        system_context={
            "SOURCE_LANG": source_language,
            "TARGET_LANG": target_language,
            "PRIOR_CONTEXT_SUMMARY": _truncate_text(
                format_yaml(prior_context_summary),
                max_chars=_MAX_MERGE_SUMMARY_CHARS,
            ),
            "PRIOR_CHARACTERS": _truncate_text(
                format_yaml(prior_characters),
                max_chars=_MAX_MERGE_CHARACTERS_CHARS,
            ),
            "PRIOR_OPEN_THREADS": _truncate_text(
                format_yaml(prior_open_threads),
                max_chars=_MAX_MERGE_THREADS_CHARS,
            ),
            "PRIOR_GLOSSARY": _truncate_text(
                format_yaml(prior_glossary),
                max_chars=_MAX_MERGE_GLOSSARY_CHARS,
            ),
        },
        user_context={
            "STAGE1_JSON": page_result_json,
        },
    )
    return rendered["system"], rendered["user_template"]
