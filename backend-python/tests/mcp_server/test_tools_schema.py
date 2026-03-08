# backend-python/tests/mcp_server/test_tools_schema.py
"""Regression tests for MCP tool parameter schemas."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp_server.tools import register_tools


def _tool_parameters(tool_name: str) -> dict:
    server = FastMCP("test-server")
    register_tools(server)
    tool = server._tool_manager._tools[tool_name]
    return tool.parameters


def test_update_page_memory_uses_structured_arrays() -> None:
    params = _tool_parameters("update_page_memory")
    properties = params["properties"]

    assert "characters" in properties
    assert "glossary" in properties
    assert "characters_json" not in properties
    assert "glossary_json" not in properties
    assert properties["characters"]["anyOf"][0]["type"] == "array"
    assert properties["glossary"]["anyOf"][0]["type"] == "array"


def test_update_volume_context_uses_structured_arrays() -> None:
    params = _tool_parameters("update_volume_context")
    properties = params["properties"]

    assert "active_characters" in properties
    assert "glossary" in properties
    assert "active_characters_json" not in properties
    assert "glossary_json" not in properties
    assert properties["active_characters"]["anyOf"][0]["type"] == "array"
    assert properties["glossary"]["anyOf"][0]["type"] == "array"


def test_detection_and_page_translation_tools_expose_safe_defaults() -> None:
    detection_params = _tool_parameters("detect_text_boxes")
    detection_properties = detection_params["properties"]
    assert detection_properties["replace_existing"]["default"] is False

    translate_params = _tool_parameters("translate_active_page")
    translate_properties = translate_params["properties"]
    assert translate_properties["preserve_existing_boxes"]["default"] is True
