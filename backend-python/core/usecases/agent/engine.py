# backend-python/core/usecases/agent/engine.py
"""Primary orchestration logic for agent operations."""

from __future__ import annotations

from threading import Event
from typing import Any

from config import (
    AGENT_MAX_OUTPUT_TOKENS,
    AGENT_MODEL,
    AGENT_PROMPT_FILE,
    AGENT_REASONING_EFFORT,
    AGENT_TEMPERATURE,
)
from infra.llm import (
    build_response_params,
    create_openai_client,
    extract_response_text,
    has_openai_sdk,
    openai_responses_create,
    openai_responses_stream_events,
)
from infra.prompts import load_prompt_bundle, render_prompt_bundle


def _load_system_prompt() -> str:
    bundle = load_prompt_bundle(AGENT_PROMPT_FILE)
    rendered = render_prompt_bundle(
        bundle,
        system_context={},
        user_context={},
    )
    return rendered["system"]


def _build_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    system_prompt = _load_system_prompt()
    input_payload: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        }
    ]
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "")
        content_type = "input_text"
        if role in {"assistant", "tool"}:
            content_type = "output_text"
        input_payload.append(
            {
                "role": role,
                "content": [{"type": content_type, "text": content}],
            }
        )
    return input_payload


def run_agent_chat(messages: list[dict[str, Any]], *, model_id: str | None = None) -> str:
    if not has_openai_sdk():
        raise RuntimeError("OpenAI SDK is not available")

    resolved_model = model_id or AGENT_MODEL
    cfg = {
        "model": resolved_model,
        "max_output_tokens": AGENT_MAX_OUTPUT_TOKENS,
    }
    if str(resolved_model).startswith("gpt-5"):
        effort = AGENT_REASONING_EFFORT
        if effort not in {"low", "medium", "high"}:
            effort = "medium"
        cfg["reasoning"] = {"effort": effort}
    else:
        cfg["temperature"] = AGENT_TEMPERATURE
    client = create_openai_client({})
    input_payload = _build_input(messages)
    params = build_response_params(cfg, input_payload)
    resp = openai_responses_create(
        client,
        params,
        component="agent.chat",
        context={"model_id": str(resolved_model)},
    )
    return extract_response_text(resp).strip()


def run_agent_chat_stream(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None = None,
    stop_event: Event | None = None,
):
    if not has_openai_sdk():
        raise RuntimeError("OpenAI SDK is not available")

    resolved_model = model_id or AGENT_MODEL
    cfg = {
        "model": resolved_model,
        "max_output_tokens": AGENT_MAX_OUTPUT_TOKENS,
    }
    if str(resolved_model).startswith("gpt-5"):
        effort = AGENT_REASONING_EFFORT
        if effort not in {"low", "medium", "high"}:
            effort = "medium"
        cfg["reasoning"] = {"effort": effort}
    else:
        cfg["temperature"] = AGENT_TEMPERATURE

    client = create_openai_client({})
    input_payload = _build_input(messages)
    params = build_response_params(cfg, input_payload)
    params.setdefault("text", {"format": {"type": "text"}})

    had_delta = False
    if stop_event is not None and stop_event.is_set():
        return

    for event in openai_responses_stream_events(
        client,
        params,
        component="agent.chat.stream",
        context={"model_id": str(resolved_model)},
    ):
        if stop_event is not None and stop_event.is_set():
            break
        event_type = getattr(event, "type", None)
        if event_type is None and isinstance(event, dict):
            event_type = event.get("type")
        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", None)
            if delta is None and isinstance(event, dict):
                delta = event.get("delta")
            if delta:
                had_delta = True
                yield str(delta)
        elif event_type == "response.output_text.done" and not had_delta:
            text_value = getattr(event, "text", None)
            if text_value is None and isinstance(event, dict):
                text_value = event.get("text")
            if text_value:
                yield str(text_value)
