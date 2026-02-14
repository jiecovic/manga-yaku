# backend-python/api/routers/agent.py
from __future__ import annotations

import asyncio
import json
import threading

from api.schemas.agent import (
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
from core.usecases.agent.engine import run_agent_chat, run_agent_chat_stream
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from infra.db.agent_store import (
    add_agent_message,
    create_agent_session,
    delete_agent_session,
    get_agent_session,
    list_agent_messages,
    list_agent_sessions,
    update_agent_session,
)
from infra.http import cors_headers_for_stream

router = APIRouter(tags=["agent"])

_STREAM_TASKS: set[asyncio.Task] = set()
# Keep background stream tasks alive until completion.


@router.get("/agent/config", response_model=AgentConfigResponse)
async def get_agent_config() -> AgentConfigResponse:
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
    return list_agent_sessions(volume_id)


@router.post("/agent/sessions", response_model=AgentSessionPublic)
async def create_session(
    req: CreateAgentSessionRequest,
) -> AgentSessionPublic:
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
    session = get_agent_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    max_messages = max(1, min(100, int(req.maxMessages)))
    history = list_agent_messages(session_id, limit=max_messages)
    payload = [
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("content")
    ]
    model_id = session.model_id or AGENT_MODEL
    if model_id not in AGENT_MODELS and AGENT_MODELS:
        model_id = AGENT_MODELS[0]
    response_text = run_agent_chat(payload, model_id=model_id)

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
) -> StreamingResponse:
    session = get_agent_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    limit = max(1, min(100, int(max_messages)))
    history = list_agent_messages(session_id, limit=limit)
    payload = [
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("content")
    ]
    model_id = session.model_id or AGENT_MODEL
    if model_id not in AGENT_MODELS and AGENT_MODELS:
        model_id = AGENT_MODELS[0]

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    stop_event = threading.Event()
    loop = asyncio.get_running_loop()

    def run_stream() -> None:
        text_chunks: list[str] = []
        try:
            for delta in run_agent_chat_stream(
                payload,
                model_id=model_id,
                stop_event=stop_event,
            ):
                text_chunks.append(delta)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "delta", "delta": delta},
                )
            if stop_event.is_set():
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "canceled"},
                )
                return
            response_text = "".join(text_chunks).strip()
            message = add_agent_message(
                session_id,
                role="assistant",
                content=response_text,
                meta={"source": "agent_reply"},
            )
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "done", "message": message},
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": str(exc)},
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
