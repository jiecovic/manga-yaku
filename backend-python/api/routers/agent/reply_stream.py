# backend-python/api/routers/agent/reply_stream.py
"""Streaming agent reply transport helpers."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from config import AGENT_MODEL, AGENT_MODELS
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from infra.db.agent_store import get_agent_session, list_agent_messages
from infra.http import cors_headers_for_stream

from .helpers import build_prompt_payload
from .reply_stream_worker import StreamReplyWorker

_STREAM_TASKS: set[asyncio.Task] = set()


async def build_stream_agent_reply_response(
    session_id: str,
    request: Request,
    *,
    max_messages: int,
    current_filename: str | None,
) -> StreamingResponse:
    """Build a streaming SSE response for an agent reply."""
    session = get_agent_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    limit = max(1, min(100, int(max_messages)))
    history = list_agent_messages(session_id, limit=limit)
    payload = build_prompt_payload(history)
    model_id = session.model_id or AGENT_MODEL
    if model_id not in AGENT_MODELS and AGENT_MODELS:
        model_id = AGENT_MODELS[0]

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    stop_event = threading.Event()
    loop = asyncio.get_running_loop()
    worker = StreamReplyWorker(
        session_id=session_id,
        volume_id=session.volume_id,
        model_id=model_id,
        payload=payload,
        current_filename=current_filename,
        queue=queue,
        loop=loop,
        stop_event=stop_event,
    )

    task = asyncio.create_task(asyncio.to_thread(worker.run))
    _STREAM_TASKS.add(task)
    task.add_done_callback(_STREAM_TASKS.discard)

    async def event_generator():
        while True:
            if await request.is_disconnected():
                stop_event.set()
                break
            try:
                queued_payload = await asyncio.wait_for(queue.get(), timeout=15.0)
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
            yield f"data: {json.dumps(queued_payload)}\n\n"
            if queued_payload.get("type") in {"done", "error"}:
                break

    headers = {"Cache-Control": "no-cache"}
    headers.update(cors_headers_for_stream(request))
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )
