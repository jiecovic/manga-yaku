# backend-python/core/usecases/agent/tool_jobs.py
"""Job-backed OCR and detection helpers for agent tools."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tool_shared import (
    coerce_filename,
    find_text_box_by_id,
    list_text_boxes_for_page,
    resolve_active_page_filename,
)
from core.usecases.agent.turn_state import get_active_page_revision
from core.usecases.ocr.workflow_creation import OcrBoxWorkflowInput, create_ocr_box_workflow
from infra.db.db_store import load_page
from infra.jobs.job_modes import BOX_DETECTION_JOB_TYPE
from infra.jobs.runtime import create_and_enqueue_memory_job, wait_for_memory_job_terminal
from infra.jobs.store import JobStatus
from infra.jobs.workflow_runtime import wait_for_workflow_terminal

_TOOL_JOB_WAIT_TIMEOUT_SECONDS = 15.0
_TOOL_JOB_WAIT_POLL_SECONDS = 0.1
_TOOL_WORKFLOW_WAIT_TIMEOUT_SECONDS = 20.0
_TOOL_WORKFLOW_WAIT_POLL_SECONDS = 0.2



def detect_text_boxes_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    filename: str | None,
    profile_id: str | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    if not volume_id:
        return {"error": "No active volume selected"}

    resolved_filename, error = resolve_active_page_filename(
        volume_id=volume_id,
        filename=filename,
        active_filename=active_filename,
        action_label="Detection",
    )
    if error is not None or resolved_filename is None:
        return error or {"error": "filename resolution failed", "volume_id": volume_id}

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
    filename: str | None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    from core.usecases.ocr.profile_settings import agent_enabled_ocr_profiles

    if not volume_id:
        return {"error": "No active volume selected"}
    if int(box_id) <= 0:
        return {"error": "box_id must be > 0"}

    resolved_filename, error = resolve_active_page_filename(
        volume_id=volume_id,
        filename=filename,
        active_filename=active_filename,
        action_label="OCR",
    )
    if error is not None or resolved_filename is None:
        return error or {"error": "filename resolution failed", "volume_id": volume_id}

    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    target_box = find_text_box_by_id(text_boxes, int(box_id))
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
        workflow_run_id = create_ocr_box_workflow(
            OcrBoxWorkflowInput(
                profile_id=selected_profile_id,
                volume_id=volume_id,
                filename=resolved_filename,
                x=float(target_box["x"]),
                y=float(target_box["y"]),
                width=float(target_box["width"]),
                height=float(target_box["height"]),
                box_id=int(target_box["id"]),
                box_order=int(target_box["orderIndex"]),
            )
        )
    except Exception as exc:
        return {
            "error": str(exc).strip() or "Failed to enqueue OCR job",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
        }

    try:
        run = wait_for_workflow_terminal(
            workflow_run_id,
            timeout_seconds=_TOOL_WORKFLOW_WAIT_TIMEOUT_SECONDS,
            poll_seconds=_TOOL_WORKFLOW_WAIT_POLL_SECONDS,
        )
    except TimeoutError:
        run = None

    if run is None:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": "queued",
            "message": "OCR job queued/running; check Jobs panel for live progress",
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
    refreshed_box = find_text_box_by_id(refreshed_boxes, int(box_id))
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
