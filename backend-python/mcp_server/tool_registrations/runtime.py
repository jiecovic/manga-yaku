# backend-python/mcp_server/tool_registrations/runtime.py
"""MCP tool registrations for run context and page navigation."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tools.pages import (
    list_volume_pages_tool,
    set_active_page_tool,
    shift_active_page_tool,
)
from mcp.server.fastmcp import Context, FastMCP

from .common import apply_active_filename_result, resolve_tool_context, run_sync_tool


def register_runtime_tools(mcp: FastMCP[Any]) -> None:
    """Register MCP tools that manage run-scoped page context.

    These tools are the navigation layer for the chat agent. They let one run
    inspect the current volume/page context and move the active page forward,
    backward, or to an explicit filename.
    """

    @mcp.tool(
        name="get_runtime_context", description="Return active volume/page context for this run"
    )
    def get_runtime_context(ctx: Context) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return {
            "volume_id": resolved.volume_id,
            "active_filename": resolved.active_filename,
            "agent_run_id": resolved.agent_run_id,
        }

    @mcp.tool(
        name="set_active_page",
        description="Switch active page for subsequent tools in this run",
    )
    async def set_active_page(
        filename: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        result = await run_sync_tool(
            set_active_page_tool,
            volume_id=resolved.volume_id,
            filename=filename,
        )
        return apply_active_filename_result(
            result=result,
            agent_run_id=resolved.agent_run_id,
        )

    @mcp.tool(
        name="shift_active_page",
        description="Move active page by relative offset in current volume (next=+1, previous=-1)",
    )
    async def shift_active_page(
        offset: int = 1,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        result = await run_sync_tool(
            shift_active_page_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            offset=offset,
        )
        return apply_active_filename_result(
            result=result,
            agent_run_id=resolved.agent_run_id,
        )

    @mcp.tool(name="list_volume_pages", description="List pages available in the current volume")
    async def list_volume_pages(ctx: Context) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(list_volume_pages_tool, resolved.volume_id)
