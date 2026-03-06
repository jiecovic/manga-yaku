# backend-python/mcp_server/context.py
"""Runtime context resolution for MCP tool calls."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any

from core.usecases.agent.tool_impl import coerce_filename

MCP_ENV_VOLUME_ID = "MANGAYAKU_AGENT_VOLUME_ID"
MCP_ENV_ACTIVE_FILENAME = "MANGAYAKU_AGENT_ACTIVE_FILENAME"
MCP_HEADER_VOLUME_ID = "x-mangayaku-volume-id"
MCP_HEADER_ACTIVE_FILENAME = "x-mangayaku-active-filename"
MCP_HEADER_AGENT_RUN_ID = "x-mangayaku-agent-run-id"

_ACTIVE_FILENAME_BY_RUN_ID: dict[str, str] = {}
_ACTIVE_FILENAME_LOCK = threading.Lock()


@dataclass(frozen=True)
class McpToolContext:
    volume_id: str
    active_filename: str | None
    agent_run_id: str | None


def set_runtime_active_filename(agent_run_id: str, filename: str | None) -> None:
    run_id = str(agent_run_id or "").strip()
    if not run_id:
        return

    resolved_filename = coerce_filename(filename)
    with _ACTIVE_FILENAME_LOCK:
        if resolved_filename:
            _ACTIVE_FILENAME_BY_RUN_ID[run_id] = resolved_filename
        else:
            _ACTIVE_FILENAME_BY_RUN_ID.pop(run_id, None)


def get_runtime_active_filename(agent_run_id: str | None) -> str | None:
    run_id = str(agent_run_id or "").strip()
    if not run_id:
        return None
    with _ACTIVE_FILENAME_LOCK:
        return _ACTIVE_FILENAME_BY_RUN_ID.get(run_id)


def clear_runtime_active_filename(agent_run_id: str | None) -> None:
    run_id = str(agent_run_id or "").strip()
    if not run_id:
        return
    with _ACTIVE_FILENAME_LOCK:
        _ACTIVE_FILENAME_BY_RUN_ID.pop(run_id, None)


def get_tool_context() -> McpToolContext:
    volume_id = str(os.getenv(MCP_ENV_VOLUME_ID, "") or "").strip()
    active_filename = coerce_filename(os.getenv(MCP_ENV_ACTIVE_FILENAME))
    return McpToolContext(
        volume_id=volume_id,
        active_filename=active_filename,
        agent_run_id=None,
    )


def get_tool_context_from_request(ctx: Any | None) -> McpToolContext:
    """Resolve context from MCP request headers, falling back to process env."""
    request_context = getattr(ctx, "request_context", None)
    request = getattr(request_context, "request", None)
    headers = getattr(request, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        volume_id = str(headers.get(MCP_HEADER_VOLUME_ID) or "").strip()
        requested_active_filename = coerce_filename(headers.get(MCP_HEADER_ACTIVE_FILENAME))
        agent_run_id = str(headers.get(MCP_HEADER_AGENT_RUN_ID) or "").strip() or None
        runtime_active_filename = get_runtime_active_filename(agent_run_id)
        active_filename = runtime_active_filename or requested_active_filename
        if volume_id or active_filename:
            return McpToolContext(
                volume_id=volume_id,
                active_filename=active_filename,
                agent_run_id=agent_run_id,
            )
    return get_tool_context()
