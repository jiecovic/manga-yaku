from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import yaml

from config import (
    AGENT_MAX_OUTPUT_TOKENS,
    AGENT_MODEL,
    AGENT_REASONING_EFFORT,
    AGENT_TEMPERATURE,
    AGENT_TRANSLATE_MAX_OUTPUT_TOKENS,
    AGENT_TRANSLATE_REASONING_EFFORT,
)
from infra.llm import (
    build_response_params,
    extract_response_text,
    openai_responses_create,
)
from infra.prompts import load_prompt_bundle, render_prompt_bundle

logger = logging.getLogger(__name__)

_SPEAKER_GENDER_CHOICES = {"male", "female", "unknown"}

JsonParser = Callable[[dict[str, Any]], dict[str, Any]]


def _response_status_parts(response_dump: Any) -> tuple[str, str | None]:
    if not isinstance(response_dump, dict):
        return "", None
    status = str(response_dump.get("status") or "").strip()
    incomplete_reason: str | None = None
    incomplete = response_dump.get("incomplete_details")
    if isinstance(incomplete, dict):
        raw_reason = incomplete.get("reason")
        if isinstance(raw_reason, str) and raw_reason.strip():
            incomplete_reason = raw_reason.strip()
    return status, incomplete_reason


def _extract_token_usage(response_dump: Any) -> dict[str, int] | None:
    if not isinstance(response_dump, dict):
        return None
    usage = response_dump.get("usage")
    if not isinstance(usage, dict):
        return None
    token_usage: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and value >= 0:
            token_usage[key] = value
    return token_usage or None


def build_translate_stage_text_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "translate_page_stage1",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "boxes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "box_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                            "ocr_profile_id": {"type": "string"},
                            "ocr_text": {"type": "string"},
                            "speaker_id": {"type": "string"},
                            "addressee_id": {"type": "string"},
                            "speaker_gender": {
                                "type": "string",
                                "enum": ["male", "female", "unknown"],
                            },
                            "speaker_visual_cues": {"type": "string"},
                            "translation": {"type": "string"},
                        },
                        "required": [
                            "box_ids",
                            "ocr_profile_id",
                            "ocr_text",
                            "speaker_id",
                            "addressee_id",
                            "speaker_gender",
                            "speaker_visual_cues",
                            "translation",
                        ],
                    },
                },
                "no_text_boxes": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "image_summary": {"type": "string"},
                "page_events": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "page_characters_detected": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "speaker_id": {"type": "string"},
                            "speaker_gender": {
                                "type": "string",
                                "enum": ["male", "female", "unknown"],
                            },
                            "speaker_visual_cues": {"type": "string"},
                        },
                        "required": ["speaker_id", "speaker_gender", "speaker_visual_cues"],
                    },
                },
            },
            "required": [
                "boxes",
                "no_text_boxes",
                "image_summary",
                "page_events",
                "page_characters_detected",
            ],
        },
        "strict": True,
    }


def build_state_merge_text_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "translate_page_stage2",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "characters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "gender": {"type": "string"},
                            "info": {"type": "string"},
                        },
                        "required": ["name", "gender", "info"],
                    },
                },
                "story_summary": {"type": "string"},
                "open_threads": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "glossary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "term": {"type": "string"},
                            "translation": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["term", "translation", "note"],
                    },
                },
            },
            "required": [
                "characters",
                "story_summary",
                "open_threads",
                "glossary",
            ],
        },
        "strict": True,
    }


def extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise ValueError("Empty response")
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("JSON response must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    snippet = raw[start : end + 1]
    try:
        parsed = json.loads(snippet)
        if not isinstance(parsed, dict):
            raise ValueError("JSON response must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    repaired = repair_json(snippet)
    parsed = json.loads(repaired)
    if not isinstance(parsed, dict):
        raise ValueError("JSON response must be an object")
    return parsed


def repair_json(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r"}\s*{", "},{", text)
    text = re.sub(r"]\s*{", "],{", text)
    text = re.sub(r'([0-9eE"\}\]])\s*("[^"]+"\s*:)', r"\1,\2", text)
    return text


def coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def normalize_translate_stage_result(data: dict[str, Any]) -> dict[str, Any]:
    if "boxes" not in data or "no_text_boxes" not in data:
        raise ValueError("stage1 payload must include boxes and no_text_boxes")

    no_text_box_ids: set[int] = set()
    raw_no_text = data.get("no_text_boxes")
    if isinstance(raw_no_text, list):
        for item in raw_no_text:
            parsed = coerce_positive_int(item)
            if parsed is not None:
                no_text_box_ids.add(parsed)

    boxes: list[dict[str, Any]] = []
    raw_boxes = data.get("boxes")
    if isinstance(raw_boxes, list):
        for raw in raw_boxes:
            if not isinstance(raw, dict):
                continue
            raw_ids = raw.get("box_ids")
            if not isinstance(raw_ids, list):
                continue
            box_ids: list[int] = []
            seen_ids: set[int] = set()
            for item in raw_ids:
                parsed = coerce_positive_int(item)
                if parsed is None or parsed in seen_ids or parsed in no_text_box_ids:
                    continue
                seen_ids.add(parsed)
                box_ids.append(parsed)
            if not box_ids:
                continue

            speaker_gender = str(raw.get("speaker_gender") or "").strip().lower()
            if speaker_gender not in _SPEAKER_GENDER_CHOICES:
                speaker_gender = "unknown"

            boxes.append(
                {
                    "box_ids": box_ids,
                    "ocr_profile_id": str(raw.get("ocr_profile_id") or "unknown").strip()
                    or "unknown",
                    "ocr_text": str(raw.get("ocr_text") or "").strip(),
                    "speaker_id": str(raw.get("speaker_id") or "unknown").strip()
                    or "unknown",
                    "addressee_id": str(raw.get("addressee_id") or "").strip(),
                    "speaker_gender": speaker_gender,
                    "speaker_visual_cues": str(raw.get("speaker_visual_cues") or "").strip(),
                    "translation": str(raw.get("translation") or "").strip(),
                }
            )

    page_events: list[str] = []
    raw_events = data.get("page_events")
    if isinstance(raw_events, list):
        for item in raw_events:
            text = str(item or "").strip()
            if text:
                page_events.append(text)

    page_characters_detected: list[dict[str, str]] = []
    raw_detected = data.get("page_characters_detected")
    if isinstance(raw_detected, list):
        for item in raw_detected:
            if not isinstance(item, dict):
                continue
            speaker_id = str(item.get("speaker_id") or "unknown").strip() or "unknown"
            speaker_gender = str(item.get("speaker_gender") or "").strip().lower()
            if speaker_gender not in _SPEAKER_GENDER_CHOICES:
                speaker_gender = "unknown"
            speaker_visual_cues = str(item.get("speaker_visual_cues") or "").strip()
            page_characters_detected.append(
                {
                    "speaker_id": speaker_id,
                    "speaker_gender": speaker_gender,
                    "speaker_visual_cues": speaker_visual_cues,
                }
            )

    return {
        "boxes": boxes,
        "no_text_boxes": sorted(no_text_box_ids),
        "image_summary": str(data.get("image_summary") or "").strip(),
        "page_events": page_events,
        "page_characters_detected": page_characters_detected,
    }


def _is_short_repetitive_noise(text: str) -> bool:
    cleaned = re.sub(r"\s+", "", str(text or "").strip())
    if not cleaned:
        return False
    if len(cleaned) > 4:
        return False
    return len(set(cleaned)) == 1


def apply_no_text_consensus_guard(
    *,
    stage1_result: dict[str, Any],
    input_boxes: list[dict[str, Any]],
    ocr_profiles: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], list[int]]:
    source_by_index: dict[int, dict[str, Any]] = {}
    for box in input_boxes:
        if not isinstance(box, dict):
            continue
        box_index = coerce_positive_int(box.get("box_index"))
        if box_index is None:
            continue
        source_by_index[box_index] = box

    remote_profile_ids: set[str] = set()
    weak_empty_detection_profile_ids: set[str] = set()
    if isinstance(ocr_profiles, list):
        for profile in ocr_profiles:
            if not isinstance(profile, dict):
                continue
            profile_id = str(profile.get("id") or "").strip()
            if not profile_id:
                continue
            model_id = str(profile.get("model") or "").strip().lower()
            hint = str(profile.get("hint") or "").strip().lower()
            if profile_id.startswith("openai_") or "gpt" in model_id:
                remote_profile_ids.add(profile_id)
            if "empty-crop detection" in hint or "empty crop detection" in hint:
                weak_empty_detection_profile_ids.add(profile_id)

    # Backward-compatible fallback for old profile hints/configs.
    if not weak_empty_detection_profile_ids:
        weak_empty_detection_profile_ids.add("manga_ocr_default")

    def _is_remote_profile(profile_id: str) -> bool:
        return profile_id in remote_profile_ids or profile_id.startswith("openai_")

    no_text_box_ids: set[int] = set()
    raw_no_text = stage1_result.get("no_text_boxes")
    if isinstance(raw_no_text, list):
        for item in raw_no_text:
            parsed = coerce_positive_int(item)
            if parsed is not None:
                no_text_box_ids.add(parsed)

    adjusted_no_text: list[int] = []
    filtered_boxes: list[dict[str, Any]] = []
    raw_boxes = stage1_result.get("boxes")
    if not isinstance(raw_boxes, list):
        return stage1_result, adjusted_no_text

    for entry in raw_boxes:
        if not isinstance(entry, dict):
            continue
        raw_ids = entry.get("box_ids")
        if not isinstance(raw_ids, list):
            filtered_boxes.append(entry)
            continue
        parsed_box_ids = [coerce_positive_int(item) for item in raw_ids]
        box_ids = [item for item in parsed_box_ids if item is not None]
        if len(box_ids) != 1:
            filtered_boxes.append(entry)
            continue
        box_index = box_ids[0]
        if box_index in no_text_box_ids:
            continue
        source_box = source_by_index.get(box_index)
        if not isinstance(source_box, dict):
            filtered_boxes.append(entry)
            continue

        chosen_profile_id = str(entry.get("ocr_profile_id") or "").strip()
        if chosen_profile_id not in weak_empty_detection_profile_ids:
            filtered_boxes.append(entry)
            continue
        chosen_text = str(entry.get("ocr_text") or "").strip()
        if not _is_short_repetitive_noise(chosen_text):
            filtered_boxes.append(entry)
            continue

        raw_no_text_profiles = source_box.get("ocr_no_text_profiles")
        no_text_profiles = raw_no_text_profiles if isinstance(raw_no_text_profiles, list) else []
        remote_no_text_count = 0
        for profile_id in no_text_profiles:
            pid = str(profile_id or "").strip()
            if pid and _is_remote_profile(pid):
                remote_no_text_count += 1

        remote_text_count = 0
        raw_candidates = source_box.get("ocr_candidates")
        if isinstance(raw_candidates, list):
            for candidate in raw_candidates:
                if not isinstance(candidate, dict):
                    continue
                pid = str(candidate.get("profile_id") or "").strip()
                text = str(candidate.get("text") or "").strip()
                if pid and text and _is_remote_profile(pid):
                    remote_text_count += 1

        # Strong consensus fallback: weak local short/noisy hit is overridden by
        # multiple remote no-text signals when no remote text candidate exists.
        if remote_no_text_count >= 2 and remote_text_count == 0:
            no_text_box_ids.add(box_index)
            adjusted_no_text.append(box_index)
            continue

        filtered_boxes.append(entry)

    adjusted_result = dict(stage1_result)
    adjusted_result["boxes"] = filtered_boxes
    adjusted_result["no_text_boxes"] = sorted(no_text_box_ids)
    return adjusted_result, adjusted_no_text


def normalize_state_merge_result(data: dict[str, Any]) -> dict[str, Any]:
    if "characters" not in data or "open_threads" not in data or "glossary" not in data:
        raise ValueError("stage2 payload must include characters/open_threads/glossary")

    characters: list[dict[str, str]] = []
    raw_characters = data.get("characters")
    if isinstance(raw_characters, list):
        for item in raw_characters:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            gender = str(item.get("gender") or "unknown").strip().lower() or "unknown"
            info = str(item.get("info") or "").strip()
            characters.append({"name": name, "gender": gender, "info": info})

    open_threads: list[str] = []
    raw_threads = data.get("open_threads")
    if isinstance(raw_threads, list):
        for item in raw_threads:
            text = str(item or "").strip()
            if text:
                open_threads.append(text)

    glossary: list[dict[str, str]] = []
    raw_glossary = data.get("glossary")
    if isinstance(raw_glossary, list):
        for item in raw_glossary:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term") or "").strip()
            translation = str(item.get("translation") or "").strip()
            note = str(item.get("note") or "").strip()
            if not term or not translation:
                continue
            glossary.append({"term": term, "translation": translation, "note": note})

    return {
        "characters": characters,
        "open_threads": open_threads,
        "glossary": glossary,
        "story_summary": str(data.get("story_summary") or "").strip(),
    }


def json_result_validator(parser: JsonParser) -> Callable[[str], tuple[bool, str | None]]:
    def _validate(text: str) -> tuple[bool, str | None]:
        try:
            parser(extract_json(text))
            return True, None
        except Exception as exc:
            return False, str(exc).strip() or repr(exc)

    return _validate


def repair_with_llm(
    *,
    client: Any,
    model_cfg: dict[str, Any],
    raw_text: str,
    text_format: dict[str, Any],
    component: str,
    log_context: dict[str, Any] | None = None,
) -> str:
    if not raw_text.strip():
        return raw_text

    repair_prompt = (
        "Fix the following JSON to match the required schema. "
        "Return only valid JSON. Do not add commentary."
    )
    input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": repair_prompt}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": raw_text}],
        },
    ]

    repair_cfg = dict(model_cfg)
    repair_cfg["text"] = {"format": text_format}
    if "temperature" in repair_cfg:
        repair_cfg["temperature"] = 0.0
    if "max_output_tokens" in repair_cfg:
        try:
            repair_cfg["max_output_tokens"] = min(int(repair_cfg["max_output_tokens"]), 4096)
        except (TypeError, ValueError):
            repair_cfg["max_output_tokens"] = 2048

    params = build_response_params(repair_cfg, input_payload)
    resp = openai_responses_create(
        client,
        params,
        component=component,
        context=log_context,
    )
    return extract_response_text(resp, raise_on_refusal=True)


def should_retry(response: Any) -> bool:
    status = getattr(response, "status", None)
    if status is None and isinstance(response, dict):
        status = response.get("status")
    if status != "incomplete":
        return False

    details = getattr(response, "incomplete_details", None)
    if details is None and isinstance(response, dict):
        details = response.get("incomplete_details") or {}
    if isinstance(details, dict):
        reason = details.get("reason")
    else:
        reason = getattr(details, "reason", None)
    return reason == "max_output_tokens"


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


def build_model_cfg(
    *,
    model_id: str | None,
    max_output_tokens: int | None,
    reasoning_effort: str | None,
    temperature: float | None,
) -> dict[str, Any]:
    resolved_model = model_id or AGENT_MODEL
    max_output = max_output_tokens or max(
        AGENT_MAX_OUTPUT_TOKENS,
        AGENT_TRANSLATE_MAX_OUTPUT_TOKENS,
    )
    cfg: dict[str, Any] = {
        "model": resolved_model,
        "max_output_tokens": max_output,
    }
    if str(resolved_model).startswith("gpt-5"):
        effort = reasoning_effort or AGENT_TRANSLATE_REASONING_EFFORT or AGENT_REASONING_EFFORT
        if effort not in {"low", "medium", "high"}:
            effort = "medium"
        cfg["reasoning"] = {"effort": effort}
    else:
        cfg["temperature"] = temperature if temperature is not None else AGENT_TEMPERATURE
    return cfg


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
    cfg = dict(model_cfg)
    cfg["text"] = {"format": text_format}
    attempt_count = 1
    api_latency_ms = 0
    repair_latency_ms = 0

    validator = json_result_validator(parser)
    params = build_response_params(cfg, input_payload)
    call_started = time.perf_counter()
    resp = openai_responses_create(
        client,
        params,
        component=component,
        context=log_context,
        result_validator=validator,
    )
    api_latency_ms += int((time.perf_counter() - call_started) * 1000)
    raw_text = extract_response_text(resp, raise_on_refusal=True)

    if should_retry(resp):
        attempt_count += 1
        retry_cfg = dict(cfg)
        current_limit = coerce_positive_int(retry_cfg.get("max_output_tokens")) or 1024
        retry_cfg["max_output_tokens"] = max(current_limit * 2, current_limit + 512)
        retry_params = build_response_params(retry_cfg, input_payload)
        retry_started = time.perf_counter()
        retry_resp = openai_responses_create(
            client,
            retry_params,
            component=component,
            context=log_context,
            result_validator=validator,
        )
        api_latency_ms += int((time.perf_counter() - retry_started) * 1000)
        retry_text = extract_response_text(retry_resp, raise_on_refusal=True)
        if retry_text:
            cfg = retry_cfg
            resp = retry_resp
            raw_text = retry_text

    repaired_text: str | None = None
    try:
        result = parser(extract_json(raw_text))
    except Exception as exc:
        logger.warning("Failed to parse %s JSON, retrying repair: %s", component, exc)
        repair_started = time.perf_counter()
        repaired_text = repair_with_llm(
            client=client,
            model_cfg=cfg,
            raw_text=raw_text,
            text_format=text_format,
            component=repair_component,
            log_context=log_context,
        )
        repair_latency_ms = int((time.perf_counter() - repair_started) * 1000)
        result = parser(extract_json(repaired_text))

    response_dump: Any
    try:
        response_dump = resp.model_dump()
    except Exception:
        response_dump = repr(resp)

    status, incomplete_reason = _response_status_parts(response_dump)
    finish_reason = status
    if status == "incomplete" and incomplete_reason:
        finish_reason = f"incomplete:{incomplete_reason}"

    diagnostics = {
        "model": cfg.get("model"),
        "attempt_count": attempt_count,
        "api_latency_ms": api_latency_ms,
        "repair_latency_ms": repair_latency_ms,
        "latency_ms": max(0, api_latency_ms + repair_latency_ms),
        "response_status": status,
        "incomplete_reason": incomplete_reason,
        "finish_reason": finish_reason,
        "token_usage": _extract_token_usage(response_dump),
        "params": {
            "max_output_tokens": cfg.get("max_output_tokens"),
            "reasoning": cfg.get("reasoning"),
            "temperature": cfg.get("temperature"),
            "text": cfg.get("text"),
        },
        "raw_output_text": raw_text,
        "repair_output_text": repaired_text,
        "response": response_dump,
    }
    return result, diagnostics
