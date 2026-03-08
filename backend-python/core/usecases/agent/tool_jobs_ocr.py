# backend-python/core/usecases/agent/tool_jobs_ocr.py
"""OCR job-backed helpers for agent tools."""

from __future__ import annotations

from typing import Any

from core.usecases.agent.tool_jobs_shared import (
    build_auto_idempotency_key,
    build_box_revision,
    normalize_claim_status,
    wait_for_agent_workflow,
)
from core.usecases.agent.tool_shared import (
    coerce_filename,
    find_text_box_by_id,
    list_text_boxes_for_page,
    resolve_active_page_filename,
)
from core.usecases.agent.turn_state import get_active_page_revision
from infra.db.db_store import load_page
from infra.db.idempotency_store import (
    claim_idempotency_key,
    finalize_idempotency_key,
    release_idempotency_claim,
)
from infra.jobs.job_modes import OCR_BOX_WORKFLOW_TYPE
from infra.jobs.operations import OCR_BOX_OPERATION, enqueue_persisted_operation


def list_ocr_profiles_tool() -> dict[str, Any]:
    """Return agent-eligible OCR profiles and defaults."""
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
    force_rerun: bool = False,
) -> dict[str, Any]:
    """Run OCR for a single box through the persisted workflow layer."""
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
    existing_text = str(target_box.get("text") or "").strip()
    if existing_text and not force_rerun:
        return {
            "status": "skipped_existing",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": None,
            "text": existing_text,
            "page_revision": get_active_page_revision(
                volume_id=volume_id,
                current_filename=resolved_filename,
            ),
            "box": target_box,
            "resource_reused": True,
            "message": "Skipped OCR because the box already has text; use force_rerun=true to rerun OCR",
        }

    selected_profile_id = coerce_filename(profile_id)
    if not selected_profile_id:
        enabled_profiles = agent_enabled_ocr_profiles()
        selected_profile_id = enabled_profiles[0] if enabled_profiles else "manga_ocr_default"

    idempotency_payload = {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "profile_id": selected_profile_id,
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=resolved_filename,
        ),
        "box_revision": build_box_revision(target_box),
    }
    idempotency_key, request_hash = build_auto_idempotency_key(
        namespace="agent.ocr_text_box",
        payload=idempotency_payload,
    )
    claim = claim_idempotency_key(
        job_type=OCR_BOX_WORKFLOW_TYPE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    idempotency_state = normalize_claim_status(str(claim.get("status") or ""))
    if idempotency_state == "conflict":
        return {
            "error": "Equivalent OCR request conflicted with different payload",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }

    workflow_run_id = str(claim.get("resource_id") or "").strip()
    if idempotency_state == "new":
        try:
            workflow_run_id = enqueue_persisted_operation(
                OCR_BOX_OPERATION,
                {
                    "profileId": selected_profile_id,
                    "volumeId": volume_id,
                    "filename": resolved_filename,
                    "x": float(target_box["x"]),
                    "y": float(target_box["y"]),
                    "width": float(target_box["width"]),
                    "height": float(target_box["height"]),
                    "boxId": int(target_box["id"]),
                    "boxOrder": int(target_box["orderIndex"]),
                },
            )
            workflow_run_id = finalize_idempotency_key(
                job_type=OCR_BOX_WORKFLOW_TYPE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                resource_id=workflow_run_id,
            )
        except Exception as exc:
            release_idempotency_claim(
                job_type=OCR_BOX_WORKFLOW_TYPE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            return {
                "error": str(exc).strip() or "Failed to enqueue OCR job",
                "volume_id": volume_id,
                "filename": resolved_filename,
                "box_id": int(box_id),
                "profile_id": selected_profile_id,
                "idempotency_key": idempotency_key,
                "idempotency_state": "new",
            }
    elif idempotency_state == "in_progress" and not workflow_run_id:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_status": "queued",
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
            "resource_reused": True,
            "message": "Equivalent OCR workflow is already being created or queued",
        }

    observation = wait_for_agent_workflow(
        workflow_run_id=workflow_run_id,
        timeout_seconds=OCR_BOX_OPERATION.agent_wait_timeout_seconds or 20.0,
        poll_seconds=OCR_BOX_OPERATION.agent_wait_poll_seconds or 0.2,
        wait_error_message="Failed while waiting for OCR job",
    )
    if observation.wait_error is not None:
        return {
            "error": observation.wait_error,
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }

    if not observation.found:
        if idempotency_state == "replay":
            return _build_ocr_replay_snapshot(
                volume_id=volume_id,
                filename=resolved_filename,
                box_id=int(box_id),
                profile_id=selected_profile_id,
                workflow_run_id=workflow_run_id,
                idempotency_key=idempotency_key,
                target_box=target_box,
            )
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": "queued",
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
            "resource_reused": idempotency_state != "new",
            "message": "OCR job queued/running; check Jobs panel for live progress",
        }

    workflow_status = observation.workflow_status
    result_json = observation.result_json
    if observation.failed:
        return {
            "error": observation.error_message or "OCR workflow failed",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": workflow_status,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }
    if observation.canceled:
        return {
            "error": "OCR workflow was canceled",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": workflow_status,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }
    if observation.active:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": workflow_status,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
            "resource_reused": idempotency_state != "new",
            "message": "OCR job queued/running; check Jobs panel for live progress",
        }

    refreshed = load_page(volume_id, resolved_filename)
    refreshed_box = find_text_box_by_id(list_text_boxes_for_page(refreshed), int(box_id))
    text_value = str((refreshed_box or {}).get("text") or "").strip()
    return {
        "status": "ok" if text_value else "no_text",
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
        "idempotency_key": idempotency_key,
        "idempotency_state": idempotency_state,
        "resource_reused": idempotency_state != "new",
    }


def _build_ocr_replay_snapshot(
    *,
    volume_id: str,
    filename: str,
    box_id: int,
    profile_id: str,
    workflow_run_id: str,
    idempotency_key: str,
    target_box: dict[str, Any],
) -> dict[str, Any]:
    refreshed = load_page(volume_id, filename)
    refreshed_box = find_text_box_by_id(list_text_boxes_for_page(refreshed), box_id)
    text_value = str((refreshed_box or target_box).get("text") or "").strip()
    return {
        "status": "ok" if text_value else "no_text",
        "volume_id": volume_id,
        "filename": filename,
        "box_id": box_id,
        "profile_id": profile_id,
        "workflow_run_id": workflow_run_id,
        "workflow_status": "missing",
        "text": text_value,
        "result_message": "Equivalent OCR request already completed; reused current box state",
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=filename,
        ),
        "box": refreshed_box or target_box,
        "idempotency_key": idempotency_key,
        "idempotency_state": "replay",
        "resource_reused": True,
    }
