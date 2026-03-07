# backend-python/api/routers/agent/reply_sync.py
"""Synchronous agent reply creation helpers."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from api.schemas.agent_chat import AgentMessagePublic, AgentReplyRequest
from config import AGENT_MODEL, AGENT_MODELS
from core.usecases.agent.engine import run_agent_chat
from core.usecases.agent.turn_state import (
    get_active_page_text_box_count,
    sanitize_agent_reply_text,
    stale_context_warning_message,
)
from fastapi import HTTPException
from infra.db.agent_store import add_agent_message, get_agent_session, list_agent_messages

from .helpers import (
    build_prompt_payload,
    extract_request_id,
    is_provider_server_error,
    log_agent_sdk_attempt,
    persist_agent_warning_message,
)


async def create_agent_reply_message(
    session_id: str,
    req: AgentReplyRequest,
) -> AgentMessagePublic:
    """Create a synchronous assistant reply for an existing session."""
    session = get_agent_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    max_messages = max(1, min(100, int(req.maxMessages)))
    history = list_agent_messages(session_id, limit=max_messages)
    payload = build_prompt_payload(history)
    model_id = session.model_id or AGENT_MODEL
    if model_id not in AGENT_MODELS and AGENT_MODELS:
        model_id = AGENT_MODELS[0]
    reply_started_at = time.monotonic()
    try:
        response_text = await asyncio.to_thread(
            run_agent_chat,
            payload,
            model_id=model_id,
            volume_id=session.volume_id,
            current_filename=req.currentFilename,
            session_id=session_id,
        )
    except Exception as exc:
        error_text = str(exc).strip()
        request_id = str(getattr(exc, "request_id", "") or "").strip() or extract_request_id(
            error_text
        )
        log_agent_sdk_attempt(
            component="agent.chat.sync.sdk",
            status="error",
            session_id=session_id,
            volume_id=session.volume_id,
            filename=req.currentFilename,
            model_id=model_id,
            messages=payload,
            action_events=None,
            error_detail=error_text,
            request_id=request_id,
            latency_ms=round((time.monotonic() - reply_started_at) * 1000),
            finish_reason=(
                "provider_error"
                if is_provider_server_error(exc=exc, text=error_text)
                else "exception"
            ),
            phase="sync_reply",
        )
        raise
    active_text_box_count = get_active_page_text_box_count(
        volume_id=session.volume_id,
        current_filename=req.currentFilename,
    )
    response_text, guard_reason = sanitize_agent_reply_text(
        response_text=response_text,
        messages=payload,
        active_filename=req.currentFilename,
        active_text_box_count=active_text_box_count,
    )
    warning_messages: list[dict[str, Any]] = []
    assistant_meta: dict[str, Any] = {"source": "agent_reply"}
    if guard_reason == "stale_context_warning":
        warning_text = stale_context_warning_message(
            active_filename=req.currentFilename,
            active_text_box_count=active_text_box_count,
        )
        warning_messages.append(
            persist_agent_warning_message(
                session_id,
                message=warning_text,
                filename=req.currentFilename,
            )
        )
        assistant_meta["warnings"] = [warning_text]
    log_agent_sdk_attempt(
        component="agent.chat.sync.sdk",
        status="success" if response_text else "error",
        session_id=session_id,
        volume_id=session.volume_id,
        filename=req.currentFilename,
        model_id=model_id,
        messages=payload,
        action_events=None,
        response_text=response_text,
        error_detail=(None if response_text else "Sync reply completed without final text"),
        latency_ms=round((time.monotonic() - reply_started_at) * 1000),
        finish_reason="completed" if response_text else "empty_output",
        phase="sync_reply",
    )

    message = add_agent_message(
        session_id,
        role="assistant",
        content=response_text,
        meta=assistant_meta,
    )
    if warning_messages:
        message["meta"] = {
            **(message.get("meta") or {}),
            "timelineMessages": warning_messages,
        }
    return message
