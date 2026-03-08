# backend-python/core/usecases/translation/runtime/context.py
"""Context-building helpers for single-box translation."""

from __future__ import annotations

from infra.db.store_context import get_page_context_snapshot, get_volume_context
from infra.db.store_volume_page import load_page


def clip_context(value: str, *, max_chars: int = 420) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3].rstrip()}..."


def build_series_context(volume_id: str) -> str:
    snapshot = get_volume_context(volume_id)
    if not snapshot:
        return ""

    parts: list[str] = []
    rolling_summary = str(snapshot.get("rolling_summary") or "").strip()
    if rolling_summary:
        parts.append(f"story summary: {clip_context(rolling_summary, max_chars=900)}")

    active_characters = snapshot.get("active_characters")
    if isinstance(active_characters, list):
        lines: list[str] = []
        for item in active_characters[:8]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            info = str(item.get("info") or "").strip()
            if not name and not info:
                continue
            if name and info:
                lines.append(f"{name}: {clip_context(info, max_chars=140)}")
            elif name:
                lines.append(name)
            else:
                lines.append(clip_context(info, max_chars=140))
        if lines:
            parts.append("active characters:\n- " + "\n- ".join(lines))

    open_threads = snapshot.get("open_threads")
    if isinstance(open_threads, list):
        lines = [str(item).strip() for item in open_threads if str(item).strip()]
        if lines:
            parts.append(
                "open threads:\n- " + "\n- ".join(clip_context(line) for line in lines[:8])
            )

    glossary = snapshot.get("glossary")
    if isinstance(glossary, list):
        lines: list[str] = []
        for item in glossary[:8]:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term") or "").strip()
            translation = str(item.get("translation") or "").strip()
            note = str(item.get("note") or "").strip()
            if term and translation:
                line = f"{term} => {translation}"
                if note:
                    line += f" ({clip_context(note, max_chars=120)})"
                lines.append(line)
        if lines:
            parts.append("glossary:\n- " + "\n- ".join(lines))

    return "\n\n".join(parts)


def build_page_context(
    volume_id: str,
    filename: str,
    *,
    target_box_id: int,
) -> str:
    parts: list[str] = []
    page_snapshot = get_page_context_snapshot(volume_id, filename)
    if page_snapshot:
        manual_notes = str(page_snapshot.get("manual_notes") or "").strip()
        page_summary = str(page_snapshot.get("page_summary") or "").strip()
        image_summary = str(page_snapshot.get("image_summary") or "").strip()
        if manual_notes:
            parts.append(f"page notes: {clip_context(manual_notes, max_chars=900)}")
        if page_summary:
            parts.append(f"page summary: {clip_context(page_summary, max_chars=900)}")
        if image_summary:
            parts.append(f"image summary: {clip_context(image_summary, max_chars=900)}")

    page = load_page(volume_id, filename)
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    lines: list[str] = []
    if isinstance(raw_boxes, list):
        sorted_boxes = sorted(
            raw_boxes,
            key=lambda box: (
                int(box.get("orderIndex") or box.get("id") or 0),
                int(box.get("id") or 0),
            ),
        )
        for box in sorted_boxes:
            if not isinstance(box, dict):
                continue
            box_id = int(box.get("id") or 0)
            if box_id <= 0 or box_id == target_box_id:
                continue
            if str(box.get("type") or "").strip().lower() != "text":
                continue
            order = int(box.get("orderIndex") or box_id)
            ocr_text = str(box.get("text") or "").strip()
            translation = str(box.get("translation") or "").strip()
            if ocr_text:
                lines.append(f"box #{order} ocr: {clip_context(ocr_text)}")
            if translation:
                lines.append(f"box #{order} translation: {clip_context(translation)}")
            if len(lines) >= 12:
                break
    if lines:
        parts.append("neighbor boxes:\n- " + "\n- ".join(lines))

    return "\n\n".join(parts)
