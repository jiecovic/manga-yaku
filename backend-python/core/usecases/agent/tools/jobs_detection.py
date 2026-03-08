# backend-python/core/usecases/agent/tools/jobs_detection.py
"""Detection job-backed helpers for agent tools."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.grounding.turn_state import build_page_state_snapshot
from core.usecases.agent.tools.jobs_shared import (
    build_auto_idempotency_key,
    normalize_claim_status,
    wait_for_agent_workflow,
)
from core.usecases.agent.tools.shared import (
    coerce_filename,
    list_text_boxes_for_page,
    resolve_active_page_filename,
)
from infra.db.idempotency_store import (
    claim_idempotency_key,
    finalize_idempotency_key,
    release_idempotency_claim,
)
from infra.db.store_volume_page import load_page
from infra.jobs.job_modes import BOX_DETECTION_JOB_TYPE
from infra.jobs.operations import BOX_DETECTION_OPERATION, enqueue_persisted_operation


def detect_text_boxes_tool(
    *,
    volume_id: str,
    active_filename: str | None,
    filename: str | None,
    profile_id: str | None = None,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Run page-level text-box detection through the persisted workflow layer."""
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

    selected_profile_id = coerce_filename(profile_id)
    initial_page = load_page(volume_id, resolved_filename)
    initial_page_state = build_page_state_snapshot(
        volume_id=volume_id,
        filename=resolved_filename,
        page=initial_page,
    )
    idempotency_payload = {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "profile_id": selected_profile_id,
        "replace_existing": bool(replace_existing),
        "page_revision": initial_page_state.page_revision,
    }
    idempotency_key, request_hash = build_auto_idempotency_key(
        namespace="agent.detect_text_boxes",
        payload=idempotency_payload,
    )
    claim = claim_idempotency_key(
        job_type=BOX_DETECTION_JOB_TYPE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    idempotency_state = normalize_claim_status(str(claim.get("status") or ""))
    if idempotency_state == "conflict":
        return {
            "error": "Equivalent detection request conflicted with different payload",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }
    if idempotency_state == "replay":
        if not list_text_boxes_for_page(initial_page):
            claim = {}
            idempotency_state = "new"
            idempotency_key = None
            request_hash = None

    payload = {
        "volumeId": volume_id,
        "filename": resolved_filename,
        "profileId": selected_profile_id,
        "replaceExisting": bool(replace_existing),
        "task": "text",
    }
    job_id = str(claim.get("resource_id") or "").strip()
    if idempotency_state == "new":
        try:
            job_id = enqueue_persisted_operation(
                BOX_DETECTION_OPERATION,
                payload,
                message="Queued (agent tool)",
            )
            if idempotency_key and request_hash:
                job_id = finalize_idempotency_key(
                    job_type=BOX_DETECTION_JOB_TYPE,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resource_id=job_id,
                )
        except Exception as exc:
            if idempotency_key and request_hash:
                release_idempotency_claim(
                    job_type=BOX_DETECTION_JOB_TYPE,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )
            return {
                "error": str(exc).strip() or "Failed to enqueue detection job",
                "volume_id": volume_id,
                "filename": resolved_filename,
                "idempotency_key": idempotency_key,
                "idempotency_state": "new",
            }
    elif idempotency_state == "in_progress" and not job_id:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "profile_id": selected_profile_id,
            "replace_existing": bool(replace_existing),
            "job_status": "queued",
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
            "resource_reused": True,
            "message": "Equivalent detection job is already being created or queued",
        }

    observation = wait_for_agent_workflow(
        workflow_run_id=job_id,
        timeout_seconds=BOX_DETECTION_OPERATION.agent_wait_timeout_seconds or 15.0,
        poll_seconds=BOX_DETECTION_OPERATION.agent_wait_poll_seconds or 0.2,
        wait_error_message="Failed while waiting for detection job",
    )
    if observation.wait_error is not None:
        return {
            "error": observation.wait_error,
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": job_id,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }

    if not observation.found:
        if idempotency_state == "replay":
            return _build_detection_replay_snapshot(
                volume_id=volume_id,
                filename=resolved_filename,
                profile_id=selected_profile_id,
                replace_existing=replace_existing,
                job_id=job_id,
                idempotency_key=idempotency_key,
            )
        return {
            "error": "Detection job disappeared before completion",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": job_id,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }

    workflow_status = observation.workflow_status
    result_json = observation.result_json
    if observation.failed:
        return {
            "error": observation.error_message or "Detection job failed",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": job_id,
            "job_status": workflow_status,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }
    if observation.canceled:
        return {
            "error": "Detection job was canceled",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": job_id,
            "job_status": workflow_status,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }
    if observation.active:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "profile_id": selected_profile_id,
            "replace_existing": bool(replace_existing),
            "job_id": job_id,
            "workflow_run_id": job_id,
            "job_status": workflow_status,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
            "resource_reused": idempotency_state != "new",
            "message": str(result_json.get("message") or "").strip()
            or "Detection job queued/running; check Jobs panel for live progress",
        }

    page = load_page(volume_id, resolved_filename)
    page_state = build_page_state_snapshot(
        volume_id=volume_id,
        filename=resolved_filename,
        page=page,
    )
    total_text_box_count = int(page_state.text_box_count or 0)
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "profile_id": selected_profile_id,
        "replace_existing": bool(replace_existing),
        "new_box_count": int(result_json.get("count") or 0),
        "detected_count": int(result_json.get("count") or 0),
        "total_text_box_count": total_text_box_count,
        "text_box_count": total_text_box_count,
        "job_id": job_id,
        "workflow_run_id": job_id,
        "job_status": workflow_status,
        "page_revision": page_state.page_revision,
        "idempotency_key": idempotency_key,
        "idempotency_state": idempotency_state,
        "resource_reused": idempotency_state != "new",
        "message": _build_detection_result_message(
            new_box_count=int(result_json.get("count") or 0),
            total_text_box_count=total_text_box_count,
            replace_existing=replace_existing,
        ),
    }


def _build_detection_replay_snapshot(
    *,
    volume_id: str,
    filename: str,
    profile_id: str | None,
    replace_existing: bool,
    job_id: str,
    idempotency_key: str | None,
) -> dict[str, Any]:
    page = load_page(volume_id, filename)
    page_state = build_page_state_snapshot(
        volume_id=volume_id,
        filename=filename,
        page=page,
    )
    total_text_box_count = int(page_state.text_box_count or 0)
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": filename,
        "profile_id": profile_id,
        "replace_existing": bool(replace_existing),
        "new_box_count": 0,
        "detected_count": 0,
        "total_text_box_count": total_text_box_count,
        "text_box_count": total_text_box_count,
        "job_id": job_id,
        "job_status": "missing",
        "page_revision": page_state.page_revision,
        "idempotency_key": idempotency_key,
        "idempotency_state": "replay",
        "resource_reused": True,
        "message": "Equivalent detection request already completed; reused current page state",
    }


def _build_detection_result_message(
    *,
    new_box_count: int,
    total_text_box_count: int,
    replace_existing: bool,
) -> str:
    """Summarize whether detection added anything new to the page."""
    if new_box_count > 0:
        if replace_existing:
            return f"Detected {new_box_count} text boxes"
        return (
            f"Added {new_box_count} new text boxes; page now has {total_text_box_count} text boxes"
        )
    if replace_existing:
        return "No text boxes detected"
    return "No new text boxes detected; existing overlapping boxes were preserved"
