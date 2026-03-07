# backend-python/api/routers/agent/reply_routes.py
"""Reply-producing routes for the agent UI."""

from __future__ import annotations

from api.schemas.agent_chat import AgentMessagePublic, AgentReplyRequest
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from .reply_stream import build_stream_agent_reply_response
from .reply_sync import create_agent_reply_message

router = APIRouter(tags=["agent"])


@router.post(
    "/agent/sessions/{session_id}/reply",
    response_model=AgentMessagePublic,
)
async def create_agent_reply(
    session_id: str,
    req: AgentReplyRequest,
) -> AgentMessagePublic:
    """Create agent reply."""
    return await create_agent_reply_message(session_id, req)


@router.get("/agent/sessions/{session_id}/reply/stream")
async def stream_agent_reply(
    session_id: str,
    request: Request,
    max_messages: int = Query(20, alias="maxMessages"),
    current_filename: str | None = Query(None, alias="currentFilename"),
) -> StreamingResponse:
    """Stream agent reply."""
    return await build_stream_agent_reply_response(
        session_id,
        request,
        max_messages=max_messages,
        current_filename=current_filename,
    )
