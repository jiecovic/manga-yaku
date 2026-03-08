# backend-python/core/usecases/page_translation/call.py
"""Use-case helpers for page-translation LLM call operations."""

from __future__ import annotations

import logging
import time
from threading import Event
from typing import Any

from config import (
    AGENT_MAX_OUTPUT_TOKENS,
    AGENT_MODEL,
    AGENT_REASONING_EFFORT,
    AGENT_TEMPERATURE,
    PAGE_TRANSLATION_MAX_OUTPUT_TOKENS,
    PAGE_TRANSLATION_REASONING_EFFORT,
)
from infra.llm import (
    build_response_params,
    extract_response_text,
    openai_responses_create,
)
from infra.llm.model_capabilities import (
    model_applies_reasoning_effort,
    model_applies_temperature,
)
from infra.logging.correlation import append_correlation
from infra.prompts import load_prompt_bundle, render_prompt_bundle

from .schema import coerce_positive_int
from .schema_json import JsonParser, extract_json, json_result_validator, should_retry

logger = logging.getLogger(__name__)

_MAX_STRUCTURED_RETRY_OUTPUT_TOKENS = 4096


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

    bundle = render_prompt_bundle(
        load_prompt_bundle("page_translation/json_repair.yml"),
        system_context={},
        user_context={"RAW_TEXT": raw_text},
    )
    input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": bundle["system"]}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": bundle["user_template"]}],
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
        PAGE_TRANSLATION_MAX_OUTPUT_TOKENS,
    )
    cfg: dict[str, Any] = {
        "model": resolved_model,
        "max_output_tokens": max_output,
    }
    if model_applies_reasoning_effort(resolved_model):
        effort = reasoning_effort or PAGE_TRANSLATION_REASONING_EFFORT or AGENT_REASONING_EFFORT
        if effort not in {"low", "medium", "high"}:
            effort = "medium"
        cfg["reasoning"] = {"effort": effort}
    elif model_applies_temperature(resolved_model):
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
    stop_event: Event | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    def _raise_if_stopped() -> None:
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError(f"{component} canceled")

    cfg = dict(model_cfg)
    cfg["text"] = {"format": text_format}
    attempt_count = 1
    api_latency_ms = 0
    repair_latency_ms = 0

    validator = json_result_validator(parser)
    params = build_response_params(cfg, input_payload)
    _raise_if_stopped()
    call_started = time.perf_counter()
    resp = openai_responses_create(
        client,
        params,
        component=component,
        context=log_context,
        result_validator=validator,
    )
    api_latency_ms += int((time.perf_counter() - call_started) * 1000)
    _raise_if_stopped()
    raw_text = extract_response_text(resp, raise_on_refusal=True)

    if should_retry(resp):
        attempt_count += 1
        retry_cfg = dict(cfg)
        current_limit = coerce_positive_int(retry_cfg.get("max_output_tokens")) or 1024
        retry_cfg["max_output_tokens"] = min(
            max(current_limit * 2, current_limit + 512),
            _MAX_STRUCTURED_RETRY_OUTPUT_TOKENS,
        )
        retry_params = build_response_params(retry_cfg, input_payload)
        _raise_if_stopped()
        retry_started = time.perf_counter()
        retry_resp = openai_responses_create(
            client,
            retry_params,
            component=component,
            context=log_context,
            result_validator=validator,
        )
        api_latency_ms += int((time.perf_counter() - retry_started) * 1000)
        _raise_if_stopped()
        retry_text = extract_response_text(retry_resp, raise_on_refusal=True)
        if retry_text:
            cfg = retry_cfg
            resp = retry_resp
            raw_text = retry_text

    repaired_text: str | None = None
    try:
        result = parser(extract_json(raw_text))
    except Exception as exc:
        logger.warning(
            append_correlation(
                f"Failed to parse {component} JSON, retrying repair: {exc}",
                log_context,
                component_name=component,
            )
        )
        _raise_if_stopped()
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
