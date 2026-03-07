# backend-python/api/routers/agent/routes.py
"""HTTP routes for agent endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from api.schemas.agent_chat import (
    AgentConfigResponse,
    AgentMessagePublic,
    AgentModelPublic,
    AgentReplyRequest,
    AgentSessionPublic,
    CreateAgentMessageRequest,
    CreateAgentSessionRequest,
    UpdateAgentSessionRequest,
)
from config import AGENT_MAX_MESSAGE_CHARS, AGENT_MODEL, AGENT_MODELS
from core.usecases.agent.engine import (
    run_agent_chat,
    run_agent_chat_repair,
    run_agent_chat_stream,
)
from core.usecases.agent.turn_state import (
    get_active_page_text_box_count,
    sanitize_agent_reply_text,
)
from infra.db.agent_store import (
    add_agent_message,
    create_agent_session,
    delete_agent_session,
    get_agent_session,
    list_agent_messages,
    list_agent_sessions,
    update_agent_session,
)
from infra.db.llm_call_log_store import create_llm_call_log
from infra.http import cors_headers_for_stream
from infra.logging.correlation import append_correlation, normalize_correlation

router = APIRouter(tags=["agent"])
logger = logging.getLogger(__name__)

_STREAM_TASKS: set[asyncio.Task] = set()
# Keep background stream tasks alive until completion.
_REQUEST_ID_RE = re.compile(r"\b(req_[A-Za-z0-9]+)\b")


def _extract_request_id(value: str) -> str | None:
    match = _REQUEST_ID_RE.search(value or "")
    if not match:
        return None
    return match.group(1)


def _provider_error_fallback_reply(
    *,
    request_id: str | None,
    active_filename: str | None,
) -> str:
    page_suffix = f" for {active_filename}" if active_filename else ""
    if request_id:
        return (
            "The model provider returned a transient server error"
            f" ({request_id}){page_suffix} and no final text was produced. Please retry."
        )
    return (
        "The model provider returned a transient server error"
        f"{page_suffix} and no final text was produced. Please retry."
    )


def _truncate_text(value: str, *, limit: int = 2000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _sanitize_agent_log_payload(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            lowered = str(key).strip().lower()
            if lowered == "image_url" and isinstance(val, str) and val.startswith("data:image/"):
                out[key] = f"<redacted:data-url:{len(val)}>"
                continue
            out[key] = _sanitize_agent_log_payload(val)
        return out
    if isinstance(value, list):
        return [_sanitize_agent_log_payload(item) for item in value]
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return f"<redacted:data-url:{len(value)}>"
        return _truncate_text(value, limit=12000)
    return value


def _build_agent_request_excerpt(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in messages[-6:]:
        role = str(item.get("role") or "user").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return _truncate_text("\n\n".join(lines), limit=8000)


def _log_agent_sdk_attempt(
    *,
    component: str,
    status: str,
    session_id: str,
    volume_id: str,
    filename: str | None,
    model_id: str,
    messages: list[dict[str, Any]],
    action_events: list[dict[str, str]] | None,
    response_text: str | None = None,
    error_detail: str | None = None,
    request_id: str | None = None,
    latency_ms: int | None = None,
    finish_reason: str | None = None,
    attempt: int | None = None,
    phase: str | None = None,
) -> None:
    try:
        payload = _sanitize_agent_log_payload(
            {
                "phase": phase,
                "session_id": session_id,
                "volume_id": volume_id,
                "filename": filename,
                "model_id": model_id,
                "request_id": request_id,
                "messages": messages,
                "action_events": action_events or [],
                "response_text": response_text or "",
                "error_detail": error_detail,
            }
        )
        params_snapshot = normalize_correlation(
            {
                "component": component,
                "session_id": session_id,
                "volume_id": volume_id,
                "filename": filename,
                "model_id": model_id,
                "request_id": request_id,
            }
        )
        if phase:
            params_snapshot["phase"] = phase

        create_llm_call_log(
            provider="openai",
            api="responses_agents_sdk",
            component=component,
            status=status,
            model_id=model_id,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            error_detail=_truncate_text(error_detail or "", limit=8000) or None,
            params_snapshot=params_snapshot,
            request_excerpt=_build_agent_request_excerpt(messages),
            response_excerpt=_truncate_text(response_text or "", limit=8000) or None,
            payload=payload,
            attempt=attempt,
        )
    except Exception:
        logger.exception(
            append_correlation(
                "failed to persist agent sdk call log",
                normalize_correlation(
                    {
                        "component": component,
                        "session_id": session_id,
                        "volume_id": volume_id,
                        "filename": filename,
                        "model_id": model_id,
                        "request_id": request_id,
                    }
                ),
            )
        )


def _is_provider_server_error(*, exc: Exception | None = None, text: str | None = None) -> bool:
    if exc is not None:
        err_type = str(getattr(exc, "type", "") or "").strip().lower()
        err_code = str(getattr(exc, "code", "") or "").strip().lower()
        if err_type == "server_error" or err_code == "server_error":
            return True
    lowered = str(text or "").strip().lower()
    return "server_error" in lowered


def _try_text_repair_reply(
    *,
    messages: list[dict[str, Any]],
    action_events: list[dict[str, str]],
    session_id: str,
    volume_id: str,
    filename: str | None,
    model_id: str,
) -> str:
    try:
        repaired = run_agent_chat_repair(
            messages,
            action_events=action_events,
            model_id=model_id,
            volume_id=volume_id,
            current_filename=filename,
            session_id=session_id,
        ).strip()
    except Exception:
        logger.exception(
            append_correlation(
                "agent text repair fallback failed",
                normalize_correlation(
                    {
                        "component": "agent.reply.repair",
                        "session_id": session_id,
                        "volume_id": volume_id,
                        "filename": filename,
                        "model_id": model_id,
                    }
                ),
            )
        )
        return ""
    return repaired


def _build_prompt_payload(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for item in history:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "tool":
            continue
        payload.append({"role": role or "user", "content": content})
    return payload


def _persist_action_event_messages(
    session_id: str,
    action_events: list[dict[str, str]],
) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    for action in action_events:
        event_type = str(action.get("type") or "").strip()
        message = str(action.get("message") or "").strip()
        if event_type not in {"activity", "tool_called", "tool_output", "page_switch"}:
            continue
        if not message:
            continue
        meta: dict[str, Any] = {
            "source": "agent_timeline",
            "timelineOnly": True,
            "eventType": event_type,
        }
        tool_name = str(action.get("tool") or "").strip()
        filename = str(action.get("filename") or "").strip()
        if tool_name:
            meta["tool"] = tool_name
        if filename:
            meta["filename"] = filename
        persisted.append(
            add_agent_message(
                session_id,
                role="tool",
                content=message,
                meta=meta,
            )
        )
    return persisted


@router.get("/agent/config", response_model=AgentConfigResponse)
async def get_agent_config() -> AgentConfigResponse:
    """Return agent config."""
    models = [
        AgentModelPublic(id=model_id, label=model_id)
        for model_id in AGENT_MODELS
    ]
    default_model = AGENT_MODEL
    if default_model not in AGENT_MODELS and AGENT_MODELS:
        default_model = AGENT_MODELS[0]
    return AgentConfigResponse(
        models=models,
        defaultModel=default_model,
        maxMessageChars=AGENT_MAX_MESSAGE_CHARS,
    )


@router.get("/agent/sessions", response_model=list[AgentSessionPublic])
async def get_agent_sessions(
    volume_id: str = Query(..., alias="volumeId"),
) -> list[AgentSessionPublic]:
    """Return agent sessions."""
    return list_agent_sessions(volume_id)


@router.post("/agent/sessions", response_model=AgentSessionPublic)
async def create_session(
    req: CreateAgentSessionRequest,
) -> AgentSessionPublic:
    """Create session."""
    try:
        model_id = req.modelId
        if model_id:
            model_id = model_id.strip()
        if model_id and model_id not in AGENT_MODELS:
            raise HTTPException(status_code=400, detail="Unknown agent model")
        if not model_id:
            model_id = AGENT_MODEL
        return create_agent_session(req.volumeId, req.title, model_id=model_id)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "Volume not found" in message else 400
        raise HTTPException(status_code=status, detail=message) from exc


@router.get("/agent/sessions/{session_id}", response_model=AgentSessionPublic)
async def get_agent_session_by_id(
    session_id: str,
) -> AgentSessionPublic:
    """Return agent session by id."""
    session = get_agent_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": str(session.id),
        "volumeId": session.volume_id,
        "title": session.title,
        "modelId": session.model_id,
        "createdAt": session.created_at.isoformat(),
        "updatedAt": session.updated_at.isoformat(),
    }


@router.patch("/agent/sessions/{session_id}", response_model=AgentSessionPublic)
async def patch_agent_session(
    session_id: str,
    req: UpdateAgentSessionRequest,
) -> AgentSessionPublic:
    """Partially update agent session."""
    model_id = req.modelId
    if model_id:
        model_id = model_id.strip()
    if model_id and model_id not in AGENT_MODELS:
        raise HTTPException(status_code=400, detail="Unknown agent model")
    try:
        return update_agent_session(
            session_id,
            title=req.title,
            model_id=model_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/agent/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Delete session."""
    try:
        delete_agent_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": 1}


@router.get(
    "/agent/sessions/{session_id}/messages",
    response_model=list[AgentMessagePublic],
)
async def get_agent_messages(session_id: str) -> list[AgentMessagePublic]:
    """Return agent messages."""
    if get_agent_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return list_agent_messages(session_id)


@router.post(
    "/agent/sessions/{session_id}/messages",
    response_model=AgentMessagePublic,
)
async def create_agent_message(
    session_id: str,
    req: CreateAgentMessageRequest,
) -> AgentMessagePublic:
    """Create agent message."""
    if len(req.content or "") > AGENT_MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Message too long (max {AGENT_MAX_MESSAGE_CHARS} chars)",
        )
    try:
        return add_agent_message(
            session_id,
            role=req.role,
            content=req.content,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc


@router.post(
    "/agent/sessions/{session_id}/reply",
    response_model=AgentMessagePublic,
)
async def create_agent_reply(
    session_id: str,
    req: AgentReplyRequest,
) -> AgentMessagePublic:
    """Create agent reply."""
    session = get_agent_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    max_messages = max(1, min(100, int(req.maxMessages)))
    history = list_agent_messages(session_id, limit=max_messages)
    payload = _build_prompt_payload(history)
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
        request_id = (
            str(getattr(exc, "request_id", "") or "").strip()
            or _extract_request_id(error_text)
        )
        _log_agent_sdk_attempt(
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
                if _is_provider_server_error(exc=exc, text=error_text)
                else "exception"
            ),
            phase="sync_reply",
        )
        raise
    active_text_box_count = get_active_page_text_box_count(
        volume_id=session.volume_id,
        current_filename=req.currentFilename,
    )
    response_text, _ = sanitize_agent_reply_text(
        response_text=response_text,
        messages=payload,
        active_filename=req.currentFilename,
        active_text_box_count=active_text_box_count,
    )
    _log_agent_sdk_attempt(
        component="agent.chat.sync.sdk",
        status="success" if response_text else "error",
        session_id=session_id,
        volume_id=session.volume_id,
        filename=req.currentFilename,
        model_id=model_id,
        messages=payload,
        action_events=None,
        response_text=response_text,
        error_detail=(
            None
            if response_text
            else "Sync reply completed without final text"
        ),
        latency_ms=round((time.monotonic() - reply_started_at) * 1000),
        finish_reason="completed" if response_text else "empty_output",
        phase="sync_reply",
    )

    return add_agent_message(
        session_id,
        role="assistant",
        content=response_text,
        meta={"source": "agent_reply"},
    )


@router.get("/agent/sessions/{session_id}/reply/stream")
async def stream_agent_reply(
    session_id: str,
    request: Request,
    max_messages: int = Query(20, alias="maxMessages"),
    current_filename: str | None = Query(None, alias="currentFilename"),
) -> StreamingResponse:
    """Stream agent reply."""
    session = get_agent_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    limit = max(1, min(100, int(max_messages)))
    history = list_agent_messages(session_id, limit=limit)
    payload = _build_prompt_payload(history)
    model_id = session.model_id or AGENT_MODEL
    if model_id not in AGENT_MODELS and AGENT_MODELS:
        model_id = AGENT_MODELS[0]

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    stop_event = threading.Event()
    loop = asyncio.get_running_loop()

    def run_stream() -> None:
        text_chunks: list[str] = []
        action_events: list[dict[str, str]] = []
        runtime_active_filename = current_filename
        stream_started_at = time.monotonic()
        primary_stream_used_retry = False
        initial_text_box_count = get_active_page_text_box_count(
            volume_id=session.volume_id,
            current_filename=runtime_active_filename,
        )
        def _corr(**extras: object) -> dict[str, object]:
            return normalize_correlation(
                {
                    "component": "agent.reply.stream",
                    "session_id": session_id,
                    "volume_id": session.volume_id,
                    "filename": runtime_active_filename,
                    "model_id": model_id,
                },
                **extras,
            )

        logger.info(append_correlation("agent stream start", _corr(), max_messages=limit))
        try:
            for stream_event in run_agent_chat_stream(
                payload,
                model_id=model_id,
                volume_id=session.volume_id,
                current_filename=current_filename,
                session_id=session_id,
                stop_event=stop_event,
            ):
                event_type = str(stream_event.get("type") or "").strip()
                if event_type == "delta":
                    delta = str(stream_event.get("delta") or "")
                    if delta:
                        text_chunks.append(delta)
                        logger.debug(
                            append_correlation(
                                "agent stream delta",
                                _corr(),
                                chars=len(delta),
                            )
                        )
                elif event_type in {"activity", "tool_called", "tool_output", "page_switch"}:
                    if event_type == "tool_called" and text_chunks:
                        # Discard provisional draft text once tool execution starts.
                        # The post-tool model pass should produce the grounded final answer.
                        text_chunks.clear()
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            {"type": "delta_reset"},
                        )
                        action_events.append(
                            {
                                "type": "activity",
                                "message": "Reset draft response after tool call; waiting for grounded final answer",
                            }
                        )
                    switched_filename = ""
                    if event_type == "page_switch":
                        switched_filename = str(stream_event.get("filename") or "").strip()
                        if switched_filename:
                            runtime_active_filename = switched_filename
                    msg = str(stream_event.get("message") or "").strip()
                    if msg:
                        action: dict[str, str] = {"type": event_type, "message": msg}
                        if event_type in {"tool_called", "tool_output", "page_switch"}:
                            tool_name = str(stream_event.get("tool") or "").strip()
                            if tool_name:
                                action["tool"] = tool_name
                        if event_type == "page_switch" and switched_filename:
                            action["filename"] = switched_filename
                        action_events.append(action)
                        action_events = action_events[-40:]
                elif event_type:
                    logger.info(
                        append_correlation(
                            "agent stream event",
                            _corr(),
                            event_type=event_type,
                        )
                    )
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    stream_event,
                )
            if stop_event.is_set():
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "canceled"},
                )
                logger.info(append_correlation("agent stream canceled", _corr()))
                return
            response_text = "".join(text_chunks).strip()
            if not response_text:
                primary_stream_used_retry = True
                _log_agent_sdk_attempt(
                    component="agent.chat.stream.sdk",
                    status="error",
                    session_id=session_id,
                    volume_id=session.volume_id,
                    filename=runtime_active_filename,
                    model_id=model_id,
                    messages=payload,
                    action_events=action_events,
                    error_detail="Streamed SDK run completed without final text",
                    latency_ms=round((time.monotonic() - stream_started_at) * 1000),
                    finish_reason="empty_output",
                    phase="stream_primary",
                )
                logger.warning(
                    append_correlation(
                        "agent stream empty output; retrying sync once",
                        _corr(),
                    )
                )
                retry_started_at = time.monotonic()
                try:
                    retry_text = run_agent_chat(
                        payload,
                        model_id=model_id,
                        volume_id=session.volume_id,
                        current_filename=runtime_active_filename,
                        session_id=session_id,
                    ).strip()
                except Exception as retry_exc:
                    retry_error_text = str(retry_exc).strip()
                    retry_request_id = (
                        str(getattr(retry_exc, "request_id", "") or "").strip()
                        or _extract_request_id(retry_error_text)
                    )
                    _log_agent_sdk_attempt(
                        component="agent.chat.sync.sdk",
                        status="error",
                        session_id=session_id,
                        volume_id=session.volume_id,
                        filename=runtime_active_filename,
                        model_id=model_id,
                        messages=payload,
                        action_events=action_events,
                        error_detail=retry_error_text,
                        request_id=retry_request_id,
                        latency_ms=round((time.monotonic() - retry_started_at) * 1000),
                        finish_reason=(
                            "provider_error"
                            if _is_provider_server_error(exc=retry_exc, text=retry_error_text)
                            else "exception"
                        ),
                        phase="stream_empty_retry_sync",
                    )
                    if _is_provider_server_error(exc=retry_exc, text=retry_error_text):
                        response_text = _provider_error_fallback_reply(
                            request_id=retry_request_id,
                            active_filename=runtime_active_filename,
                        )
                        action_events.append(
                            {
                                "type": "activity",
                                "message": (
                                    f"Streaming empty-output retry hit provider server error ({retry_request_id}); returned deterministic provider fallback"
                                    if retry_request_id
                                    else "Streaming empty-output retry hit provider server error; returned deterministic provider fallback"
                                ),
                            }
                        )
                        logger.warning(
                            append_correlation(
                                "agent stream empty-output sync retry provider error",
                                _corr(request_id=retry_request_id),
                            )
                        )
                    else:
                        logger.exception(
                            append_correlation(
                                "agent stream empty-output sync retry failed",
                                _corr(),
                            )
                        )
                else:
                    if retry_text:
                        _log_agent_sdk_attempt(
                            component="agent.chat.sync.sdk",
                            status="success",
                            session_id=session_id,
                            volume_id=session.volume_id,
                            filename=runtime_active_filename,
                            model_id=model_id,
                            messages=payload,
                            action_events=action_events,
                            response_text=retry_text,
                            latency_ms=round((time.monotonic() - retry_started_at) * 1000),
                            finish_reason="completed",
                            phase="stream_empty_retry_sync",
                        )
                        response_text = retry_text
                        action_events.append(
                            {
                                "type": "activity",
                                "message": "Streaming produced empty output; recovered via sync retry",
                            }
                        )
                    else:
                        repair_text = _try_text_repair_reply(
                            messages=payload,
                            action_events=action_events,
                            session_id=session_id,
                            volume_id=session.volume_id,
                            filename=runtime_active_filename,
                            model_id=model_id,
                        )
                        if repair_text:
                            response_text = repair_text
                            action_events.append(
                                {
                                    "type": "activity",
                                    "message": "Recovered empty output via text-only repair fallback",
                                }
                            )
                        else:
                            _log_agent_sdk_attempt(
                                component="agent.chat.sync.sdk",
                                status="error",
                                session_id=session_id,
                                volume_id=session.volume_id,
                                filename=runtime_active_filename,
                                model_id=model_id,
                                messages=payload,
                                action_events=action_events,
                                error_detail="Sync retry after empty stream returned no final text",
                                latency_ms=round((time.monotonic() - retry_started_at) * 1000),
                                finish_reason="empty_output",
                                phase="stream_empty_retry_sync",
                            )
                            action_events.append(
                                {
                                    "type": "activity",
                                    "message": "Streaming and sync retry returned empty output; applied deterministic fallback",
                                }
                            )
            active_text_box_count = get_active_page_text_box_count(
                volume_id=session.volume_id,
                current_filename=runtime_active_filename,
            )
            if (
                initial_text_box_count is not None
                and active_text_box_count is not None
                and active_text_box_count != initial_text_box_count
            ):
                action_events.append(
                    {
                        "type": "activity",
                        "message": (
                            "Refreshed active page state after tool calls: "
                            f"text boxes {initial_text_box_count} -> {active_text_box_count}"
                        ),
                    }
                )
            response_text, guard_reason = sanitize_agent_reply_text(
                response_text=response_text,
                messages=payload,
                active_filename=runtime_active_filename,
                active_text_box_count=active_text_box_count,
            )
            if guard_reason == "stale_context":
                action_events.append(
                    {
                        "type": "activity",
                        "message": "Blocked stale page facts; returned grounded reply",
                    }
                )
            elif guard_reason == "empty_output_no_boxes":
                action_events.append(
                    {
                        "type": "activity",
                        "message": "Model returned empty output; returned no-box deterministic reply",
                    }
                )
            elif guard_reason == "empty_output":
                action_events.append(
                    {
                        "type": "activity",
                        "message": "Model returned empty output; returned deterministic fallback",
                    }
                )
            meta: dict[str, object] = {"source": "agent_reply"}
            if action_events:
                meta["actions"] = action_events
            persisted_timeline = _persist_action_event_messages(session_id, action_events)
            message = add_agent_message(
                session_id,
                role="assistant",
                content=response_text,
                meta=meta,
            )
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "type": "done",
                    "message": message,
                    "timelineMessages": persisted_timeline,
                },
            )
            if not primary_stream_used_retry:
                _log_agent_sdk_attempt(
                    component="agent.chat.stream.sdk",
                    status="success",
                    session_id=session_id,
                    volume_id=session.volume_id,
                    filename=runtime_active_filename,
                    model_id=model_id,
                    messages=payload,
                    action_events=action_events,
                    response_text=response_text,
                    latency_ms=round((time.monotonic() - stream_started_at) * 1000),
                    finish_reason="completed",
                    phase="stream_primary",
                )
            logger.info(
                append_correlation(
                    "agent stream done",
                    _corr(),
                    response_chars=len(response_text),
                )
            )
        except Exception as exc:
            error_text = str(exc).strip()
            request_id = (
                str(getattr(exc, "request_id", "") or "").strip()
                or _extract_request_id(error_text)
            )
            provider_server_error = _is_provider_server_error(exc=exc, text=error_text)
            _log_agent_sdk_attempt(
                component="agent.chat.stream.sdk",
                status="error",
                session_id=session_id,
                volume_id=session.volume_id,
                filename=runtime_active_filename,
                model_id=model_id,
                messages=payload,
                action_events=action_events,
                error_detail=error_text,
                request_id=request_id,
                latency_ms=round((time.monotonic() - stream_started_at) * 1000),
                finish_reason="provider_error" if provider_server_error else "exception",
                phase="stream_primary",
            )
            if provider_server_error:
                logger.warning(
                    append_correlation(
                        "agent stream provider server error; attempting sync fallback",
                        _corr(request_id=request_id),
                    )
                )
            else:
                logger.exception(append_correlation("agent stream failed", _corr(request_id=request_id)))
            if request_id:
                log_fn = logger.warning if provider_server_error else logger.error
                log_fn(append_correlation("agent stream provider error", _corr(request_id=request_id)))
            if not stop_event.is_set():
                try:
                    logger.info(append_correlation("agent stream fallback sync", _corr()))
                    fallback_text = ""
                    for attempt in range(2):
                        fallback_attempt_started_at = time.monotonic()
                        try:
                            fallback_text = run_agent_chat(
                                payload,
                                model_id=model_id,
                                volume_id=session.volume_id,
                                current_filename=runtime_active_filename,
                                session_id=session_id,
                            ).strip()
                        except Exception as fallback_attempt_exc:
                            fallback_attempt_text = str(fallback_attempt_exc).strip()
                            fallback_attempt_request_id = (
                                str(getattr(fallback_attempt_exc, "request_id", "") or "").strip()
                                or _extract_request_id(fallback_attempt_text)
                            )
                            if not request_id and fallback_attempt_request_id:
                                request_id = fallback_attempt_request_id
                            _log_agent_sdk_attempt(
                                component="agent.chat.sync.sdk",
                                status="error",
                                session_id=session_id,
                                volume_id=session.volume_id,
                                filename=runtime_active_filename,
                                model_id=model_id,
                                messages=payload,
                                action_events=action_events,
                                error_detail=fallback_attempt_text,
                                request_id=fallback_attempt_request_id,
                                latency_ms=round((time.monotonic() - fallback_attempt_started_at) * 1000),
                                finish_reason=(
                                    "provider_error"
                                    if _is_provider_server_error(
                                        exc=fallback_attempt_exc,
                                        text=fallback_attempt_text,
                                    )
                                    else "exception"
                                ),
                                phase="stream_fallback_sync",
                                attempt=attempt + 1,
                            )
                            if attempt == 0 and _is_provider_server_error(
                                exc=fallback_attempt_exc,
                                text=fallback_attempt_text,
                            ):
                                logger.warning(
                                    append_correlation(
                                        "agent stream fallback sync provider error; retrying once",
                                        _corr(request_id=fallback_attempt_request_id, attempt=attempt + 1),
                                    )
                                )
                                continue
                            raise
                        if fallback_text:
                            _log_agent_sdk_attempt(
                                component="agent.chat.sync.sdk",
                                status="success",
                                session_id=session_id,
                                volume_id=session.volume_id,
                                filename=runtime_active_filename,
                                model_id=model_id,
                                messages=payload,
                                action_events=action_events,
                                response_text=fallback_text,
                                request_id=request_id,
                                latency_ms=round((time.monotonic() - fallback_attempt_started_at) * 1000),
                                finish_reason="completed",
                                phase="stream_fallback_sync",
                                attempt=attempt + 1,
                            )
                            break
                        if attempt == 0:
                            _log_agent_sdk_attempt(
                                component="agent.chat.sync.sdk",
                                status="error",
                                session_id=session_id,
                                volume_id=session.volume_id,
                                filename=runtime_active_filename,
                                model_id=model_id,
                                messages=payload,
                                action_events=action_events,
                                error_detail="Sync fallback attempt completed without final text",
                                request_id=request_id,
                                latency_ms=round((time.monotonic() - fallback_attempt_started_at) * 1000),
                                finish_reason="empty_output",
                                phase="stream_fallback_sync",
                                attempt=attempt + 1,
                            )
                            logger.warning(
                                append_correlation(
                                    "agent stream fallback attempt empty; retrying once",
                                    _corr(attempt=attempt + 1),
                                )
                            )
                    fallback_text_box_count = get_active_page_text_box_count(
                        volume_id=session.volume_id,
                        current_filename=runtime_active_filename,
                    )
                    fallback_text, guard_reason = sanitize_agent_reply_text(
                        response_text=fallback_text,
                        messages=payload,
                        active_filename=runtime_active_filename,
                        active_text_box_count=fallback_text_box_count,
                    )
                    if guard_reason == "empty_output":
                        repair_text = _try_text_repair_reply(
                            messages=payload,
                            action_events=action_events,
                            session_id=session_id,
                            volume_id=session.volume_id,
                            filename=runtime_active_filename,
                            model_id=model_id,
                        )
                        if repair_text:
                            fallback_text, guard_reason = sanitize_agent_reply_text(
                                response_text=repair_text,
                                messages=payload,
                                active_filename=runtime_active_filename,
                                active_text_box_count=fallback_text_box_count,
                            )
                            if guard_reason != "empty_output":
                                action_events.append(
                                    {
                                        "type": "activity",
                                        "message": "Recovered fallback empty output via text-only repair fallback",
                                    }
                                )
                            else:
                                repair_text = ""
                        if not repair_text:
                            _log_agent_sdk_attempt(
                                component="agent.chat.sync.sdk",
                                status="error",
                                session_id=session_id,
                                volume_id=session.volume_id,
                                filename=runtime_active_filename,
                                model_id=model_id,
                                messages=payload,
                                action_events=action_events,
                                error_detail="Sync fallback returned no final text after retries",
                                request_id=request_id,
                                finish_reason="empty_output",
                                phase="stream_fallback_sync",
                            )
                            fallback_text = _provider_error_fallback_reply(
                                request_id=request_id,
                                active_filename=runtime_active_filename,
                            )
                            guard_reason = "provider_error_empty"
                    fallback_actions = list(action_events)
                    if guard_reason == "stale_context":
                        fallback_actions.append(
                            {
                                "type": "activity",
                                "message": "Blocked stale page facts in fallback reply",
                            }
                        )
                    elif guard_reason == "empty_output_no_boxes":
                        fallback_actions.append(
                            {
                                "type": "activity",
                                "message": "Fallback produced empty output; returned no-box deterministic reply",
                            }
                        )
                    elif guard_reason == "empty_output":
                        fallback_actions.append(
                            {
                                "type": "activity",
                                "message": "Fallback produced empty output; returned deterministic reply",
                            }
                        )
                    elif guard_reason == "provider_error_empty":
                        fallback_actions.append(
                            {
                                "type": "activity",
                                "message": (
                                    f"Provider server error ({request_id}); returned deterministic provider fallback"
                                    if request_id
                                    else "Provider server error; returned deterministic provider fallback"
                                ),
                            }
                        )
                    fallback_actions.append(
                        {
                            "type": "activity",
                            "message": (
                                f"Streaming failed ({request_id}), used sync fallback reply"
                                if request_id
                                else "Streaming failed, used sync fallback reply"
                            ),
                        }
                    )
                    fallback_meta: dict[str, object] = {"source": "agent_reply_fallback"}
                    if fallback_actions:
                        fallback_meta["actions"] = fallback_actions[-40:]
                    persisted_timeline = _persist_action_event_messages(session_id, fallback_actions)
                    fallback_message = add_agent_message(
                        session_id,
                        role="assistant",
                        content=fallback_text,
                        meta=fallback_meta,
                    )
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {
                            "type": "done",
                            "message": fallback_message,
                            "timelineMessages": persisted_timeline,
                        },
                    )
                    _log_agent_sdk_attempt(
                        component="agent.chat.sync.sdk",
                        status="error" if guard_reason == "provider_error_empty" else "success",
                        session_id=session_id,
                        volume_id=session.volume_id,
                        filename=runtime_active_filename,
                        model_id=model_id,
                        messages=payload,
                        action_events=fallback_actions,
                        response_text=fallback_text,
                        request_id=request_id,
                        error_detail=(
                            "Provider error fallback reply used because no final text was produced"
                            if guard_reason == "provider_error_empty"
                            else None
                        ),
                        finish_reason="provider_error" if guard_reason == "provider_error_empty" else "completed",
                        phase="stream_fallback_final_reply",
                    )
                    logger.info(
                        append_correlation(
                            "agent stream fallback done",
                            _corr(request_id=request_id),
                            response_chars=len(fallback_text),
                        )
                    )
                    return
                except Exception as fallback_exc:
                    fallback_error_text = str(fallback_exc).strip()
                    fallback_request_id = (
                        str(getattr(fallback_exc, "request_id", "") or "").strip()
                        or _extract_request_id(fallback_error_text)
                    )
                    if _is_provider_server_error(exc=fallback_exc, text=fallback_error_text):
                        final_request_id = fallback_request_id or request_id
                        _log_agent_sdk_attempt(
                            component="agent.chat.sync.sdk",
                            status="error",
                            session_id=session_id,
                            volume_id=session.volume_id,
                            filename=runtime_active_filename,
                            model_id=model_id,
                            messages=payload,
                            action_events=action_events,
                            error_detail=fallback_error_text,
                            request_id=final_request_id,
                            finish_reason="provider_error",
                            phase="stream_fallback_final_reply",
                        )
                        fallback_text = _provider_error_fallback_reply(
                            request_id=final_request_id,
                            active_filename=runtime_active_filename,
                        )
                        fallback_actions = list(action_events)
                        fallback_actions.append(
                            {
                                "type": "activity",
                                "message": (
                                    f"Streaming+fallback hit provider server error ({final_request_id}); returned deterministic provider message"
                                    if final_request_id
                                    else "Streaming+fallback hit provider server error; returned deterministic provider message"
                                ),
                            }
                        )
                        fallback_meta: dict[str, object] = {"source": "agent_reply_fallback"}
                        if fallback_actions:
                            fallback_meta["actions"] = fallback_actions[-40:]
                        persisted_timeline = _persist_action_event_messages(session_id, fallback_actions)
                        fallback_message = add_agent_message(
                            session_id,
                            role="assistant",
                            content=fallback_text,
                            meta=fallback_meta,
                        )
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            {
                                "type": "done",
                                "message": fallback_message,
                                "timelineMessages": persisted_timeline,
                            },
                        )
                        logger.warning(
                            append_correlation(
                                "agent stream fallback provider error; returned deterministic provider fallback",
                                _corr(request_id=final_request_id),
                            )
                        )
                        return
                    logger.exception(append_correlation("agent stream fallback failed", _corr(request_id=fallback_request_id)))
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": error_text},
            )

    task = asyncio.create_task(asyncio.to_thread(run_stream))
    _STREAM_TASKS.add(task)
    task.add_done_callback(_STREAM_TASKS.discard)

    async def event_generator():
        while True:
            if await request.is_disconnected():
                stop_event.set()
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                if task.done() and queue.empty():
                    stream_error = task.exception()
                    if stream_error is not None:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "type": "error",
                                    "message": f"Streaming task ended: {stream_error}",
                                }
                            )
                            + "\n\n"
                        )
                    else:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "type": "error",
                                    "message": "Streaming ended without completion event",
                                }
                            )
                            + "\n\n"
                        )
                    break
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(payload)}\n\n"
            if payload.get("type") in {"done", "error"}:
                break

    headers = {"Cache-Control": "no-cache"}
    headers.update(cors_headers_for_stream(request))
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )
