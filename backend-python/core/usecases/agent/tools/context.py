# backend-python/core/usecases/agent/tools/context.py
"""Volume-level context helpers for agent tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.usecases.agent.tools.shared import (
    list_text_boxes_for_page,
    resolve_active_page_filename,
    resolve_read_page_filename,
)
from infra.db.store_context import (
    get_page_context_snapshot,
    get_volume_context,
    upsert_page_context,
    upsert_volume_context,
)
from infra.db.store_volume_page import (
    list_page_filenames,
    load_page,
)


def _to_iso(value: datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _normalize_character_entries(value: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        gender = str(item.get("gender") or "").strip()
        info = str(item.get("info") or "").strip()
        if not name and not gender and not info:
            continue
        out.append({"name": name, "gender": gender, "info": info})
    return out


def _normalize_glossary_entries(value: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        translation = str(item.get("translation") or "").strip()
        note = str(item.get("note") or "").strip()
        if not term or not translation:
            continue
        out.append({"term": term, "translation": translation, "note": note})
    return out


def _normalize_open_threads(value: list[str] | None) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def get_volume_context_tool(*, volume_id: str) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}
    snapshot = get_volume_context(volume_id) or {}
    return {
        "volume_id": volume_id,
        "rolling_summary": str(snapshot.get("rolling_summary") or "").strip(),
        "active_characters": _normalize_character_entries(snapshot.get("active_characters")),
        "open_threads": _normalize_open_threads(snapshot.get("open_threads")),
        "glossary": _normalize_glossary_entries(snapshot.get("glossary")),
        "last_page_index": snapshot.get("last_page_index"),
        "updated_at": _to_iso(snapshot.get("updated_at")),
    }


def update_volume_context_tool(
    *,
    volume_id: str,
    rolling_summary: str | None = None,
    active_characters: list[dict[str, str]] | None = None,
    open_threads: list[str] | None = None,
    glossary: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    existing = get_volume_context(volume_id) or {}
    next_rolling_summary = (
        str(rolling_summary).strip()
        if rolling_summary is not None
        else str(existing.get("rolling_summary") or "").strip()
    )
    next_active_characters = (
        _normalize_character_entries(active_characters)
        if active_characters is not None
        else _normalize_character_entries(existing.get("active_characters"))
    )
    next_open_threads = (
        _normalize_open_threads(open_threads)
        if open_threads is not None
        else _normalize_open_threads(existing.get("open_threads"))
    )
    next_glossary = (
        _normalize_glossary_entries(glossary)
        if glossary is not None
        else _normalize_glossary_entries(existing.get("glossary"))
    )

    upsert_volume_context(
        volume_id,
        rolling_summary=next_rolling_summary,
        active_characters=next_active_characters,
        open_threads=next_open_threads,
        glossary=next_glossary,
        last_page_index=existing.get("last_page_index"),
    )
    refreshed = get_volume_context(volume_id) or {}
    return {
        "status": "ok",
        "volume_id": volume_id,
        "rolling_summary": str(refreshed.get("rolling_summary") or "").strip(),
        "active_characters": _normalize_character_entries(refreshed.get("active_characters")),
        "open_threads": _normalize_open_threads(refreshed.get("open_threads")),
        "glossary": _normalize_glossary_entries(refreshed.get("glossary")),
        "last_page_index": refreshed.get("last_page_index"),
        "updated_at": _to_iso(refreshed.get("updated_at")),
        "updated_fields": {
            "rolling_summary": rolling_summary is not None,
            "active_characters": active_characters is not None,
            "open_threads": open_threads is not None,
            "glossary": glossary is not None,
        },
    }


def get_page_memory_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    filename: str | None,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename, error = resolve_read_page_filename(
        volume_id=volume_id,
        filename=filename,
        active_filename=active_filename,
    )
    if error is not None or resolved_filename is None:
        return error or {"error": "filename resolution failed", "volume_id": volume_id}

    snapshot = get_page_context_snapshot(volume_id, resolved_filename) or {}
    return {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "manual_notes": str(snapshot.get("manual_notes") or "").strip(),
        "page_summary": str(snapshot.get("page_summary") or "").strip(),
        "image_summary": str(snapshot.get("image_summary") or "").strip(),
        "characters": _normalize_character_entries(snapshot.get("characters_snapshot")),
        "open_threads": _normalize_open_threads(snapshot.get("open_threads_snapshot")),
        "glossary": _normalize_glossary_entries(snapshot.get("glossary_snapshot")),
        "created_at": _to_iso(snapshot.get("created_at")),
        "updated_at": _to_iso(snapshot.get("updated_at")),
    }


def update_page_memory_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    filename: str | None,
    manual_notes: str | None = None,
    page_summary: str | None = None,
    image_summary: str | None = None,
    characters: list[dict[str, Any]] | None = None,
    open_threads: list[str] | None = None,
    glossary: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename, error = resolve_active_page_filename(
        volume_id=volume_id,
        filename=filename,
        active_filename=active_filename,
        action_label="Page-memory update",
    )
    if error is not None or resolved_filename is None:
        return error or {"error": "filename resolution failed", "volume_id": volume_id}

    existing = get_page_context_snapshot(volume_id, resolved_filename) or {}
    next_manual_notes = (
        str(manual_notes).strip()
        if manual_notes is not None
        else str(existing.get("manual_notes") or "").strip()
    )
    next_page_summary = (
        str(page_summary).strip()
        if page_summary is not None
        else str(existing.get("page_summary") or "").strip()
    )
    next_image_summary = (
        str(image_summary).strip()
        if image_summary is not None
        else str(existing.get("image_summary") or "").strip()
    )
    next_characters = (
        _normalize_character_entries(characters)
        if characters is not None
        else _normalize_character_entries(existing.get("characters_snapshot"))
    )
    next_open_threads = (
        _normalize_open_threads(open_threads)
        if open_threads is not None
        else _normalize_open_threads(existing.get("open_threads_snapshot"))
    )
    next_glossary = (
        _normalize_glossary_entries(glossary)
        if glossary is not None
        else _normalize_glossary_entries(existing.get("glossary_snapshot"))
    )

    upsert_page_context(
        volume_id,
        resolved_filename,
        manual_notes=next_manual_notes,
        page_summary=next_page_summary,
        image_summary=next_image_summary,
        characters_snapshot=next_characters,
        open_threads_snapshot=next_open_threads,
        glossary_snapshot=next_glossary,
    )
    refreshed = get_page_context_snapshot(volume_id, resolved_filename) or {}
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "manual_notes": str(refreshed.get("manual_notes") or "").strip(),
        "page_summary": str(refreshed.get("page_summary") or "").strip(),
        "image_summary": str(refreshed.get("image_summary") or "").strip(),
        "characters": _normalize_character_entries(refreshed.get("characters_snapshot")),
        "open_threads": _normalize_open_threads(refreshed.get("open_threads_snapshot")),
        "glossary": _normalize_glossary_entries(refreshed.get("glossary_snapshot")),
        "created_at": _to_iso(refreshed.get("created_at")),
        "updated_at": _to_iso(refreshed.get("updated_at")),
        "updated_fields": {
            "manual_notes": manual_notes is not None,
            "page_summary": page_summary is not None,
            "image_summary": image_summary is not None,
            "characters": characters is not None,
            "open_threads": open_threads is not None,
            "glossary": glossary is not None,
        },
    }


def search_volume_text_boxes_tool(
    *,
    volume_id: str,
    query: str,
    limit: int = 40,
    only_translated: bool = False,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return {"error": "query is required"}

    safe_limit = max(1, min(int(limit), 200))
    results: list[dict[str, Any]] = []
    for filename in list_page_filenames(volume_id):
        page = load_page(volume_id, filename)
        text_boxes = list_text_boxes_for_page(page)
        for box in text_boxes:
            text_value = str(box.get("text") or "").strip()
            translation_value = str(box.get("translation") or "").strip()
            if only_translated and not translation_value:
                continue
            haystack = f"{text_value}\n{translation_value}".lower()
            if normalized_query not in haystack:
                continue
            results.append(
                {
                    "filename": filename,
                    "box_id": int(box.get("id") or 0),
                    "orderIndex": int(box.get("orderIndex") or 0),
                    "text": text_value,
                    "translation": translation_value,
                }
            )
            if len(results) >= safe_limit:
                return {
                    "volume_id": volume_id,
                    "query": query,
                    "total": len(results),
                    "results": results,
                    "truncated": True,
                }
    return {
        "volume_id": volume_id,
        "query": query,
        "total": len(results),
        "results": results,
        "truncated": False,
    }
