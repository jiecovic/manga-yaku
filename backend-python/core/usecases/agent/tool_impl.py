# backend-python/core/usecases/agent/tool_impl.py
"""Shared tool implementation helpers for agent chat tools."""

from __future__ import annotations

import time
from typing import Any

from core.usecases.agent.turn_state import get_active_page_revision
from infra.db.db_store import (
    get_volume_context,
    list_page_filenames,
    load_page,
    set_box_note_by_id,
    set_box_ocr_text_by_id,
    set_box_translation_by_id,
    upsert_volume_context,
)

_TOOL_JOB_WAIT_TIMEOUT_SECONDS = 15.0
_TOOL_JOB_WAIT_POLL_SECONDS = 0.1
_TOOL_WORKFLOW_WAIT_TIMEOUT_SECONDS = 20.0
_TOOL_WORKFLOW_WAIT_POLL_SECONDS = 0.2


def coerce_filename(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def list_text_boxes_for_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    if not isinstance(raw_boxes, list):
        return []

    out: list[dict[str, Any]] = []
    for box in raw_boxes:
        if not isinstance(box, dict):
            continue
        if str(box.get("type") or "").strip().lower() != "text":
            continue
        box_id = int(box.get("id") or 0)
        if box_id <= 0:
            continue
        out.append(
            {
                "id": box_id,
                "orderIndex": int(box.get("orderIndex") or box_id),
                "x": float(box.get("x") or 0.0),
                "y": float(box.get("y") or 0.0),
                "width": float(box.get("width") or 0.0),
                "height": float(box.get("height") or 0.0),
                "text": str(box.get("text") or "").strip(),
                "translation": str(box.get("translation") or "").strip(),
                "note": str(box.get("note") or "").strip(),
            }
        )

    out.sort(key=lambda item: (item["orderIndex"], item["id"]))
    return out


def _find_text_box_by_id(text_boxes: list[dict[str, Any]], box_id: int) -> dict[str, Any] | None:
    target_box_id = int(box_id)
    return next((item for item in text_boxes if int(item["id"]) == target_box_id), None)


def list_volume_pages_tool(volume_id: str) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}
    filenames = list_page_filenames(volume_id)
    return {
        "volume_id": volume_id,
        "page_count": len(filenames),
        "filenames": filenames,
    }


def set_active_page_tool(
    *,
    volume_id: str,
    filename: str,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename = coerce_filename(filename)
    if not resolved_filename:
        return {"error": "filename is required"}

    filenames = list_page_filenames(volume_id)
    if resolved_filename not in filenames:
        return {
            "error": f"Page {resolved_filename} was not found in volume {volume_id}",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "page_count": len(filenames),
        }

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "text_box_count": len(text_boxes),
        "page_index": int(filenames.index(resolved_filename)) + 1,
        "page_count": len(filenames),
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=resolved_filename,
        ),
    }


def shift_active_page_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    offset: int,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    filenames = list_page_filenames(volume_id)
    if not filenames:
        return {"error": "No pages found in active volume", "volume_id": volume_id, "page_count": 0}

    if active_filename and active_filename in filenames:
        current_index = filenames.index(active_filename)
    else:
        current_index = 0

    delta = int(offset)
    if delta == 0:
        return set_active_page_tool(volume_id=volume_id, filename=filenames[current_index])

    target_index = current_index + delta
    if target_index < 0:
        target_index = 0
    if target_index >= len(filenames):
        target_index = len(filenames) - 1

    target_filename = filenames[target_index]
    result = set_active_page_tool(volume_id=volume_id, filename=target_filename)
    if str(result.get("status") or "").strip().lower() == "ok":
        result["moved_by"] = int(target_index - current_index)
        result["requested_offset"] = delta
        result["at_boundary"] = bool(target_index == 0 or target_index == len(filenames) - 1)
    return result


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


def get_volume_context_tool(
    *,
    volume_id: str,
) -> dict[str, Any]:
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


def list_text_boxes_tool(
    *,
    volume_id: str,
    filename: str,
    limit: int = 300,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename = coerce_filename(filename)
    if not resolved_filename:
        return {"error": "filename is required"}

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    safe_limit = max(1, min(int(limit), 500))
    return {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "total": len(text_boxes),
        "boxes": text_boxes[:safe_limit],
    }


def get_text_box_detail_tool(
    *,
    volume_id: str,
    box_id: int,
    filename: str,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename = coerce_filename(filename)
    if not resolved_filename:
        return {"error": "filename is required"}

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    target = _find_text_box_by_id(text_boxes, int(box_id))
    if target is None:
        return {
            "error": f"Text box {int(box_id)} not found",
            "volume_id": volume_id,
            "filename": resolved_filename,
        }
    return {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "box": target,
    }


def update_text_box_fields_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    box_id: int,
    filename: str,
    text: str | None = None,
    translation: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename = coerce_filename(filename)
    if not resolved_filename:
        return {"error": "filename is required"}
    if text is None and translation is None and note is None:
        return {"error": "At least one of text, translation, or note is required"}
    if not active_filename:
        return {"error": "No active page selected"}
    if resolved_filename != active_filename:
        return {
            "error": (
                f"Writes are restricted to the active page ({active_filename}); "
                f"got {resolved_filename}"
            ),
            "volume_id": volume_id,
            "active_filename": active_filename,
            "filename": resolved_filename,
        }

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    existing = _find_text_box_by_id(text_boxes, int(box_id))
    if existing is None:
        return {
            "error": f"Text box {int(box_id)} not found",
            "volume_id": volume_id,
            "filename": resolved_filename,
        }

    if text is not None:
        set_box_ocr_text_by_id(
            volume_id,
            resolved_filename,
            box_id=int(box_id),
            ocr_text=str(text),
        )
    if translation is not None:
        set_box_translation_by_id(
            volume_id,
            resolved_filename,
            box_id=int(box_id),
            translation=str(translation),
        )
    if note is not None:
        set_box_note_by_id(
            volume_id,
            resolved_filename,
            box_id=int(box_id),
            note=str(note),
        )

    refreshed = load_page(volume_id, resolved_filename)
    refreshed_boxes = list_text_boxes_for_page(refreshed)
    updated = _find_text_box_by_id(refreshed_boxes, int(box_id))
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "box_id": int(box_id),
        "updated_fields": {
            "text": text is not None,
            "translation": translation is not None,
            "note": note is not None,
        },
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=resolved_filename,
        ),
        "box": updated or existing,
    }


def detect_text_boxes_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    filename: str,
    profile_id: str | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    from infra.jobs.job_modes import BOX_DETECTION_JOB_TYPE
    from infra.jobs.runtime import create_and_enqueue_memory_job, wait_for_memory_job_terminal
    from infra.jobs.store import JobStatus

    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename = coerce_filename(filename)
    if not resolved_filename:
        return {"error": "filename is required"}
    if not active_filename:
        return {"error": "No active page selected"}
    if resolved_filename != active_filename:
        return {
            "error": (
                f"Detection is restricted to the active page ({active_filename}); "
                f"got {resolved_filename}"
            ),
            "volume_id": volume_id,
            "active_filename": active_filename,
            "filename": resolved_filename,
        }

    payload = {
        "volumeId": volume_id,
        "filename": resolved_filename,
        "profileId": coerce_filename(profile_id),
        "replaceExisting": bool(replace_existing),
        "task": "text",
    }
    try:
        job_id = create_and_enqueue_memory_job(
            job_type=BOX_DETECTION_JOB_TYPE,
            payload=payload,
            message="Queued (agent tool)",
        )
    except Exception as exc:
        return {
            "error": str(exc).strip() or "Failed to enqueue detection job",
            "volume_id": volume_id,
            "filename": resolved_filename,
        }

    try:
        finished_job = wait_for_memory_job_terminal(
            job_id=job_id,
            timeout_seconds=_TOOL_JOB_WAIT_TIMEOUT_SECONDS,
            poll_seconds=_TOOL_JOB_WAIT_POLL_SECONDS,
        )
    except TimeoutError:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "job_status": JobStatus.queued.value,
            "message": "Detection job queued/running; check Jobs panel for live progress",
        }
    except Exception as exc:
        return {
            "error": str(exc).strip() or "Failed while waiting for detection job",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
        }

    if finished_job is None:
        return {
            "error": "Detection job disappeared before completion",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
        }

    if finished_job.status == JobStatus.failed:
        return {
            "error": str(finished_job.error or "Detection job failed"),
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "job_status": finished_job.status.value,
        }

    if finished_job.status == JobStatus.canceled:
        return {
            "error": "Detection job was canceled",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "job_status": finished_job.status.value,
        }

    if finished_job.status in {JobStatus.queued, JobStatus.running}:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "job_status": finished_job.status.value,
            "message": "Detection job queued/running; check Jobs panel for live progress",
        }

    job_result = finished_job.result if isinstance(finished_job.result, dict) else {}
    detected_count = int(job_result.get("count") or 0)
    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "profile_id": coerce_filename(profile_id),
        "replace_existing": bool(replace_existing),
        "detected_count": detected_count,
        "text_box_count": len(text_boxes),
        "job_id": job_id,
        "job_status": finished_job.status.value,
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=resolved_filename,
        ),
    }


def list_ocr_profiles_tool() -> dict[str, Any]:
    from core.usecases.ocr.profile_settings import agent_enabled_ocr_profiles
    from core.usecases.ocr.profiles import get_ocr_profile, list_ocr_profiles_for_api

    profiles_raw = list_ocr_profiles_for_api()
    agent_enabled = set(agent_enabled_ocr_profiles())

    profiles: list[dict[str, Any]] = []
    for item in profiles_raw:
        profile_id = str(item.get("id") or "").strip()
        if not profile_id:
            continue
        hint = ""
        try:
            profile = get_ocr_profile(profile_id)
            hint = str(profile.get("llm_hint") or "").strip()
        except Exception:
            hint = ""
        profiles.append(
            {
                "id": profile_id,
                "label": str(item.get("label") or profile_id),
                "description": str(item.get("description") or "").strip(),
                "hint": hint,
                "kind": str(item.get("kind") or ""),
                "enabled": bool(item.get("enabled", False)),
                "agent_enabled": profile_id in agent_enabled,
                "model_id": str(item.get("model_id") or "").strip() or None,
            }
        )

    default_profile_id = None
    for profile in profiles:
        if bool(profile.get("agent_enabled")):
            default_profile_id = str(profile["id"])
            break
    if not default_profile_id and profiles:
        default_profile_id = str(profiles[0]["id"])

    return {
        "total": len(profiles),
        "default_profile_id": default_profile_id,
        "profiles": profiles,
    }


def ocr_text_box_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    box_id: int,
    filename: str,
    profile_id: str | None = None,
) -> dict[str, Any]:
    from api.schemas.jobs import CreateOcrBoxJobRequest
    from api.services.jobs_creation_service import create_ocr_box_workflow
    from core.usecases.ocr.profile_settings import agent_enabled_ocr_profiles
    from infra.db.workflow_store import get_workflow_run

    if not volume_id:
        return {"error": "No active volume selected"}
    if int(box_id) <= 0:
        return {"error": "box_id must be > 0"}

    resolved_filename = coerce_filename(filename)
    if not resolved_filename:
        return {"error": "filename is required"}
    if not active_filename:
        return {"error": "No active page selected"}
    if resolved_filename != active_filename:
        return {
            "error": (
                f"OCR is restricted to the active page ({active_filename}); "
                f"got {resolved_filename}"
            ),
            "volume_id": volume_id,
            "active_filename": active_filename,
            "filename": resolved_filename,
        }

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    target_box = _find_text_box_by_id(text_boxes, int(box_id))
    if target_box is None:
        return {
            "error": f"Text box {int(box_id)} not found",
            "volume_id": volume_id,
            "filename": resolved_filename,
        }

    selected_profile_id = coerce_filename(profile_id)
    if not selected_profile_id:
        enabled_profiles = agent_enabled_ocr_profiles()
        selected_profile_id = enabled_profiles[0] if enabled_profiles else "manga_ocr_default"

    try:
        req = CreateOcrBoxJobRequest(
            profileId=selected_profile_id,
            volumeId=volume_id,
            filename=resolved_filename,
            x=float(target_box["x"]),
            y=float(target_box["y"]),
            width=float(target_box["width"]),
            height=float(target_box["height"]),
            boxId=int(target_box["id"]),
            boxOrder=int(target_box["orderIndex"]),
        )
        workflow_run_id = create_ocr_box_workflow(req)
    except Exception as exc:
        return {
            "error": str(exc).strip() or "Failed to enqueue OCR job",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
        }

    deadline = time.monotonic() + _TOOL_WORKFLOW_WAIT_TIMEOUT_SECONDS
    run = get_workflow_run(workflow_run_id)
    while (
        run is not None
        and str(run.get("status") or "").strip().lower() in {"queued", "running"}
        and time.monotonic() < deadline
    ):
        time.sleep(_TOOL_WORKFLOW_WAIT_POLL_SECONDS)
        run = get_workflow_run(workflow_run_id)

    if run is None:
        return {
            "error": "OCR workflow disappeared before completion",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
        }

    workflow_status = str(run.get("status") or "").strip().lower() or "failed"
    result_json = run.get("result_json") if isinstance(run.get("result_json"), dict) else {}
    if workflow_status == "failed":
        return {
            "error": str(run.get("error_message") or "OCR workflow failed").strip(),
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": workflow_status,
        }
    if workflow_status == "canceled":
        return {
            "error": "OCR workflow was canceled",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": workflow_status,
        }
    if workflow_status in {"queued", "running"}:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": workflow_status,
            "message": "OCR job queued/running; check Jobs panel for live progress",
        }

    refreshed = load_page(volume_id, resolved_filename)
    refreshed_boxes = list_text_boxes_for_page(refreshed)
    refreshed_box = _find_text_box_by_id(refreshed_boxes, int(box_id))
    text_value = str((refreshed_box or {}).get("text") or "").strip()
    status = "ok" if text_value else "no_text"
    return {
        "status": status,
        "volume_id": volume_id,
        "filename": resolved_filename,
        "box_id": int(box_id),
        "profile_id": selected_profile_id,
        "workflow_run_id": workflow_run_id,
        "workflow_status": workflow_status,
        "text": text_value,
        "result_message": str(result_json.get("message") or "").strip() or None,
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=resolved_filename,
        ),
        "box": refreshed_box or target_box,
    }
