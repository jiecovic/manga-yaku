# backend-python/core/usecases/agent/mcp_runtime.py
"""Helpers to run Agents SDK with MCP servers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from config import AGENT_MCP_SERVER_URL
from mcp_server.context import (
    MCP_HEADER_AGENT_RUN_ID,
    clear_runtime_active_filename,
)

logger = logging.getLogger(__name__)

MCP_HEADER_VOLUME_ID = "x-mangayaku-volume-id"
MCP_HEADER_ACTIVE_FILENAME = "x-mangayaku-active-filename"

try:
    from agents.mcp import MCPServerStreamableHttp

    _mcp_import_error: Exception | None = None
except Exception as exc:  # pragma: no cover - optional dependency path
    MCPServerStreamableHttp = None  # type: ignore[assignment]
    _mcp_import_error = exc


def build_agent_mcp_servers(
    *,
    volume_id: str,
    active_filename: str | None,
    agent_run_id: str | None = None,
) -> list[Any]:
    """Build per-run MCP server instances for agent tools."""
    if MCPServerStreamableHttp is None:
        raise RuntimeError(f"Agents MCP runtime is not available: {_mcp_import_error!r}")

    resolved_run_id = str(agent_run_id or "").strip() or uuid4().hex
    headers = {
        MCP_HEADER_VOLUME_ID: str(volume_id or "").strip(),
        MCP_HEADER_ACTIVE_FILENAME: str(active_filename or "").strip(),
        MCP_HEADER_AGENT_RUN_ID: resolved_run_id,
    }

    server = MCPServerStreamableHttp(
        params={
            "url": AGENT_MCP_SERVER_URL,
            "headers": headers,
            "timeout": 90.0,
            "sse_read_timeout": 300.0,
        },
        cache_tools_list=True,
        name="mangayaku-tools",
        client_session_timeout_seconds=90,
    )
    server._mangayaku_agent_run_id = resolved_run_id
    return [server]


async def connect_mcp_servers(
    servers: list[Any],
) -> tuple[list[Any], list[tuple[str, Exception]]]:
    """Connect MCP servers and return (connected, failures)."""
    connected: list[Any] = []
    failures: list[tuple[str, Exception]] = []

    for server in servers:
        name = str(getattr(server, "name", "mcp-server") or "mcp-server")
        try:
            await server.connect()
            connected.append(server)
        except Exception as exc:  # pragma: no cover - network/process path
            failures.append((name, exc))

    return connected, failures


async def cleanup_mcp_servers(servers: list[Any]) -> None:
    """Best-effort MCP server cleanup."""
    for server in reversed(servers):
        name = str(getattr(server, "name", "mcp-server") or "mcp-server")
        run_id = str(getattr(server, "_mangayaku_agent_run_id", "") or "").strip() or None
        try:
            await server.cleanup()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - cleanup path
            logger.warning("failed to cleanup mcp server %s: %s", name, exc)
        finally:
            clear_runtime_active_filename(run_id)
