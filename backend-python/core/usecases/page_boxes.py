# backend-python/core/usecases/page_boxes.py
"""Shared helpers for reading text boxes from page payloads."""

from __future__ import annotations

from typing import Any


def list_text_boxes(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Return page text boxes in stable UI/workflow order."""
    raw_boxes = page.get("boxes", []) if isinstance(page, dict) else []
    if not isinstance(raw_boxes, list):
        return []

    text_boxes = [
        box
        for box in raw_boxes
        if isinstance(box, dict) and str(box.get("type") or "").strip().lower() == "text"
    ]
    text_boxes.sort(
        key=lambda box: (
            int(box.get("orderIndex") or 10**9),
            int(box.get("id") or 0),
        )
    )
    return text_boxes
