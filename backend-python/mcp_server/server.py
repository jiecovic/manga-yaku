# backend-python/mcp_server/server.py
"""MangaYaku MCP server entrypoint (stdio transport)."""

from __future__ import annotations

from typing import Any

from infra.prompts import load_prompt_bundle
from mcp.server.fastmcp import FastMCP

from .tools import register_tools


def _load_server_instructions() -> str:
    return load_prompt_bundle("mcp/server.yml")["system"]


def create_server() -> FastMCP[Any]:
    mcp = FastMCP(
        name="mangayaku-tools",
        instructions=_load_server_instructions(),
        streamable_http_path="/",
    )
    register_tools(mcp)
    return mcp


def main() -> None:
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
