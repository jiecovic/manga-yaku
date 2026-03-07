# backend-python/mcp_server/tools.py
"""MCP tool registrations for MangaYaku agent runtime."""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.types import Image

from core.usecases.agent.tool_impl import (
    coerce_filename,
    detect_text_boxes_tool,
    get_page_memory_tool,
    get_text_box_detail_tool,
    get_volume_context_tool,
    list_ocr_profiles_tool,
    list_text_boxes_tool,
    list_volume_pages_tool,
    ocr_text_box_tool,
    search_volume_text_boxes_tool,
    set_active_page_tool,
    shift_active_page_tool,
    translate_active_page_tool,
    update_page_memory_tool,
    update_text_box_fields_tool,
    update_volume_context_tool,
)
from core.usecases.box_detection.profiles import list_box_detection_profiles_for_api
from infra.images.image_ops import load_volume_image, resize_for_llm

from .context import get_tool_context_from_request, set_runtime_active_filename


def _parse_json_array_of_objects(raw: str | None, *, field_name: str) -> list[dict[str, Any]] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        raise ValueError(f"{field_name} must be valid JSON array") from None
    if not isinstance(parsed, list):
        raise ValueError(f"{field_name} must be valid JSON array")
    return [item for item in parsed if isinstance(item, dict)]


def _build_text_box_crop_jpeg_bytes(
    *,
    volume_id: str,
    filename: str,
    box: dict[str, Any],
    padding_px: int,
    max_side: int,
) -> bytes:
    image = load_volume_image(volume_id, filename)
    width, height = image.size
    pad = max(0, int(padding_px))
    max_side_value = max(256, min(int(max_side), 1536))

    x = int(float(box.get("x") or 0.0))
    y = int(float(box.get("y") or 0.0))
    w = int(float(box.get("width") or 0.0))
    h = int(float(box.get("height") or 0.0))

    left = max(0, x - pad)
    top = max(0, y - pad)
    right = min(width, x + w + pad)
    bottom = min(height, y + h + pad)
    if right <= left or bottom <= top:
        raise ValueError("Invalid crop bounds for text box")

    crop = image.crop((left, top, right, bottom))
    crop = resize_for_llm(crop, max_side=max_side_value)
    if crop.mode != "RGB":
        crop = crop.convert("RGB")

    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=86)
    return buffer.getvalue()


def register_tools(mcp: FastMCP[Any]) -> None:
    """Register all agent MCP tools with stable names used by the chat prompt."""

    def _resolve_tool_context(ctx: Context | None) -> Any:
        return get_tool_context_from_request(ctx)

    async def _run_in_thread(fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kwargs)

    @mcp.tool(name="get_runtime_context", description="Return active volume/page context for this run")
    def get_runtime_context(ctx: Context) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        return {
            "volume_id": resolved.volume_id,
            "active_filename": resolved.active_filename,
            "agent_run_id": resolved.agent_run_id,
        }

    @mcp.tool(
        name="set_active_page",
        description="Switch active page for subsequent tools in this run",
    )
    async def set_active_page(
        filename: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        result = await _run_in_thread(
            set_active_page_tool,
            volume_id=resolved.volume_id,
            filename=filename,
        )
        if str(result.get("status") or "").strip().lower() == "ok":
            set_runtime_active_filename(resolved.agent_run_id or "", str(result.get("filename") or ""))
            result["active_filename"] = str(result.get("filename") or "").strip() or None
            result["agent_run_id"] = resolved.agent_run_id
        return result

    @mcp.tool(
        name="shift_active_page",
        description="Move active page by relative offset in current volume (next=+1, previous=-1)",
    )
    async def shift_active_page(
        offset: int = 1,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        result = await _run_in_thread(
            shift_active_page_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            offset=offset,
        )
        if str(result.get("status") or "").strip().lower() == "ok":
            set_runtime_active_filename(resolved.agent_run_id or "", str(result.get("filename") or ""))
            result["active_filename"] = str(result.get("filename") or "").strip() or None
            result["agent_run_id"] = resolved.agent_run_id
        return result

    @mcp.tool(name="list_volume_pages", description="List pages available in the current volume")
    async def list_volume_pages(ctx: Context) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(list_volume_pages_tool, resolved.volume_id)

    @mcp.tool(
        name="get_volume_context",
        description="Read persisted story context for the current volume (summary/glossary/etc)",
    )
    async def get_volume_context(ctx: Context) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(get_volume_context_tool, volume_id=resolved.volume_id)

    @mcp.tool(
        name="get_page_memory",
        description="Read persisted memory for the active page, or another page when filename is provided",
    )
    async def get_page_memory(
        filename: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
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
        active_characters_json: str | None = None,
        open_threads: list[str] | None = None,
        glossary_json: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        try:
            active_characters = _parse_json_array_of_objects(
                active_characters_json,
                field_name="active_characters_json",
            )
            glossary = _parse_json_array_of_objects(
                glossary_json,
                field_name="glossary_json",
            )
        except ValueError as exc:
            return {"error": str(exc)}

        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
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
        characters_json: str | None = None,
        open_threads: list[str] | None = None,
        glossary_json: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        try:
            characters = _parse_json_array_of_objects(
                characters_json,
                field_name="characters_json",
            )
            glossary = _parse_json_array_of_objects(
                glossary_json,
                field_name="glossary_json",
            )
        except ValueError as exc:
            return {"error": str(exc)}

        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
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
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
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
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
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
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
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
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
            update_text_box_fields_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            box_id=box_id,
            filename=filename,
            text=text,
            translation=translation,
            note=note,
        )

    @mcp.tool(name="set_text_box_note", description="Set or replace note for one text box on the active page")
    async def set_text_box_note(
        box_id: int,
        note: str,
        filename: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
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
        resolved = _resolve_tool_context(ctx)
        detail = await _run_in_thread(
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

        try:
            jpeg_bytes = await _run_in_thread(
                _build_text_box_crop_jpeg_bytes,
                volume_id=resolved.volume_id,
                filename=str(detail.get("filename") or resolved.active_filename or filename),
                box=box,
                padding_px=padding_px,
                max_side=max_side,
            )
        except Exception as exc:
            return {
                "error": str(exc).strip() or "Failed to prepare text box image crop",
                "volume_id": resolved.volume_id,
                "filename": str(detail.get("filename") or resolved.active_filename or filename),
                "box_id": int(box_id),
            }

        return [
            {
                "status": "ok",
                "volume_id": resolved.volume_id,
                "filename": str(detail.get("filename") or resolved.active_filename or filename),
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

    @mcp.tool(name="list_ocr_profiles", description="List available OCR profiles")
    async def list_ocr_profiles() -> dict[str, Any]:
        return await _run_in_thread(list_ocr_profiles_tool)

    @mcp.tool(name="list_box_detection_profiles", description="List available box detection profiles")
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
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
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
        description="Run text box detection on the active page",
    )
    async def detect_text_boxes(
        filename: str | None = None,
        profile_id: str | None = None,
        replace_existing: bool = True,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
            detect_text_boxes_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            filename=filename,
            profile_id=coerce_filename(profile_id),
            replace_existing=replace_existing,
        )

    @mcp.tool(
        name="translate_active_page",
        description="Run the staged page-translation workflow on the active page; use primitive tools afterward for inspection and box-level corrections",
    )
    async def translate_active_page(
        filename: str | None = None,
        detection_profile_id: str | None = None,
        ocr_profiles: list[str] | None = None,
        source_language: str | None = None,
        target_language: str | None = None,
        model_id: str | None = None,
        force_rerun: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        resolved = _resolve_tool_context(ctx)
        return await _run_in_thread(
            translate_active_page_tool,
            volume_id=resolved.volume_id,
            active_filename=resolved.active_filename,
            filename=filename,
            detection_profile_id=coerce_filename(detection_profile_id),
            ocr_profiles=ocr_profiles,
            source_language=coerce_filename(source_language),
            target_language=coerce_filename(target_language),
            model_id=coerce_filename(model_id),
            force_rerun=force_rerun,
        )
