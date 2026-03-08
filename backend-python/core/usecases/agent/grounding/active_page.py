# backend-python/core/usecases/agent/grounding/active_page.py
"""Active-page snapshot and revision helpers for agent grounding."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from infra.db.store_volume_page import load_page
from infra.images.image_ops import get_page_image_path


@dataclass(frozen=True)
class PageStateSnapshot:
    """Normalized page facts used by agent grounding and idempotency checks."""

    filename: str | None
    text_box_count: int | None
    page_revision: str | None


def _coerce_filename(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _count_text_boxes(page: dict[str, Any]) -> int:
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    if not isinstance(raw_boxes, list):
        return 0
    count = 0
    for box in raw_boxes:
        if not isinstance(box, dict):
            continue
        if str(box.get("type") or "").strip().lower() != "text":
            continue
        if int(box.get("id") or 0) <= 0:
            continue
        count += 1
    return count


def _normalize_box_for_revision(box: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(box.get("id") or 0),
        "type": str(box.get("type") or "").strip().lower(),
        "order_index": int(box.get("orderIndex") or 0),
        "x": round(float(box.get("x") or 0.0), 3),
        "y": round(float(box.get("y") or 0.0), 3),
        "width": round(float(box.get("width") or 0.0), 3),
        "height": round(float(box.get("height") or 0.0), 3),
        "text": str(box.get("text") or "").strip(),
        "translation": str(box.get("translation") or "").strip(),
    }


def _compute_page_revision(
    *,
    volume_id: str,
    filename: str,
    page: dict[str, Any],
) -> str:
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    boxes: list[dict[str, Any]] = []
    if isinstance(raw_boxes, list):
        for item in raw_boxes:
            if isinstance(item, dict):
                boxes.append(_normalize_box_for_revision(item))
    boxes.sort(key=lambda row: (row["order_index"], row["id"]))

    payload: dict[str, Any] = {
        "volume_id": volume_id,
        "filename": filename,
        "boxes": boxes,
    }

    try:
        image_path = get_page_image_path(volume_id, filename)
        stat = image_path.stat()
        payload["image_mtime_ns"] = int(stat.st_mtime_ns)
        payload["image_size"] = int(stat.st_size)
    except Exception:
        pass

    normalized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def build_page_state_snapshot(
    *,
    volume_id: str,
    filename: str | None,
    page: dict[str, Any] | None,
) -> PageStateSnapshot:
    """Build a normalized page snapshot from an already-loaded page record."""
    resolved = _coerce_filename(filename)
    if not volume_id or not resolved or not isinstance(page, dict):
        return PageStateSnapshot(
            filename=resolved,
            text_box_count=None,
            page_revision=None,
        )
    return PageStateSnapshot(
        filename=resolved,
        text_box_count=_count_text_boxes(page),
        page_revision=_compute_page_revision(
            volume_id=volume_id,
            filename=resolved,
            page=page,
        ),
    )


def get_active_page_snapshot(
    *,
    volume_id: str,
    current_filename: str | None,
) -> PageStateSnapshot:
    """Load the active page once and return the normalized page snapshot."""
    resolved = _coerce_filename(current_filename)
    if not volume_id or not resolved:
        return PageStateSnapshot(
            filename=resolved,
            text_box_count=None,
            page_revision=None,
        )
    try:
        page = load_page(volume_id, resolved)
    except Exception:
        return PageStateSnapshot(
            filename=resolved,
            text_box_count=None,
            page_revision=None,
        )
    return build_page_state_snapshot(
        volume_id=volume_id,
        filename=current_filename,
        page=page,
    )


def get_active_page_state(
    *,
    volume_id: str,
    current_filename: str | None,
) -> tuple[int | None, str | None]:
    snapshot = get_active_page_snapshot(
        volume_id=volume_id,
        current_filename=current_filename,
    )
    return snapshot.text_box_count, snapshot.page_revision


def get_active_page_text_box_count(
    *,
    volume_id: str,
    current_filename: str | None,
) -> int | None:
    snapshot = get_active_page_snapshot(
        volume_id=volume_id,
        current_filename=current_filename,
    )
    return snapshot.text_box_count


def get_active_page_revision(
    *,
    volume_id: str,
    current_filename: str | None,
) -> str | None:
    snapshot = get_active_page_snapshot(
        volume_id=volume_id,
        current_filename=current_filename,
    )
    return snapshot.page_revision


def build_turn_state_message(
    *,
    volume_id: str,
    active_filename: str | None,
    text_box_count: int | None,
    page_revision: str | None = None,
) -> dict[str, Any]:
    filename_value = _coerce_filename(active_filename) or "none"
    box_count_value = "unknown" if text_box_count is None else str(int(text_box_count))
    revision_value = str(page_revision or "").strip() or "unknown"
    lines = [
        "Authoritative turn state (must not be contradicted):",
        f"- active_volume_id: {volume_id or 'none'}",
        f"- active_filename: {filename_value}",
        f"- active_text_box_count: {box_count_value}",
        f"- active_page_revision: {revision_value}",
        "Use this turn state for any page-specific claims.",
        "For page-specific writes, mutate only the current active_filename.",
        "After any mutating tool call, re-read tool state before claiming completion.",
    ]
    return {
        "role": "system",
        "content": [{"type": "input_text", "text": "\n".join(lines)}],
    }
