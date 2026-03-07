# backend-python/core/usecases/agent/engine_sdk_runtime.py
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
from core.usecases.agent.streaming import extract_sdk_result_text, run_sdk_stream_events
from core.usecases.agent.tool_shared import coerce_filename
from core.usecases.agent.turn_state import (
    build_turn_state_message,
    get_active_page_revision,
    get_active_page_text_box_count,
)
from infra.logging.correlation import append_correlation


@dataclass(frozen=True)
class AgentToolContext:
    """Context object passed into SDK-backed agent tool runs."""

    volume_id: str
    current_filename: str | None


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

    session = session_builder(session_id)
    run_context = AgentToolContext(
        volume_id=volume_value,
        current_filename=active_filename,
    )
    mcp_servers = build_agent_mcp_servers(
        volume_id=volume_value,
        active_filename=active_filename,
    )

    input_items = input_builder(messages)
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

        max_turns = resolve_max_turns()
        agent = agent_builder(resolved_model, mcp_servers=connected_servers)
        try:
            result = await resolved_runner_cls.run(
                agent,
                input=sdk_input,
                context=run_context,
                session=session,
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

    session = session_builder(session_id)
    run_context = AgentToolContext(
        volume_id=volume_value,
        current_filename=active_filename,
    )
    mcp_servers = build_agent_mcp_servers(
        volume_id=volume_value,
        active_filename=active_filename,
    )
    agent = agent_builder(resolved_model, mcp_servers=mcp_servers)

    input_items = input_builder(messages)
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
    max_turns = resolve_max_turns()
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
        max_turns=max_turns,
        correlation={
            "component": "agent.chat.stream.sdk",
            "session_id": session_id,
            "volume_id": volume_value,
            "filename": active_filename,
            "model_id": resolved_model,
        },
    )
