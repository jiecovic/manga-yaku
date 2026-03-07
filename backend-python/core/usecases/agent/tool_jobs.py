# backend-python/core/usecases/agent/tool_jobs.py
"""Job-backed OCR and detection helpers for agent tools."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from config import TRANSLATION_SOURCE_LANGUAGE, TRANSLATION_TARGET_LANGUAGE
from core.usecases.agent.tool_shared import (
    coerce_filename,
    find_text_box_by_id,
    list_text_boxes_for_page,
    resolve_active_page_filename,
)
from core.usecases.agent.turn_state import get_active_page_revision
from core.usecases.ocr.workflow_creation import OcrBoxWorkflowInput, create_ocr_box_workflow
from infra.db.db_store import load_page
from infra.db.idempotency_store import (
    claim_idempotency_key,
    finalize_idempotency_key,
    release_idempotency_claim,
)
from infra.jobs.agent_translate_creation import create_agent_translate_page_job
from infra.jobs.job_modes import BOX_DETECTION_JOB_TYPE, OCR_BOX_WORKFLOW_TYPE
from infra.jobs.runtime import STORE
from infra.jobs.utility_workflow_creation import create_persisted_utility_workflow
from infra.jobs.workflow_repo import get_workflow_run
from infra.jobs.workflow_runtime import wait_for_workflow_terminal

_TOOL_JOB_WAIT_TIMEOUT_SECONDS = 15.0
_TOOL_JOB_WAIT_POLL_SECONDS = 0.1
_TOOL_WORKFLOW_WAIT_TIMEOUT_SECONDS = 20.0
_TOOL_WORKFLOW_WAIT_POLL_SECONDS = 0.2
_TOOL_AGENT_PAGE_WAIT_TIMEOUT_SECONDS = 45.0
_TOOL_AGENT_PAGE_WAIT_POLL_SECONDS = 0.2


def _canonical_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_auto_idempotency_key(*, namespace: str, payload: dict[str, Any]) -> tuple[str, str]:
    request_hash = _canonical_request_hash(payload)
    return f"{namespace}:{request_hash[:32]}", request_hash


def _normalize_claim_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "claimed":
        return "new"
    if normalized in {"replay", "in_progress", "conflict"}:
        return normalized
    return "new"


def _build_box_revision(box: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(box.get("id") or 0),
        "orderIndex": int(box.get("orderIndex") or 0),
        "x": round(float(box.get("x") or 0.0), 3),
        "y": round(float(box.get("y") or 0.0), 3),
        "width": round(float(box.get("width") or 0.0), 3),
        "height": round(float(box.get("height") or 0.0), 3),
        "text": str(box.get("text") or "").strip(),
        "translation": str(box.get("translation") or "").strip(),
        "note": str(box.get("note") or "").strip(),
    }


def _count_page_translation_state(*, volume_id: str, filename: str) -> dict[str, int]:
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
    text_boxes = list_text_boxes_for_page(page)
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": filename,
        "profile_id": profile_id,
        "replace_existing": bool(replace_existing),
        "detected_count": 0,
        "text_box_count": len(text_boxes),
        "job_id": job_id,
        "job_status": "missing",
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=filename,
        ),
        "idempotency_key": idempotency_key,
        "idempotency_state": "replay",
        "resource_reused": True,
        "message": "Equivalent detection request already completed; reused current page state",
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
    refreshed_boxes = list_text_boxes_for_page(refreshed)
    refreshed_box = find_text_box_by_id(refreshed_boxes, box_id)
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


def _result_json(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = payload.get("result_json") if isinstance(payload, dict) else None
    if isinstance(raw, dict):
        return dict(raw)
    return {}


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

    selected_profile_id = coerce_filename(profile_id)
    page_revision = get_active_page_revision(
        volume_id=volume_id,
        current_filename=resolved_filename,
    )
    idempotency_payload = {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "profile_id": selected_profile_id,
        "replace_existing": bool(replace_existing),
        "page_revision": page_revision,
    }
    idempotency_key, request_hash = _build_auto_idempotency_key(
        namespace="agent.detect_text_boxes",
        payload=idempotency_payload,
    )
    claim = claim_idempotency_key(
        job_type=BOX_DETECTION_JOB_TYPE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    idempotency_state = _normalize_claim_status(str(claim.get("status") or ""))
    if idempotency_state == "conflict":
        return {
            "error": "Equivalent detection request conflicted with different payload",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }
    if idempotency_state == "replay":
        page = load_page(volume_id, resolved_filename)
        current_text_boxes = list_text_boxes_for_page(page)
        if not current_text_boxes:
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
    claimed = idempotency_state == "new"
    if claimed:
        try:
            job_id = create_persisted_utility_workflow(
                workflow_type=BOX_DETECTION_JOB_TYPE,
                request_payload=payload,
                message="Queued (agent tool)",
            )
            if idempotency_key and request_hash:
                job_id = finalize_idempotency_key(
                    job_type=BOX_DETECTION_JOB_TYPE,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resource_id=job_id,
                )
            STORE.broadcast_snapshot()
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

    try:
        finished_run = wait_for_workflow_terminal(
            workflow_run_id=job_id,
            timeout_seconds=_TOOL_JOB_WAIT_TIMEOUT_SECONDS,
            poll_seconds=_TOOL_WORKFLOW_WAIT_POLL_SECONDS,
        )
    except TimeoutError:
        return {
            "status": "queued",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "profile_id": selected_profile_id,
            "replace_existing": bool(replace_existing),
            "job_id": job_id,
            "workflow_run_id": job_id,
            "job_status": "queued",
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
            "resource_reused": idempotency_state != "new",
            "message": "Detection job queued/running; check Jobs panel for live progress",
        }
    except Exception as exc:
        return {
            "error": str(exc).strip() or "Failed while waiting for detection job",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": job_id,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }

    if finished_run is None:
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
    workflow_status = str(finished_run.get("status") or "").strip().lower() or "failed"
    result_json = _result_json(finished_run)
    if workflow_status == "failed":
        return {
            "error": str(finished_run.get("error_message") or "Detection job failed"),
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": job_id,
            "job_status": workflow_status,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
        }
    if workflow_status == "canceled":
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
    if workflow_status in {"queued", "running"}:
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

    detected_count = int(result_json.get("count") or 0)
    page = load_page(volume_id, resolved_filename)
    text_boxes = list_text_boxes_for_page(page)
    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": resolved_filename,
        "profile_id": selected_profile_id,
        "replace_existing": bool(replace_existing),
        "detected_count": detected_count,
        "text_box_count": len(text_boxes),
        "job_id": job_id,
        "workflow_run_id": job_id,
        "job_status": workflow_status,
        "page_revision": get_active_page_revision(
            volume_id=volume_id,
            current_filename=resolved_filename,
        ),
        "idempotency_key": idempotency_key,
        "idempotency_state": idempotency_state,
        "resource_reused": idempotency_state != "new",
    }


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
) -> dict[str, Any]:
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
    payload = {
        "volumeId": volume_id,
        "filename": resolved_filename,
        "detectionProfileId": coerce_filename(detection_profile_id),
        "ocrProfiles": [str(item).strip() for item in (ocr_profiles or []) if str(item).strip()],
        "sourceLanguage": coerce_filename(source_language) or TRANSLATION_SOURCE_LANGUAGE,
        "targetLanguage": coerce_filename(target_language) or TRANSLATION_TARGET_LANGUAGE,
        "modelId": coerce_filename(model_id),
        "forceRerun": bool(force_rerun),
    }
    decision = create_agent_translate_page_job(
        payload=payload,
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

    try:
        finished_run = wait_for_workflow_terminal(
            job_id,
            timeout_seconds=_TOOL_AGENT_PAGE_WAIT_TIMEOUT_SECONDS,
            poll_seconds=_TOOL_AGENT_PAGE_WAIT_POLL_SECONDS,
        )
    except Exception as exc:
        return {
            "error": str(exc).strip() or "Failed while waiting for page-translate workflow",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
        }

    if not isinstance(finished_run, dict):
        return {
            "error": "Page translation workflow could not be found",
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
        }

    workflow_run_id = str(finished_run.get("id") or "").strip() or job_id
    workflow_status = str(finished_run.get("status") or "").strip().lower() or "queued"
    result_json = _result_json(finished_run)

    if workflow_status in {"queued", "running"}:
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

    if workflow_status == "failed":
        return {
            "error": str(
                result_json.get("error_message")
                or finished_run.get("error_message")
                or "Page translation workflow failed"
            ),
            "volume_id": volume_id,
            "filename": resolved_filename,
            "job_id": job_id,
            "workflow_run_id": workflow_run_id,
        }
    if workflow_status == "canceled":
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
    force_rerun: bool = False,
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

    page_revision = get_active_page_revision(
        volume_id=volume_id,
        current_filename=resolved_filename,
    )
    idempotency_payload = {
        "volume_id": volume_id,
        "filename": resolved_filename,
        "profile_id": selected_profile_id,
        "page_revision": page_revision,
        "box_revision": _build_box_revision(target_box),
    }
    idempotency_key, request_hash = _build_auto_idempotency_key(
        namespace="agent.ocr_text_box",
        payload=idempotency_payload,
    )
    claim = claim_idempotency_key(
        job_type=OCR_BOX_WORKFLOW_TYPE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    idempotency_state = _normalize_claim_status(str(claim.get("status") or ""))
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
    claimed = idempotency_state == "new"
    if claimed:
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

    try:
        run = wait_for_workflow_terminal(
            workflow_run_id,
            timeout_seconds=_TOOL_WORKFLOW_WAIT_TIMEOUT_SECONDS,
            poll_seconds=_TOOL_WORKFLOW_WAIT_POLL_SECONDS,
        )
    except TimeoutError:
        run = None

    if run is None:
        run = get_workflow_run(workflow_run_id) if workflow_run_id else None
        if not isinstance(run, dict):
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

    workflow_status = str(run.get("status") or "").strip().lower() or "failed"
    result_json = _result_json(run)
    if workflow_status == "failed":
        return {
            "error": str(run.get("error_message") or "OCR workflow failed").strip(),
            "volume_id": volume_id,
            "filename": resolved_filename,
            "box_id": int(box_id),
            "profile_id": selected_profile_id,
            "workflow_run_id": workflow_run_id,
            "workflow_status": workflow_status,
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
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
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
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
            "idempotency_key": idempotency_key,
            "idempotency_state": idempotency_state,
            "resource_reused": idempotency_state != "new",
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
        "idempotency_key": idempotency_key,
        "idempotency_state": idempotency_state,
        "resource_reused": idempotency_state != "new",
    }
