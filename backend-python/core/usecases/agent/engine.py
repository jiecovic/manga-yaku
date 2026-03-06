# backend-python/core/usecases/agent/engine.py
"""Primary orchestration logic for agent operations."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from threading import Event
from typing import Any, cast

from config import (
    AGENT_GROUNDING_MODE,
    AGENT_MAX_OUTPUT_TOKENS,
    AGENT_MAX_TURNS,
    AGENT_MODEL,
    AGENT_PROMPT_FILE,
    AGENT_REASONING_EFFORT,
    AGENT_TEMPERATURE,
    DATA_DIR,
)
from core.usecases.agent.grounding_context import (
    build_grounding_message,
    resolve_active_filename,
    should_use_visual_grounding,
)
from core.usecases.agent.mcp_runtime import (
    build_agent_mcp_servers,
    cleanup_mcp_servers,
    connect_mcp_servers,
)
from core.usecases.agent.streaming import (
    extract_sdk_result_text,
    run_legacy_stream_events,
    run_sdk_stream_events,
)
from core.usecases.agent.tool_impl import (
    coerce_filename,
)
from core.usecases.agent.turn_state import (
    build_turn_state_message,
    get_active_page_revision,
    get_active_page_text_box_count,
)
from infra.llm import (
    build_response_params,
    create_openai_client,
    extract_response_text,
    has_openai_sdk,
    openai_responses_create,
)
from infra.logging.correlation import append_correlation, normalize_correlation
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


@dataclass(frozen=True)
class AgentToolContext:
    volume_id: str
    current_filename: str | None


def _load_system_prompt() -> str:
    bundle = load_prompt_bundle(AGENT_PROMPT_FILE)
    rendered = render_prompt_bundle(
        bundle,
        system_context={},
        user_context={},
    )
    return rendered["system"]


def _runtime_choice() -> str:
    raw = os.getenv("AGENT_CHAT_RUNTIME", "sdk").strip().lower()
    if raw not in {"legacy", "sdk"}:
        raw = "sdk"
    if raw == "sdk" and Runner is None:
        return "legacy"
    return raw


def _sdk_use_sqlite_session() -> bool:
    raw = os.getenv("AGENT_SDK_USE_SQLITE_SESSION", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _build_legacy_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _build_sdk_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    input_payload: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "user").strip().lower()
        text = str(msg.get("content") or "").strip()
        if not text:
            continue
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        content_type = "input_text"
        if role in {"assistant", "tool"}:
            content_type = "output_text"
        input_payload.append(
            {
                "role": role,
                "content": [{"type": content_type, "text": text}],
            }
        )
    return input_payload


def _build_sdk_agent(model_id: str, *, mcp_servers: list[Any]) -> Any:
    if Agent is None or ModelSettings is None:
        raise RuntimeError(f"Agents SDK is not available: {_agents_import_error!r}")

    settings: dict[str, Any] = {
        "max_tokens": AGENT_MAX_OUTPUT_TOKENS,
    }
    if str(model_id).startswith("gpt-5"):
        effort = AGENT_REASONING_EFFORT
        if effort not in {"low", "medium", "high"}:
            effort = "medium"
        settings["reasoning"] = {"effort": effort}
    else:
        settings["temperature"] = AGENT_TEMPERATURE

    return Agent(
        name="MangaYaku Chat",
        instructions=_load_system_prompt(),
        model=model_id,
        model_settings=ModelSettings(**settings),
        mcp_servers=list(mcp_servers),
    )


def _build_sdk_session(session_id: str | None) -> Any:
    # We already persist chat history in our own DB, so keep SDK session off by
    # default to avoid duplicated/conflated turn state. Enable only when needed.
    if not _sdk_use_sqlite_session():
        return None
    if SQLiteSession is None or not session_id:
        return None
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = DATA_DIR / "agent_sdk_sessions.sqlite3"
    session_key = f"chat:{session_id}"
    return SQLiteSession(session_id=session_key, db_path=str(db_path))


def _run_agent_chat_legacy(
    messages: list[dict[str, Any]],
    *,
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
    input_payload = _build_legacy_input(messages)
    params = build_response_params(cfg, input_payload)
    resp = openai_responses_create(
        client,
        params,
        component="agent.chat",
        context=normalize_correlation(
            {
                "component": "agent.chat",
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
    if Runner is None:
        raise RuntimeError(f"Agents SDK is not available: {_agents_import_error!r}")

    resolved_model = model_id or AGENT_MODEL
    volume_value = str(volume_id or "").strip()
    requested_filename = coerce_filename(current_filename)
    fallback_filename = coerce_filename(current_filename)
    active_filename = None
    if volume_value:
        active_filename = resolve_active_filename(
            volume_id=volume_value,
            requested_filename=requested_filename,
            fallback_filename=fallback_filename,
        )
    active_text_box_count = get_active_page_text_box_count(
        volume_id=volume_value,
        current_filename=active_filename,
    )
    active_page_revision = get_active_page_revision(
        volume_id=volume_value,
        current_filename=active_filename,
    )

    session = _build_sdk_session(session_id)
    run_context = AgentToolContext(
        volume_id=volume_value,
        current_filename=active_filename,
    )
    mcp_servers = build_agent_mcp_servers(
        volume_id=volume_value,
        active_filename=active_filename,
    )

    input_items = _build_sdk_input(messages)
    input_items.append(
        build_turn_state_message(
            volume_id=volume_value,
            active_filename=active_filename,
            text_box_count=active_text_box_count,
            page_revision=active_page_revision,
        )
    )
    if volume_value and active_filename:
        grounding = build_grounding_message(
            volume_id=volume_value,
            filename=active_filename,
            page_revision=active_page_revision,
            include_images=should_use_visual_grounding(
                messages,
                grounding_mode_setting=AGENT_GROUNDING_MODE,
            ),
            grounding_mode_setting=AGENT_GROUNDING_MODE,
        )
        if grounding:
            input_items.append(grounding)

    sdk_input = cast(Any, input_items)

    async def run_once() -> str:
        connected_servers, failed_servers = await connect_mcp_servers(mcp_servers)
        if not connected_servers:
            raise RuntimeError("No MCP tool servers are available for this agent run")
        for server_name, exc in failed_servers:
            logger.warning(
                append_correlation(
                    f"mcp server unavailable during sync run: {server_name}: {exc}",
                    {
                        "component": "agent.chat.sdk",
                        "session_id": session_id,
                        "volume_id": volume_value,
                        "filename": active_filename,
                        "model_id": resolved_model,
                    },
                )
            )

        agent = _build_sdk_agent(resolved_model, mcp_servers=connected_servers)
        try:
            result = await Runner.run(
                agent,
                input=sdk_input,
                context=run_context,
                session=session,
                max_turns=max(1, int(AGENT_MAX_TURNS)),
            )
            return extract_sdk_result_text(result).strip()
        finally:
            await cleanup_mcp_servers(connected_servers)

    return asyncio.run(run_once())


def run_agent_chat(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None = None,
    volume_id: str | None = None,
    current_filename: str | None = None,
    session_id: str | None = None,
) -> str:
    if _runtime_choice() == "sdk":
        return _run_agent_chat_sdk(
            messages,
            model_id=model_id,
            volume_id=volume_id,
            current_filename=current_filename,
            session_id=session_id,
        )
    return _run_agent_chat_legacy(
        messages,
        model_id=model_id,
        volume_id=volume_id,
        current_filename=current_filename,
        session_id=session_id,
    )


def _run_agent_chat_stream_legacy(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None = None,
    volume_id: str | None = None,
    current_filename: str | None = None,
    session_id: str | None = None,
    stop_event: Event | None = None,
):
    yield from run_legacy_stream_events(
        messages,
        model_id=model_id,
        stop_event=stop_event,
        build_input=_build_legacy_input,
        correlation={
            "component": "agent.chat.stream",
            "session_id": session_id,
            "volume_id": volume_id,
            "filename": current_filename,
            "model_id": model_id or AGENT_MODEL,
        },
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
    runner_cls = Runner
    if runner_cls is None:
        raise RuntimeError(f"Agents SDK is not available: {_agents_import_error!r}")

    resolved_model = model_id or AGENT_MODEL
    volume_value = str(volume_id or "").strip()
    requested_filename = coerce_filename(current_filename)
    fallback_filename = coerce_filename(current_filename)
    active_filename = None
    if volume_value:
        active_filename = resolve_active_filename(
            volume_id=volume_value,
            requested_filename=requested_filename,
            fallback_filename=fallback_filename,
        )
    active_text_box_count = get_active_page_text_box_count(
        volume_id=volume_value,
        current_filename=active_filename,
    )
    active_page_revision = get_active_page_revision(
        volume_id=volume_value,
        current_filename=active_filename,
    )

    session = _build_sdk_session(session_id)
    run_context = AgentToolContext(
        volume_id=volume_value,
        current_filename=active_filename,
    )
    mcp_servers = build_agent_mcp_servers(
        volume_id=volume_value,
        active_filename=active_filename,
    )
    agent = _build_sdk_agent(resolved_model, mcp_servers=mcp_servers)

    input_items = _build_sdk_input(messages)
    input_items.append(
        build_turn_state_message(
            volume_id=volume_value,
            active_filename=active_filename,
            text_box_count=active_text_box_count,
            page_revision=active_page_revision,
        )
    )
    runtime_event = "Agents SDK runtime active (MCP tools)"
    grounding_event: str | None = None
    if volume_value and active_filename:
        include_images = should_use_visual_grounding(
            messages,
            grounding_mode_setting=AGENT_GROUNDING_MODE,
        )
        grounding = build_grounding_message(
            volume_id=volume_value,
            filename=active_filename,
            page_revision=active_page_revision,
            include_images=include_images,
            grounding_mode_setting=AGENT_GROUNDING_MODE,
        )
        if grounding:
            input_items.append(grounding)
            mode_label = "full" if include_images else "lightweight"
            rev_label = active_page_revision or "unknown"
            grounding_event = (
                f"Loaded {mode_label} grounding for page {active_filename} (rev {rev_label})"
            )
        else:
            grounding_event = f"Failed to load grounding assets for page {active_filename}"
    elif volume_value:
        grounding_event = "No active page selected; running without page grounding"
    else:
        grounding_event = "No active volume selected; running chat-only context"
    sdk_input = cast(Any, input_items)

    yield {"type": "activity", "message": runtime_event}
    if grounding_event:
        yield {"type": "activity", "message": grounding_event}

    yield from run_sdk_stream_events(
        runner_cls=runner_cls,
        agent=agent,
        sdk_input=sdk_input,
        run_context=run_context,
        session=session,
        mcp_servers=mcp_servers,
        stop_event=stop_event,
        max_turns=max(1, int(AGENT_MAX_TURNS)),
        correlation={
            "component": "agent.chat.stream.sdk",
            "session_id": session_id,
            "volume_id": volume_value,
            "filename": active_filename,
            "model_id": resolved_model,
        },
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
    if _runtime_choice() == "legacy":
        yield from _run_agent_chat_stream_legacy(
            messages,
            model_id=model_id,
            volume_id=volume_id,
            current_filename=current_filename,
            session_id=session_id,
            stop_event=stop_event,
        )
        return

    yield from _run_agent_chat_stream_sdk(
        messages,
        model_id=model_id,
        volume_id=volume_id,
        current_filename=current_filename,
        session_id=session_id,
        stop_event=stop_event,
    )
