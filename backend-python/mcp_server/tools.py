# backend-python/mcp_server/tools.py
"""Stable MCP tool entrypoint for the chat-agent tool surface.

The actual tool registrations are grouped by concern under
`mcp_server.tool_registrations`. This module keeps the single public
`register_tools()` entrypoint used by the backend app and the MCP schema tests.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .tool_registrations.boxes import register_box_tools
from .tool_registrations.context_memory import register_context_memory_tools
from .tool_registrations.operations import register_operation_tools
from .tool_registrations.runtime import register_runtime_tools


def register_tools(mcp: FastMCP[Any]) -> None:
    """Register the full MCP tool surface in stable concern-based groups."""
    register_runtime_tools(mcp)
    register_context_memory_tools(mcp)
    register_box_tools(mcp)
    register_operation_tools(mcp)
