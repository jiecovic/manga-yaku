# backend-python/mcp_server/http_app.py
"""Standalone ASGI app for MangaYaku MCP Streamable HTTP transport."""

from mcp_server.server import create_server

app = create_server().streamable_http_app()
