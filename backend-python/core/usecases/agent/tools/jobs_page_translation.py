# backend-python/core/usecases/agent/tools/jobs_page_translation.py
"""Page-translate job-backed helpers for agent tools."""

from __future__ import annotations

from config import TRANSLATION_SOURCE_LANGUAGE, TRANSLATION_TARGET_LANGUAGE
from core.usecases.agent.tools.jobs_shared import wait_for_agent_workflow
from core.usecases.agent.tools.shared import (
    coerce_filename,
    list_text_boxes_for_page,
    resolve_active_page_filename,
)
from infra.db.store_volume_page import load_page
from infra.jobs.operations import PAGE_TRANSLATION_OPERATION, enqueue_persisted_operation


def translate_active_page_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    filename: str | None,
    detection_profile_id: str | None = None,
    ocr_profiles: list[str] | None = None,
    source_language: str | None = None,
    target_language: str | None = None,
    model_id: str | None = None,
    force_rerun: bool = False,
) -> dict[str, object]:
    """Run page translation through the persisted page-translation workflow."""
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename, error = resolve_active_page_filename(
        volume_id=volume_id,
        filename=filename,
        active_filename=active_filename,
        action_label="Page translation",
    )
    if error is not None or resolved_filename is None:
        return error or {"error": "filename resolution failed", "volume_id": volume_id}

    pre_state = _count_page_translation_state(
        volume_id=volume_id,
        filename=resolved_filename,
    )
    already_translated_before = (
        pre_state["text_box_count"] > 0
        and pre_state["translated_count"] >= pre_state["text_box_count"]
    )
    if already_translated_before and not force_rerun:
        return {
            "status": "already_translated",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "text_box_count": pre_state["text_box_count"],
            "ocr_filled_count": pre_state["ocr_filled_count"],
            "translated_count": pre_state["translated_count"],
            "translated_now_count": 0,
            "already_translated_before": True,
            "resource_reused": True,
            "message": "Page already has translations; use force_rerun=true to overwrite them",
        }

    decision = enqueue_persisted_operation(
        PAGE_TRANSLATION_OPERATION,
        {
            "volumeId": volume_id,
            "filename": resolved_filename,
            "detectionProfileId": coerce_filename(detection_profile_id),
            "ocrProfiles": [
                str(item).strip() for item in (ocr_profiles or []) if str(item).strip()
            ],
            "sourceLanguage": coerce_filename(source_language) or TRANSLATION_SOURCE_LANGUAGE,
            "targetLanguage": coerce_filename(target_language) or TRANSLATION_TARGET_LANGUAGE,
            "modelId": coerce_filename(model_id),
            "forceRerun": bool(force_rerun),
        },
        idempotency_key=None,
    )
    status = str(decision.get("status") or "").strip().lower()
    if status == "invalid":
        return {
            "error": str(decision.get("detail") or "Invalid page-translate request"),
            "volume_id": volume_id,
            "filename": resolved_filename,
        }
    if status == "error":
        return {
            "error": str(decision.get("detail") or "Failed to enqueue page-translate workflow"),
            "volume_id": volume_id,
            "filename": resolved_filename,
        }

    job_id = str(decision.get("job_id") or "").strip()
    if not job_id:
        return {
            "error": "Failed to resolve page-translate job id",
            "volume_id": volume_id,
            "filename": resolved_filename,
        }

    observation = wait_for_agent_workflow(
        workflow_run_id=job_id,
        timeout_seconds=PAGE_TRANSLATION_OPERATION.agent_wait_timeout_seconds or 45.0,
        poll_seconds=PAGE_TRANSLATION_OPERATION.agent_wait_poll_seconds or 0.2,
        wait_error_message="Failed while waiting for page-translate workflow",
    )
    if observation.wait_error is not None:
        return {
            "error": observation.wait_error,
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
        }

    if not observation.found:
        return {
            "error": "Page translation workflow could not be found",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
        }

    workflow_run_id = observation.workflow_run_id or job_id
    workflow_status = observation.workflow_status or "queued"
    result_json = observation.result_json
    if observation.active:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": workflow_status,
            "text_box_count": pre_state["text_box_count"],
            "ocr_filled_count": pre_state["ocr_filled_count"],
            "translated_count": pre_state["translated_count"],
            "translated_now_count": 0,
            "already_translated_before": already_translated_before,
            "started_now": bool(decision.get("queued")),
            "message": str(result_json.get("message") or "").strip()
            or "Page translation workflow queued/running; check Jobs panel for live progress",
            "resource_reused": status != "queued",
        }
    if observation.failed:
        return {
            "error": observation.error_message or "Page translation workflow failed",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": workflow_run_id,
        }
    if observation.canceled:
        return {
            "error": "Page translation workflow was canceled",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": workflow_run_id,
        }

    post_state = _count_page_translation_state(
        volume_id=volume_id,
        filename=resolved_filename,
    )
    translated_now_count = max(0, post_state["translated_count"] - pre_state["translated_count"])
    return {
        "status": "completed",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "job_id": job_id,
        "workflow_run_id": str(result_json.get("workflowRunId") or "").strip() or workflow_run_id,
        "state": str(result_json.get("state") or "").strip() or "completed",
        "stage": str(result_json.get("stage") or "").strip() or "completed",
        "processed": int(result_json.get("processed") or 0),
        "total": int(result_json.get("total") or 0),
        "updated": int(result_json.get("updated") or 0),
        "order_applied": bool(result_json.get("orderApplied")),
        "text_box_count": post_state["text_box_count"],
        "ocr_filled_count": post_state["ocr_filled_count"],
        "translated_count": post_state["translated_count"],
        "translated_now_count": translated_now_count,
        "already_translated_before": already_translated_before,
        "message": str(result_json.get("message") or "").strip() or "Page translation complete",
        "story_summary": result_json.get("storySummary"),
        "image_summary": result_json.get("imageSummary"),
        "characters": result_json.get("characters"),
        "open_threads": result_json.get("openThreads"),
        "glossary": result_json.get("glossary"),
        "resource_reused": status != "queued",
    }


def count_page_translation_state(*, volume_id: str, filename: str) -> dict[str, int]:
    """Return translation progress counters for one page."""
    page = load_page(volume_id, filename)
    text_boxes = list_text_boxes_for_page(page)
    ocr_filled = 0
    translated = 0
    for box in text_boxes:
        if str(box.get("text") or "").strip():
            ocr_filled += 1
        if str(box.get("translation") or "").strip():
            translated += 1
    return {
        "text_box_count": len(text_boxes),
        "ocr_filled_count": ocr_filled,
        "translated_count": translated,
    }


_count_page_translation_state = count_page_translation_state
