# backend-python/core/usecases/agent/tool_context.py
"""Volume-level context helpers for agent tools."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tool_shared import list_text_boxes_for_page
from infra.db.db_store import (
    get_volume_context,
    list_page_filenames,
    load_page,
    upsert_volume_context,
)


def _normalize_active_characters(value: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        info = str(item.get("info") or "").strip()
        if not name and not info:
            continue
        out.append({"name": name, "info": info})
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
        "active_characters": _normalize_active_characters(snapshot.get("active_characters")),
        "open_threads": _normalize_open_threads(snapshot.get("open_threads")),
        "glossary": _normalize_glossary_entries(snapshot.get("glossary")),
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
        _normalize_active_characters(active_characters)
        if active_characters is not None
        else _normalize_active_characters(existing.get("active_characters"))
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
    )
    refreshed = get_volume_context(volume_id) or {}
    return {
        "status": "ok",
        "volume_id": volume_id,
        "rolling_summary": str(refreshed.get("rolling_summary") or "").strip(),
        "active_characters": _normalize_active_characters(refreshed.get("active_characters")),
        "open_threads": _normalize_open_threads(refreshed.get("open_threads")),
        "glossary": _normalize_glossary_entries(refreshed.get("glossary")),
        "updated_fields": {
            "rolling_summary": rolling_summary is not None,
            "active_characters": active_characters is not None,
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
