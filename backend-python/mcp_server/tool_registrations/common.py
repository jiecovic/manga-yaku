# backend-python/mcp_server/tool_registrations/common.py
"""Shared helpers used across MCP tool registration groups."""

from __future__ import annotations

import asyncio
import io
from typing import Any

from infra.images.image_ops import load_volume_image, resize_for_llm
from mcp.server.fastmcp import Context

from ..context import McpToolContext, get_tool_context_from_request, set_runtime_active_filename


def resolve_tool_context(ctx: Context | None) -> McpToolContext:
    """Resolve volume/page/run context for a single MCP tool call."""
    return get_tool_context_from_request(ctx)


async def run_sync_tool(fn: Any, /, *args: Any, **kwargs: Any) -> Any:
    """Run sync tool adapters in a worker thread to avoid blocking the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def apply_active_filename_result(
    *,
    result: dict[str, Any],
    agent_run_id: str | None,
) -> dict[str, Any]:
    """Persist and mirror the new active page after a successful navigation tool.

    Page-navigation tools return the selected filename. We write it into the
    run-scoped MCP context cache so later tool calls in the same agent run can
    omit the filename and still target the new active page.
    """
    if str(result.get("status") or "").strip().lower() != "ok":
        return result

    resolved_filename = str(result.get("filename") or "").strip()
    set_runtime_active_filename(agent_run_id or "", resolved_filename)
    result["active_filename"] = resolved_filename or None
    result["agent_run_id"] = agent_run_id
    return result


def build_text_box_crop_jpeg_bytes(
    *,
    volume_id: str,
    filename: str,
    box: dict[str, Any],
    padding_px: int,
    max_side: int,
) -> bytes:
    """Build a bounded JPEG crop for one text box image payload.

    MCP tool calls can return images, but we keep crops small and padded so the
    agent gets readable local context without shipping the whole page image each
    time.
    """
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
