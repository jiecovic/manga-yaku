# backend-python/core/usecases/agent/tools/jobs.py
"""Public facade for job-backed agent tools."""

from __future__ import annotations

from core.usecases.agent.tools.jobs_detection import detect_text_boxes_tool
from core.usecases.agent.tools.jobs_ocr import (
    list_ocr_profiles_tool,
    ocr_text_box_tool,
)
from core.usecases.agent.tools.jobs_page_translation import translate_active_page_tool

__all__ = [
    "detect_text_boxes_tool",
    "list_ocr_profiles_tool",
    "ocr_text_box_tool",
    "translate_active_page_tool",
]
