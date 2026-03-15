# backend-python/mcp_server/tool_registrations/boxes.py
"""MCP tool registrations for box inspection, search, and editing."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tools.boxes import (
    get_text_box_detail_tool,
    list_text_boxes_tool,
    search_volume_text_boxes_tool,
    update_text_box_fields_tool,
)
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.types import Image

from .common import build_text_box_crop_jpeg_bytes, resolve_tool_context, run_sync_tool


def register_box_tools(mcp: FastMCP[Any]) -> None:
    """Register MCP tools that inspect or mutate text boxes.

    This group covers search, listing, box detail lookup, direct field updates,
    and the image-crop helper used when the agent wants to visually inspect a
    single box before OCR or translation.
    """

    @mcp.tool(
        name="search_volume_text_boxes",
        description="Search OCR/translation text across all pages in the current volume",
    )
    async def search_volume_text_boxes(
        query: str,
        limit: int = 40,
        only_translated: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            search_volume_text_boxes_tool,
            volume_id=resolved.volume_id,
            query=query,
            limit=limit,
            only_translated=only_translated,
        )

    @mcp.tool(
        name="list_text_boxes",
        description="List text boxes for the active page, or another page when filename is provided",
    )
    async def list_text_boxes(
        filename: str | None = None,
        limit: int = 300,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            list_text_boxes_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            filename=filename,
            limit=limit,
        )

    @mcp.tool(
        name="get_text_box_detail",
        description="Get one text box by numeric ID on the active page, or another page when filename is provided",
    )
    async def get_text_box_detail(
        box_id: int,
        filename: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            get_text_box_detail_tool,
            volume_id=resolved.volume_id,
            box_id=box_id,
            active_filename=resolved.active_filename,
            filename=filename,
        )

    @mcp.tool(
        name="update_text_box_fields",
        description="Update OCR text and/or translation for one box on the active page",
    )
    async def update_text_box_fields(
        box_id: int,
        filename: str | None = None,
        text: str | None = None,
        translation: str | None = None,
        note: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            update_text_box_fields_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            box_id=box_id,
            filename=filename,
            text=text,
            translation=translation,
            note=note,
        )

    @mcp.tool(
        name="set_text_box_note",
        description="Set or replace note for one text box on the active page",
    )
    async def set_text_box_note(
        box_id: int,
        note: str,
        filename: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = resolve_tool_context(ctx)
        return await run_sync_tool(
            update_text_box_fields_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            box_id=box_id,
            filename=filename,
            note=note,
        )

    @mcp.tool(
        name="view_text_box",
        description=(
            "Return a cropped image for one text box (plus box metadata) so OCR/translation can be visually verified"
        ),
    )
    async def view_text_box(
        box_id: int,
        filename: str | None = None,
        padding_px: int = 8,
        max_side: int = 1024,
        ctx: Context | None = None,
    ) -> Any:
        resolved = resolve_tool_context(ctx)
        detail = await run_sync_tool(
            get_text_box_detail_tool,
            volume_id=resolved.volume_id,
            box_id=box_id,
            active_filename=resolved.active_filename,
            filename=filename,
        )
        if "error" in detail:
            return detail

        box = detail.get("box") if isinstance(detail.get("box"), dict) else None
        if not isinstance(box, dict):
            return {"error": "Text box payload missing in detail result"}

        result_filename = str(detail.get("filename") or resolved.active_filename or filename)
        try:
            jpeg_bytes = await run_sync_tool(
                build_text_box_crop_jpeg_bytes,
                volume_id=resolved.volume_id,
                filename=result_filename,
                box=box,
                padding_px=padding_px,
                max_side=max_side,
            )
        except Exception as exc:
            return {
                "error": str(exc).strip() or "Failed to prepare text box image crop",
                "volume_id": resolved.volume_id,
                "filename": result_filename,
                "box_id": int(box_id),
            }

        return [
            {
                "status": "ok",
                "volume_id": resolved.volume_id,
                "filename": result_filename,
                "box_id": int(box_id),
                "bbox": {
                    "x": float(box.get("x") or 0.0),
                    "y": float(box.get("y") or 0.0),
                    "width": float(box.get("width") or 0.0),
                    "height": float(box.get("height") or 0.0),
                },
                "text": str(box.get("text") or ""),
                "translation": str(box.get("translation") or ""),
                "note": str(box.get("note") or ""),
                "padding_px": max(0, int(padding_px)),
            },
            Image(data=jpeg_bytes, format="jpeg"),
        ]
