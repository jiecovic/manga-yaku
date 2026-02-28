# backend-python/api/services/jobs_creation_service.py
"""Service-layer helpers for jobs creation service operations."""

from __future__ import annotations

from uuid import uuid4

from api.schemas.jobs import (
    CreateOcrBoxJobRequest,
    CreateOcrPageJobRequest,
    CreateTranslateBoxJobRequest,
)
from core.usecases.settings.service import get_setting_value
from core.usecases.translation.profiles import get_translation_profile
from fastapi import HTTPException
from infra.db.db_store import load_page
from infra.jobs.handlers.utils import list_text_boxes
from infra.jobs.store import Job, JobStatus, JobStore

from .jobs_workflow_helpers import (
    OCR_BOX_WORKFLOW_TYPE,
    OCR_PAGE_WORKFLOW_TYPE,
    create_ocr_workflow_with_tasks,
    create_translate_workflow_with_task,
    normalize_profile_ids,
    resolve_enabled_ocr_profiles,
)


def enqueue_memory_job(
    *,
    store: JobStore,
    job_type: str,
    payload: dict,
    progress: float | None = None,
    message: str | None = None,
) -> str:
    job_id = str(uuid4())
    now = store.now()
    store.add_job(
        Job(
            id=job_id,
            type=job_type,
            status=JobStatus.queued,
            created_at=now,
            updated_at=now,
            payload=payload,
            result=None,
            error=None,
            progress=progress,
            message=message,
        )
    )
    return job_id


def create_ocr_box_workflow(req: CreateOcrBoxJobRequest) -> str:
    volume_id = str(req.volumeId or "").strip()
    filename = str(req.filename or "").strip()
    box_id = int(req.boxId or 0)
    if box_id <= 0:
        raise HTTPException(status_code=400, detail="boxId is required for OCR box workflow")

    profile_ids = normalize_profile_ids(
        raw_profile_ids=[str(req.profileId or "").strip()],
    )
    valid_profiles = resolve_enabled_ocr_profiles(profile_ids)
    if not valid_profiles:
        raise HTTPException(status_code=400, detail="No enabled OCR profile selected")

    profile_id = valid_profiles[0]
    request_payload = {
        "profileId": profile_id,
        "profileIds": [profile_id],
        "volumeId": volume_id,
        "filename": filename,
        "x": float(req.x),
        "y": float(req.y),
        "width": float(req.width),
        "height": float(req.height),
        "boxId": box_id,
        "boxOrder": req.boxOrder,
    }
    queued_tasks = [
        {
            "status": "queued",
            "box_id": box_id,
            "profile_id": profile_id,
            "input_json": {
                "volume_id": volume_id,
                "filename": filename,
                "box_id": box_id,
                "profile_id": profile_id,
                "x": float(req.x),
                "y": float(req.y),
                "width": float(req.width),
                "height": float(req.height),
            },
        }
    ]

    return create_ocr_workflow_with_tasks(
        workflow_type=OCR_BOX_WORKFLOW_TYPE,
        volume_id=volume_id,
        filename=filename,
        request_payload=request_payload,
        total_boxes=1,
        skipped=0,
        processable_boxes=1,
        queued_tasks=queued_tasks,
    )


def create_ocr_page_workflow(req: CreateOcrPageJobRequest) -> str:
    raw_profile_ids = req.profileIds if isinstance(req.profileIds, list) else []
    selected_profile_id = str(req.profileId or "").strip()
    if not selected_profile_id and raw_profile_ids:
        selected_profile_id = str(raw_profile_ids[0] or "").strip()
    profile_ids = normalize_profile_ids(
        raw_profile_ids=[selected_profile_id] if selected_profile_id else None,
        fallback_profile_id="manga_ocr_default",
    )
    valid_profiles = resolve_enabled_ocr_profiles(profile_ids)
    if not valid_profiles:
        raise HTTPException(status_code=400, detail="No enabled OCR profiles selected")

    volume_id = str(req.volumeId or "").strip()
    filename = str(req.filename or "").strip()
    skip_existing = bool(req.skipExisting)

    page = load_page(volume_id, filename)
    text_boxes = list_text_boxes(page)
    total_boxes = len(text_boxes)
    processable_boxes: list[dict] = []
    skipped = 0
    for box in text_boxes:
        # Keep page OCR idempotent when skip-existing is enabled.
        if skip_existing and str(box.get("text") or "").strip():
            skipped += 1
            continue
        processable_boxes.append(box)

    request_payload = {
        "profileId": valid_profiles[0],
        "profileIds": valid_profiles,
        "volumeId": volume_id,
        "filename": filename,
        "skipExisting": skip_existing,
    }
    queued_tasks: list[dict] = []
    for box in processable_boxes:
        box_id = int(box.get("id") or 0)
        if box_id <= 0:
            continue
        for profile_id in valid_profiles:
            queued_tasks.append(
                {
                    "status": "queued",
                    "box_id": box_id,
                    "profile_id": profile_id,
                    "input_json": {
                        "volume_id": volume_id,
                        "filename": filename,
                        "box_id": box_id,
                        "profile_id": profile_id,
                        "x": float(box.get("x") or 0.0),
                        "y": float(box.get("y") or 0.0),
                        "width": float(box.get("width") or 0.0),
                        "height": float(box.get("height") or 0.0),
                    },
                }
            )

    return create_ocr_workflow_with_tasks(
        workflow_type=OCR_PAGE_WORKFLOW_TYPE,
        volume_id=volume_id,
        filename=filename,
        request_payload=request_payload,
        total_boxes=total_boxes,
        skipped=skipped,
        processable_boxes=len(processable_boxes),
        queued_tasks=queued_tasks,
    )


def create_translate_box_workflow(req: CreateTranslateBoxJobRequest) -> str:
    profile_id = str(req.profileId or "").strip()
    if not profile_id:
        raise HTTPException(status_code=400, detail="profileId is required")
    try:
        profile = get_translation_profile(profile_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not profile.get("enabled", True):
        raise HTTPException(status_code=400, detail="Selected translation profile is disabled")

    volume_id = str(req.volumeId or "").strip()
    filename = str(req.filename or "").strip()
    box_id = int(req.boxId or 0)
    if box_id <= 0:
        raise HTTPException(status_code=400, detail="boxId is required for translation workflow")

    use_page_context: bool
    if req.usePageContext is None:
        raw = get_setting_value("translation.single_box.use_context")
        use_page_context = bool(raw) if isinstance(raw, bool) else True
    else:
        use_page_context = bool(req.usePageContext)

    request_payload = {
        "profileId": profile_id,
        "volumeId": volume_id,
        "filename": filename,
        "boxId": box_id,
        "usePageContext": use_page_context,
        "boxOrder": req.boxOrder,
    }
    return create_translate_workflow_with_task(
        volume_id=volume_id,
        filename=filename,
        request_payload=request_payload,
        box_id=box_id,
        profile_id=profile_id,
        use_page_context=use_page_context,
    )
