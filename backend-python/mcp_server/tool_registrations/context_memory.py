# backend-python/mcp_server/tool_registrations/context_memory.py
"""MCP tool registrations for persisted volume and page memory."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tools.context import (
    get_page_memory_tool,
    get_volume_context_tool,
    update_page_memory_tool,
    update_volume_context_tool,
)
from mcp.server.fastmcp import Context, FastMCP

from .common import resolve_tool_context, run_sync_tool


def register_context_memory_tools(mcp: FastMCP[Any]) -> None:
    """Register MCP tools that read or update persisted story context.

    These tools expose the durable memory rows the UI and workflows use:
    volume-level context and page-level memory summaries.
    """

    @mcp.tool(
        name="get_volume_context",
        description="Read persisted story context for the current volume (summary/glossary/etc)",
    )
    async def get_volume_context(ctx: Context) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(get_volume_context_tool, volume_id=resolved.volume_id)

    @mcp.tool(
        name="get_page_memory",
        description="Read persisted memory for the active page, or another page when filename is provided",
    )
    async def get_page_memory(
        filename: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            get_page_memory_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            filename=filename,
        )

    @mcp.tool(
        name="update_volume_context",
        description="Update persisted story context for the current volume",
    )
    async def update_volume_context(
        rolling_summary: str | None = None,
        active_characters: list[dict[str, Any]] | None = None,
        open_threads: list[str] | None = None,
        glossary: list[dict[str, Any]] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            update_volume_context_tool,
            volume_id=resolved.volume_id,
            rolling_summary=rolling_summary,
            active_characters=active_characters,
            open_threads=open_threads,
            glossary=glossary,
        )

    @mcp.tool(
        name="update_page_memory",
        description="Update persisted memory for the active page",
    )
    async def update_page_memory(
        filename: str | None = None,
        manual_notes: str | None = None,
        page_summary: str | None = None,
        image_summary: str | None = None,
        characters: list[dict[str, Any]] | None = None,
        open_threads: list[str] | None = None,
        glossary: list[dict[str, Any]] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            update_page_memory_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            filename=filename,
            manual_notes=manual_notes,
            page_summary=page_summary,
            image_summary=image_summary,
            characters=characters,
            open_threads=open_threads,
            glossary=glossary,
        )
