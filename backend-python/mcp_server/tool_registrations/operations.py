# backend-python/mcp_server/tool_registrations/operations.py
"""MCP tool registrations for OCR, detection, and page-translation workflows."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tools import (
    detect_text_boxes_tool,
    list_ocr_profiles_tool,
    ocr_text_box_tool,
    translate_active_page_tool,
)
from core.usecases.agent.tools.shared import coerce_filename
from core.usecases.box_detection.profiles.registry import list_box_detection_profiles_for_api
from mcp.server.fastmcp import Context, FastMCP

from .common import resolve_tool_context, run_sync_tool


def register_operation_tools(mcp: FastMCP[Any]) -> None:
    """Register MCP tools that launch or inspect larger OCR/translation actions.

    These tools are the bridge from the chat agent into persisted OCR,
    detection, and page-translation operations.
    """

    @mcp.tool(name="list_ocr_profiles", description="List available OCR profiles")
    async def list_ocr_profiles() -> dict[str, Any]:
        return await run_sync_tool(list_ocr_profiles_tool)

    @mcp.tool(
        name="list_box_detection_profiles", description="List available box detection profiles"
    )
    async def list_box_detection_profiles() -> dict[str, Any]:
        profiles_raw = list_box_detection_profiles_for_api()
        profiles = [
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or item.get("id") or ""),
                "enabled": bool(item.get("enabled", False)),
                "provider": str(item.get("provider") or ""),
            }
            for item in profiles_raw
            if str(item.get("id") or "").strip()
        ]
        return {"total": len(profiles), "profiles": profiles}

    @mcp.tool(
        name="ocr_text_box",
        description="Run OCR for one text box on the active page; skips boxes that already have text unless force_rerun=true",
    )
    async def ocr_text_box(
        box_id: int,
        filename: str | None = None,
        profile_id: str | None = None,
        force_rerun: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            ocr_text_box_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            box_id=box_id,
            filename=filename,
            profile_id=profile_id,
            force_rerun=force_rerun,
        )

    @mcp.tool(
        name="detect_text_boxes",
        description=(
            "Run text box detection on the active page. By default replace_existing=false "
            "preserves current boxes and only adds non-overlapping new detections; set "
            "replace_existing=true only when you explicitly want to rebuild page boxes "
            "from scratch."
        ),
    )
    async def detect_text_boxes(
        filename: str | None = None,
        profile_id: str | None = None,
        replace_existing: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            detect_text_boxes_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            filename=filename,
            profile_id=coerce_filename(profile_id),
            replace_existing=replace_existing,
        )

    @mcp.tool(
        name="translate_active_page",
        description=(
            "Run the staged page-translation workflow on the active page. By default it "
            "preserves existing boxes and only adds non-overlapping new detections before "
            "OCR/translation; set preserve_existing_boxes=false only for an explicit full "
            "rebuild. Use primitive tools afterward for inspection and box-level corrections."
        ),
    )
    async def translate_active_page(
        filename: str | None = None,
        detection_profile_id: str | None = None,
        preserve_existing_boxes: bool = True,
        ocr_profiles: list[str] | None = None,
        source_language: str | None = None,
        target_language: str | None = None,
        model_id: str | None = None,
        force_rerun: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            translate_active_page_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            filename=filename,
            detection_profile_id=coerce_filename(detection_profile_id),
            preserve_existing_boxes=preserve_existing_boxes,
            ocr_profiles=ocr_profiles,
            source_language=coerce_filename(source_language),
            target_language=coerce_filename(target_language),
            model_id=coerce_filename(model_id),
            force_rerun=force_rerun,
        )
