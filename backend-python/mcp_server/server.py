# backend-python/mcp_server/server.py
"""MangaYaku MCP server entrypoint (stdio transport)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .tools import register_tools


def create_server() -> FastMCP[Any]:
    mcp = FastMCP(
        name="mangayaku-tools",
        instructions=(
            "Tools for MangaYaku volume/page grounding, page switching, text box detection, OCR, visual box inspection, and OCR/translation/note updates."
        ),
        streamable_http_path="/",
    )
    register_tools(mcp)
    return mcp


def main() -> None:
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
