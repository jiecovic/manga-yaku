# backend-python/core/usecases/agent/engine.py
"""Primary orchestration logic for agent operations."""

from __future__ import annotations

import logging
from threading import Event
from typing import Any

from config import (
    AGENT_MODEL,
    AGENT_PROMPT_FILE,
    TRANSLATION_SOURCE_LANGUAGE,
    TRANSLATION_TARGET_LANGUAGE,
)
from core.usecases.agent.chat_runtime_settings import (
    resolve_agent_chat_max_output_tokens,
    resolve_agent_chat_max_turns,
)
from core.usecases.agent.runtime.engine_sdk_runtime import (
    build_sdk_agent as _build_sdk_agent_impl,
)
from core.usecases.agent.runtime.engine_sdk_runtime import (
    build_sdk_input as _build_sdk_input_impl,
)
from core.usecases.agent.runtime.engine_sdk_runtime import (
    build_sdk_session as _build_sdk_session_impl,
)
from core.usecases.agent.runtime.engine_sdk_runtime import (
    run_agent_chat_sdk as _run_agent_chat_sdk_impl,
)
from core.usecases.agent.runtime.engine_sdk_runtime import (
    run_agent_chat_stream_sdk as _run_agent_chat_stream_sdk_impl,
)
from core.usecases.agent.runtime.engine_sdk_runtime import (
    sdk_use_sqlite_session as _sdk_use_sqlite_session_impl,
)
from infra.llm import (
    build_response_params,
    create_openai_client,
    extract_response_text,
    has_openai_sdk,
    openai_responses_create,
)
from infra.logging.correlation import normalize_correlation
from infra.prompts import load_prompt_bundle, render_prompt_bundle

# Optional Agents SDK imports.
try:
    from agents import (
        Agent,
        ModelSettings,
        Runner,
        SQLiteSession,
    )

    _agents_import_error: Exception | None = None
except Exception as exc:  # pragma: no cover - optional dependency path
    Agent = None  # type: ignore[assignment]
    ModelSettings = None  # type: ignore[assignment]
    Runner = None  # type: ignore[assignment]
    SQLiteSession = None  # type: ignore[assignment]
    _agents_import_error = exc


logger = logging.getLogger(__name__)


def _resolve_agent_chat_max_turns() -> int:
    return resolve_agent_chat_max_turns()


def _resolve_agent_chat_max_output_tokens() -> int:
    return resolve_agent_chat_max_output_tokens()


def _load_system_prompt() -> str:
    bundle = load_prompt_bundle(AGENT_PROMPT_FILE)
    rendered = render_prompt_bundle(
        bundle,
        system_context={
            "SOURCE_LANG": TRANSLATION_SOURCE_LANGUAGE,
            "TARGET_LANG": TRANSLATION_TARGET_LANGUAGE,
        },
        user_context={},
    )
    return rendered["system"]


def _build_repair_prompt_payload(
    *,
    conversation_excerpt: str,
    action_excerpt: str,
) -> list[dict[str, Any]]:
    bundle = load_prompt_bundle("agent/chat/repair.yml")
    rendered = render_prompt_bundle(
        bundle,
        system_context={},
        user_context={
            "CONVERSATION_EXCERPT": conversation_excerpt or "(empty)",
            "ACTION_EXCERPT": action_excerpt or "(none)",
        },
    )
    return [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": rendered["system"]}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": rendered["user_template"]}],
        },
    ]


def _sdk_use_sqlite_session() -> bool:
    return _sdk_use_sqlite_session_impl()


def _build_sdk_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _build_sdk_input_impl(messages)


def _build_repair_conversation_excerpt(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages[-6:]:
        role = str(msg.get("role") or "user").strip().lower()
        text = str(msg.get("content") or "").strip()
        if not text:
            continue
        lines.append(f"{role}: {text}")
    return "\n\n".join(lines).strip()


def _build_repair_action_excerpt(action_events: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for event in action_events[-12:]:
        event_type = str(event.get("type") or "").strip().lower()
        message = str(event.get("message") or "").strip()
        if not message:
            continue
        if event_type in {"tool_called", "tool_output", "activity", "page_switch"}:
            lines.append(f"- {message}")
    return "\n".join(lines).strip()


def _build_sdk_agent(model_id: str, *, mcp_servers: list[Any]) -> Any:
    return _build_sdk_agent_impl(
        model_id,
        mcp_servers=mcp_servers,
        agent_cls=Agent,
        model_settings_cls=ModelSettings,
        load_system_prompt=_load_system_prompt,
        resolve_max_output_tokens=_resolve_agent_chat_max_output_tokens,
        agents_import_error=_agents_import_error,
    )


def _build_sdk_session(session_id: str | None) -> Any:
    return _build_sdk_session_impl(
        session_id,
        use_sqlite_session=_sdk_use_sqlite_session(),
        sqlite_session_cls=SQLiteSession,
    )


def run_agent_chat_repair(
    messages: list[dict[str, Any]],
    *,
    action_events: list[dict[str, str]],
    model_id: str | None = None,
    volume_id: str | None = None,
    current_filename: str | None = None,
    session_id: str | None = None,
) -> str:
    if not has_openai_sdk():
        raise RuntimeError("OpenAI SDK is not available")

    resolved_model = model_id or AGENT_MODEL
    cfg = {
        "model": resolved_model,
        "max_output_tokens": _resolve_agent_chat_max_output_tokens(),
    }

    conversation_excerpt = _build_repair_conversation_excerpt(messages)
    action_excerpt = _build_repair_action_excerpt(action_events)
    input_payload = _build_repair_prompt_payload(
        conversation_excerpt=conversation_excerpt,
        action_excerpt=action_excerpt,
    )

    client = create_openai_client({})
    params = build_response_params(cfg, input_payload)
    resp = openai_responses_create(
        client,
        params,
        component="agent.chat.repair",
        context=normalize_correlation(
            {
                "component": "agent.chat.repair",
                "model_id": str(resolved_model),
                "session_id": session_id,
                "volume_id": volume_id,
                "filename": current_filename,
            }
        ),
    )
    return extract_response_text(resp).strip()


def _run_agent_chat_sdk(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None,
    volume_id: str | None,
    current_filename: str | None,
    session_id: str | None,
) -> str:
    return _run_agent_chat_sdk_impl(
        messages,
        model_id=model_id,
        volume_id=volume_id,
        current_filename=current_filename,
        session_id=session_id,
        runner_cls=Runner,
        agent_builder=_build_sdk_agent,
        session_builder=_build_sdk_session,
        input_builder=_build_sdk_input,
        resolve_max_turns=_resolve_agent_chat_max_turns,
        logger=logger,
        agents_import_error=_agents_import_error,
    )


def run_agent_chat(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None = None,
    volume_id: str | None = None,
    current_filename: str | None = None,
    session_id: str | None = None,
) -> str:
    return _run_agent_chat_sdk(
        messages,
        model_id=model_id,
        volume_id=volume_id,
        current_filename=current_filename,
        session_id=session_id,
    )


def _run_agent_chat_stream_sdk(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None,
    volume_id: str | None,
    current_filename: str | None,
    session_id: str | None,
    stop_event: Event | None = None,
):
    yield from _run_agent_chat_stream_sdk_impl(
        messages,
        model_id=model_id,
        volume_id=volume_id,
        current_filename=current_filename,
        session_id=session_id,
        stop_event=stop_event,
        runner_cls=Runner,
        agent_builder=_build_sdk_agent,
        session_builder=_build_sdk_session,
        input_builder=_build_sdk_input,
        resolve_max_turns=_resolve_agent_chat_max_turns,
        agents_import_error=_agents_import_error,
    )


def run_agent_chat_stream(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None = None,
    volume_id: str | None = None,
    current_filename: str | None = None,
    session_id: str | None = None,
    stop_event: Event | None = None,
):
    yield from _run_agent_chat_stream_sdk(
        messages,
        model_id=model_id,
        volume_id=volume_id,
        current_filename=current_filename,
        session_id=session_id,
        stop_event=stop_event,
    )
