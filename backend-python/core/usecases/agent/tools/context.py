# backend-python/core/usecases/agent/tools/context.py
"""Volume and page memory helpers for agent tools."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tools.context_serialization import (
    serialize_character_entries,
    serialize_glossary_entries,
    serialize_open_threads,
    serialize_optional_timestamp,
)
from core.usecases.agent.tools.shared import (
    resolve_active_page_filename,
    resolve_read_page_filename,
)
from infra.db.store_context import (
    get_page_context_snapshot,
    get_volume_context,
    upsert_page_context,
    upsert_volume_context,
)


def get_volume_context_tool(*, volume_id: str) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}
    snapshot = get_volume_context(volume_id) or {}
    return {
        "volume_id": volume_id,
        "rolling_summary": str(snapshot.get("rolling_summary") or "").strip(),
        "active_characters": serialize_character_entries(snapshot.get("active_characters")),
        "open_threads": serialize_open_threads(snapshot.get("open_threads")),
        "glossary": serialize_glossary_entries(snapshot.get("glossary")),
        "last_page_index": snapshot.get("last_page_index"),
        "updated_at": serialize_optional_timestamp(snapshot.get("updated_at")),
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
        serialize_character_entries(active_characters)
        if active_characters is not None
        else serialize_character_entries(existing.get("active_characters"))
    )
    next_open_threads = (
        serialize_open_threads(open_threads)
        if open_threads is not None
        else serialize_open_threads(existing.get("open_threads"))
    )
    next_glossary = (
        serialize_glossary_entries(glossary)
        if glossary is not None
        else serialize_glossary_entries(existing.get("glossary"))
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
        "active_characters": serialize_character_entries(refreshed.get("active_characters")),
        "open_threads": serialize_open_threads(refreshed.get("open_threads")),
        "glossary": serialize_glossary_entries(refreshed.get("glossary")),
        "last_page_index": refreshed.get("last_page_index"),
        "updated_at": serialize_optional_timestamp(refreshed.get("updated_at")),
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
        "characters": serialize_character_entries(snapshot.get("characters_snapshot")),
        "open_threads": serialize_open_threads(snapshot.get("open_threads_snapshot")),
        "glossary": serialize_glossary_entries(snapshot.get("glossary_snapshot")),
        "created_at": serialize_optional_timestamp(snapshot.get("created_at")),
        "updated_at": serialize_optional_timestamp(snapshot.get("updated_at")),
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
        serialize_character_entries(characters)
        if characters is not None
        else serialize_character_entries(existing.get("characters_snapshot"))
    )
    next_open_threads = (
        serialize_open_threads(open_threads)
        if open_threads is not None
        else serialize_open_threads(existing.get("open_threads_snapshot"))
    )
    next_glossary = (
        serialize_glossary_entries(glossary)
        if glossary is not None
        else serialize_glossary_entries(existing.get("glossary_snapshot"))
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
        "characters": serialize_character_entries(refreshed.get("characters_snapshot")),
        "open_threads": serialize_open_threads(refreshed.get("open_threads_snapshot")),
        "glossary": serialize_glossary_entries(refreshed.get("glossary_snapshot")),
        "created_at": serialize_optional_timestamp(refreshed.get("created_at")),
        "updated_at": serialize_optional_timestamp(refreshed.get("updated_at")),
        "updated_fields": {
            "manual_notes": manual_notes is not None,
            "page_summary": page_summary is not None,
            "image_summary": image_summary is not None,
            "characters": characters is not None,
            "open_threads": open_threads is not None,
            "glossary": glossary is not None,
        },
    }
