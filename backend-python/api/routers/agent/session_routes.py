# backend-python/api/routers/agent/session_routes.py
"""Session and message CRUD routes for the agent UI."""

from __future__ import annotations

from api.schemas.agent_chat import (
    AgentConfigResponse,
    AgentMessagePublic,
    AgentModelPublic,
    AgentSessionPublic,
    CreateAgentMessageRequest,
    CreateAgentSessionRequest,
    UpdateAgentSessionRequest,
)
from config import AGENT_MAX_MESSAGE_CHARS, AGENT_MODEL, AGENT_MODELS
from fastapi import APIRouter, HTTPException, Query
from infra.db.agent_store import (
    add_agent_message,
    create_agent_session,
    delete_agent_session,
    get_agent_session,
    list_agent_messages,
    list_agent_sessions,
    update_agent_session,
)

router = APIRouter(tags=["agent"])


@router.get("/agent/config", response_model=AgentConfigResponse)
async def get_agent_config() -> AgentConfigResponse:
    """Return agent config."""
    models = [AgentModelPublic(id=model_id, label=model_id) for model_id in AGENT_MODELS]
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
