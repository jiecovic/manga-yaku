# backend-python/core/usecases/agent/runtime/engine_sdk_runtime.py
"""Shared SDK runtime helpers for agent chat execution."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Any, cast

from config import (
    AGENT_GROUNDING_MODE,
    AGENT_MODEL,
    AGENT_REASONING_EFFORT,
    AGENT_TEMPERATURE,
    DATA_DIR,
)
from core.usecases.agent.grounding.context import (
    build_grounding_message,
    resolve_active_filename,
    should_use_visual_grounding,
)
from core.usecases.agent.grounding.turn_state import (
    PageStateSnapshot,
    build_turn_state_message,
    get_active_page_snapshot,
)
from core.usecases.agent.runtime.mcp_runtime import (
    build_agent_mcp_servers,
    cleanup_mcp_servers,
    connect_mcp_servers,
)
from core.usecases.agent.runtime.streaming import (
    extract_sdk_result_text,
    run_sdk_stream_events,
)
from infra.logging.correlation import append_correlation


@dataclass(frozen=True)
class AgentToolContext:
    """Context object passed into SDK-backed agent tool runs."""

    volume_id: str
    current_filename: str | None


@dataclass(frozen=True)
class PreparedAgentChatRun:
    """Shared prepared chat-run inputs used by both sync and stream execution."""

    resolved_model: str
    volume_id: str
    active_page: PageStateSnapshot
    session: Any
    run_context: AgentToolContext
    mcp_servers: list[Any]
    sdk_input: Any
    grounding_event: str | None = None


def sdk_use_sqlite_session() -> bool:
    """Return whether the optional SDK sqlite session store is enabled."""
    raw = os.getenv("AGENT_SDK_USE_SQLITE_SESSION", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def build_sdk_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize chat history into the Agents SDK input item format."""
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


def build_sdk_agent(
    model_id: str,
    *,
    mcp_servers: list[Any],
    agent_cls: Any,
    model_settings_cls: Any,
    load_system_prompt: Callable[[], str],
    resolve_max_output_tokens: Callable[[], int],
    agents_import_error: Exception | None,
) -> Any:
    """Build the configured Agents SDK agent instance."""
    if agent_cls is None or model_settings_cls is None:
        raise RuntimeError(f"Agents SDK is not available: {agents_import_error!r}")

    settings: dict[str, Any] = {
        "max_tokens": resolve_max_output_tokens(),
        "parallel_tool_calls": False,
    }
    if str(model_id).startswith("gpt-5"):
        effort = AGENT_REASONING_EFFORT
        if effort not in {"low", "medium", "high"}:
            effort = "medium"
        settings["reasoning"] = {"effort": effort}
    else:
        settings["temperature"] = AGENT_TEMPERATURE

    return agent_cls(
        name="MangaYaku Chat",
        instructions=load_system_prompt(),
        model=model_id,
        model_settings=model_settings_cls(**settings),
        mcp_servers=list(mcp_servers),
    )


def build_sdk_session(
    session_id: str | None,
    *,
    use_sqlite_session: bool,
    sqlite_session_cls: Any,
) -> Any:
    """Build the optional SDK sqlite session object when enabled."""
    if not use_sqlite_session:
        return None
    if sqlite_session_cls is None or not session_id:
        return None
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = DATA_DIR / "agent_sdk_sessions.sqlite3"
    session_key = f"chat:{session_id}"
    return sqlite_session_cls(session_id=session_key, db_path=str(db_path))


def _prepare_agent_chat_run(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None,
    volume_id: str | None,
    current_filename: str | None,
    session_id: str | None,
    session_builder: Callable[[str | None], Any],
    input_builder: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    include_activity_events: bool,
) -> PreparedAgentChatRun:
    """Resolve active-page state and build the shared SDK input for one chat turn."""
    resolved_model = model_id or AGENT_MODEL
    volume_value = str(volume_id or "").strip()
    active_filename = None
    if volume_value:
        active_filename = resolve_active_filename(
            volume_id=volume_value,
            requested_filename=current_filename,
        )
    active_page = get_active_page_snapshot(
        volume_id=volume_value,
        current_filename=active_filename,
    )

    session = session_builder(session_id)
    run_context = AgentToolContext(
        volume_id=volume_value,
        current_filename=active_page.filename,
    )
    mcp_servers = build_agent_mcp_servers(
        volume_id=volume_value,
        active_filename=active_page.filename,
    )

    input_items = input_builder(messages)
    input_items.append(
        build_turn_state_message(
            volume_id=volume_value,
            active_filename=active_page.filename,
            text_box_count=active_page.text_box_count,
            page_revision=active_page.page_revision,
        )
    )

    grounding_event: str | None = None
    if volume_value and active_page.filename:
        include_images = should_use_visual_grounding(
            messages,
            grounding_mode_setting=AGENT_GROUNDING_MODE,
        )
        grounding = build_grounding_message(
            volume_id=volume_value,
            filename=active_page.filename,
            page_revision=active_page.page_revision,
            include_images=include_images,
            grounding_mode_setting=AGENT_GROUNDING_MODE,
        )
        if grounding:
            input_items.append(grounding)
            if include_activity_events:
                mode_label = "full" if include_images else "lightweight"
                rev_label = active_page.page_revision or "unknown"
                grounding_event = (
                    f"Loaded {mode_label} grounding for page {active_page.filename} "
                    f"(rev {rev_label})"
                )
        elif include_activity_events:
            grounding_event = f"Failed to load grounding assets for page {active_page.filename}"
    elif include_activity_events and volume_value:
        grounding_event = "No active page selected; running without page grounding"
    elif include_activity_events:
        grounding_event = "No active volume selected; running chat-only context"

    return PreparedAgentChatRun(
        resolved_model=resolved_model,
        volume_id=volume_value,
        active_page=active_page,
        session=session,
        run_context=run_context,
        mcp_servers=mcp_servers,
        sdk_input=cast(Any, input_items),
        grounding_event=grounding_event,
    )


def run_agent_chat_sdk(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None,
    volume_id: str | None,
    current_filename: str | None,
    session_id: str | None,
    runner_cls: Any,
    agent_builder: Callable[..., Any],
    session_builder: Callable[[str | None], Any],
    input_builder: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    resolve_max_turns: Callable[[], int],
    logger: logging.Logger,
    agents_import_error: Exception | None,
) -> str:
    """Run a synchronous chat turn through the Agents SDK runtime."""
    if runner_cls is None:
        raise RuntimeError(f"Agents SDK is not available: {agents_import_error!r}")
    resolved_runner_cls = cast(Any, runner_cls)
    prepared = _prepare_agent_chat_run(
        messages,
        model_id=model_id,
        volume_id=volume_id,
        current_filename=current_filename,
        session_id=session_id,
        session_builder=session_builder,
        input_builder=input_builder,
        include_activity_events=False,
    )

    async def run_once() -> str:
        connected_servers, failed_servers = await connect_mcp_servers(prepared.mcp_servers)
        if not connected_servers:
            raise RuntimeError("No MCP tool servers are available for this agent run")
        for server_name, exc in failed_servers:
            logger.warning(
                append_correlation(
                    f"mcp server unavailable during sync run: {server_name}: {exc}",
                    {
                        "component": "agent.chat.sdk",
                        "session_id": session_id,
                        "volume_id": prepared.volume_id,
                        "filename": prepared.active_page.filename,
                        "model_id": prepared.resolved_model,
                    },
                )
            )

        max_turns = resolve_max_turns()
        agent = agent_builder(prepared.resolved_model, mcp_servers=connected_servers)
        try:
            result = await resolved_runner_cls.run(
                agent,
                input=prepared.sdk_input,
                context=prepared.run_context,
                session=prepared.session,
                max_turns=max_turns,
            )
            return extract_sdk_result_text(result).strip()
        finally:
            await cleanup_mcp_servers(connected_servers)

    return asyncio.run(run_once())


def run_agent_chat_stream_sdk(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None,
    volume_id: str | None,
    current_filename: str | None,
    session_id: str | None,
    stop_event: Event | None,
    runner_cls: Any,
    agent_builder: Callable[..., Any],
    session_builder: Callable[[str | None], Any],
    input_builder: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    resolve_max_turns: Callable[[], int],
    agents_import_error: Exception | None,
):
    """Stream a chat turn through the Agents SDK runtime."""
    if runner_cls is None:
        raise RuntimeError(f"Agents SDK is not available: {agents_import_error!r}")
    prepared = _prepare_agent_chat_run(
        messages,
        model_id=model_id,
        volume_id=volume_id,
        current_filename=current_filename,
        session_id=session_id,
        session_builder=session_builder,
        input_builder=input_builder,
        include_activity_events=True,
    )
    agent = agent_builder(prepared.resolved_model, mcp_servers=prepared.mcp_servers)

    runtime_event = "Agents SDK runtime active (MCP tools)"
    max_turns = resolve_max_turns()

    yield {"type": "activity", "message": runtime_event}
    if prepared.grounding_event:
        yield {"type": "activity", "message": prepared.grounding_event}

    yield from run_sdk_stream_events(
        runner_cls=runner_cls,
        agent=agent,
        sdk_input=prepared.sdk_input,
        run_context=prepared.run_context,
        session=prepared.session,
        mcp_servers=prepared.mcp_servers,
        stop_event=stop_event,
        max_turns=max_turns,
        correlation={
            "component": "agent.chat.stream.sdk",
            "session_id": session_id,
            "volume_id": prepared.volume_id,
            "filename": prepared.active_page.filename,
            "model_id": prepared.resolved_model,
        },
    )
