# backend-python/core/usecases/agent/tool_impl.py
"""Compatibility facade for agent tool helpers."""

from __future__ import annotations

from core.usecases.agent.tool_boxes import (
    get_text_box_detail_tool,
    list_text_boxes_tool,
    update_text_box_fields_tool,
)
from core.usecases.agent.tool_context import (
    get_page_memory_tool,
    get_volume_context_tool,
    search_volume_text_boxes_tool,
    update_page_memory_tool,
    update_volume_context_tool,
)
from core.usecases.agent.tool_jobs import (
    detect_text_boxes_tool,
    list_ocr_profiles_tool,
    ocr_text_box_tool,
    translate_active_page_tool,
)
from core.usecases.agent.tool_pages import (
    list_volume_pages_tool,
    set_active_page_tool,
    shift_active_page_tool,
)
from core.usecases.agent.tool_shared import (
    coerce_filename,
    find_text_box_by_id,
    list_text_boxes_for_page,
)

__all__ = [
    "coerce_filename",
    "detect_text_boxes_tool",
    "find_text_box_by_id",
    "get_page_memory_tool",
    "get_text_box_detail_tool",
    "get_volume_context_tool",
    "list_ocr_profiles_tool",
    "list_text_boxes_for_page",
    "list_text_boxes_tool",
    "list_volume_pages_tool",
    "ocr_text_box_tool",
    "search_volume_text_boxes_tool",
    "set_active_page_tool",
    "shift_active_page_tool",
    "translate_active_page_tool",
    "update_page_memory_tool",
    "update_text_box_fields_tool",
    "update_volume_context_tool",
]
