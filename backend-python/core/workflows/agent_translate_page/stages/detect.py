"""Workflow stage handler for agent translate page: detect."""

from __future__ import annotations

import asyncio
from typing import Any

from core.usecases.box_detection.engine import detect_text_boxes_for_page
from infra.db.db_store import load_page

from ..helpers import list_text_boxes


async def run_detect_stage(
    *,
    volume_id: str,
    filename: str,
    detection_profile_id: str | None,
) -> list[dict[str, Any]]:
    """Run detect stage."""
    await asyncio.to_thread(
        detect_text_boxes_for_page,
        volume_id,
        filename,
        detection_profile_id,
        replace_existing=True,
    )
    page = load_page(volume_id, filename)
    return list_text_boxes(page)
