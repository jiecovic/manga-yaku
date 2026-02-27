from __future__ import annotations

import json
import logging
import time
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

from . import page_translate_schema as _schema

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

logger = logging.getLogger(__name__)


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
