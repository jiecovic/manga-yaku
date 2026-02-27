from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from infra.db.db_store import (
    clear_page_context_snapshot,
    clear_volume_context,
    clear_volume_derived_data,
    get_page_context_snapshot,
    get_volume,
    get_volume_context,
    list_page_filenames,
    set_page_context,
)


def _to_iso(value: datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def get_volume_memory_payload(volume_id: str) -> dict:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    context = get_volume_context(volume_id)
    if context is None:
        return {
            "rollingSummary": "",
            "activeCharacters": [],
            "openThreads": [],
            "glossary": [],
            "lastPageIndex": None,
            "updatedAt": None,
        }
    return {
        "rollingSummary": str(context.get("rolling_summary") or ""),
        "activeCharacters": context.get("active_characters") or [],
        "openThreads": context.get("open_threads") or [],
        "glossary": context.get("glossary") or [],
        "lastPageIndex": context.get("last_page_index"),
        "updatedAt": _to_iso(context.get("updated_at")),
    }


def get_page_memory_payload(volume_id: str, filename: str) -> dict:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    if filename not in set(list_page_filenames(volume_id)):
        raise HTTPException(status_code=404, detail="Page not found")
    context = get_page_context_snapshot(volume_id, filename)
    if context is None:
        return {
            "pageSummary": "",
            "imageSummary": "",
            "characters": [],
            "openThreads": [],
            "glossary": [],
            "createdAt": None,
            "updatedAt": None,
        }
    return {
        "pageSummary": str(context.get("page_summary") or ""),
        "imageSummary": str(context.get("image_summary") or ""),
        "characters": context.get("characters_snapshot") or [],
        "openThreads": context.get("open_threads_snapshot") or [],
        "glossary": context.get("glossary_snapshot") or [],
        "createdAt": _to_iso(context.get("created_at")),
        "updatedAt": _to_iso(context.get("updated_at")),
    }


def clear_volume_memory(volume_id: str) -> None:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    clear_volume_context(volume_id)


def clear_page_memory(volume_id: str, filename: str) -> None:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    if filename not in set(list_page_filenames(volume_id)):
        raise HTTPException(status_code=404, detail="Page not found")

    # Keep both page memory stores in sync when clearing.
    clear_page_context_snapshot(volume_id, filename)
    set_page_context(volume_id, filename, "")


def clear_volume_derived_state_payload(volume_id: str) -> dict:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")

    try:
        raw = clear_volume_derived_data(volume_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "cleared": True,
        "details": {
            "pagesTouched": int(raw.get("pages_touched") or 0),
            "boxesDeleted": int(raw.get("boxes_deleted") or 0),
            "detectionRunsDeleted": int(raw.get("detection_runs_deleted") or 0),
            "pageContextSnapshotsDeleted": int(raw.get("page_context_snapshots_deleted") or 0),
            "pageNotesCleared": int(raw.get("page_notes_cleared") or 0),
            "volumeContextDeleted": int(raw.get("volume_context_deleted") or 0),
            "agentSessionsDeleted": int(raw.get("agent_sessions_deleted") or 0),
            "workflowRunsDeleted": int(raw.get("workflow_runs_deleted") or 0),
            "taskRunsDeleted": int(raw.get("task_runs_deleted") or 0),
            "taskAttemptEventsDeleted": int(raw.get("task_attempt_events_deleted") or 0),
            "llmCallLogsDeleted": int(raw.get("llm_call_logs_deleted") or 0),
            "llmPayloadFilesDeleted": int(raw.get("llm_payload_files_deleted") or 0),
            "agentDebugFilesDeleted": int(raw.get("agent_debug_files_deleted") or 0),
        },
    }
