# backend-python/api/services/jobs_creation_service.py
"""Service-layer helpers for jobs creation service operations."""

from __future__ import annotations

from typing import TypedDict

from fastapi import HTTPException

from api.schemas.jobs import (
    CreateAgentTranslatePageJobRequest,
    CreateBoxDetectionJobRequest,
    CreateOcrBoxJobRequest,
    CreateOcrPageJobRequest,
    CreatePrepareDatasetJobRequest,
    CreateTrainModelJobRequest,
    CreateTranslateBoxJobRequest,
)
from core.usecases.ocr.workflow_creation import (
    OcrBoxWorkflowInput,
    OcrPageWorkflowInput,
)
from core.usecases.ocr.workflow_creation import (
    create_ocr_box_workflow as create_persisted_ocr_box_workflow,
)
from core.usecases.ocr.workflow_creation import (
    create_ocr_page_workflow as create_persisted_ocr_page_workflow,
)
from core.usecases.settings.service import get_setting_value
from core.usecases.translation.profiles import get_translation_profile
from infra.jobs.agent_translate_creation import (
    create_agent_translate_page_job as create_shared_agent_translate_page_job,
)
from infra.jobs.job_modes import (
    BOX_DETECTION_JOB_TYPE,
    PREPARE_DATASET_JOB_TYPE,
    TRAIN_MODEL_JOB_TYPE,
)
from infra.jobs.store import JobStore
from infra.jobs.utility_workflow_creation import create_persisted_utility_workflow

from .jobs_workflow_helpers import (
    create_translate_workflow_with_task,
)


class AgentTranslatePageEnqueueResult(TypedDict):
    """Result tuple for creating/reusing an agent translate page job."""

    job_id: str
    queued: bool


def create_agent_translate_page_job(
    *,
    store: JobStore,
    req: CreateAgentTranslatePageJobRequest,
    idempotency_key: str | None = None,
) -> AgentTranslatePageEnqueueResult:
    """Create or reuse an agent translate-page job."""
    decision = create_shared_agent_translate_page_job(
        store=store,
        payload=req.model_dump(),
        idempotency_key=idempotency_key,
    )
    status = str(decision.get("status") or "")
    if status == "invalid":
        raise HTTPException(status_code=400, detail=decision.get("detail") or "Invalid request")
    if status in {"conflict", "in_progress"}:
        raise HTTPException(status_code=409, detail=decision.get("detail") or "Job conflict")
    if status == "error":
        raise HTTPException(status_code=500, detail=decision.get("detail") or "Failed to enqueue job")
    job_id = str(decision.get("job_id") or "").strip()
    if not job_id:
        raise HTTPException(status_code=500, detail="Failed to resolve job id")
    return {"job_id": job_id, "queued": bool(decision.get("queued"))}


def create_box_detection_workflow(req: CreateBoxDetectionJobRequest) -> str:
    """Create a persisted box-detection utility workflow."""
    return create_persisted_utility_workflow(
        workflow_type=BOX_DETECTION_JOB_TYPE,
        request_payload=req.model_dump(),
    )


def create_prepare_dataset_workflow(req: CreatePrepareDatasetJobRequest) -> str:
    """Create a persisted dataset-preparation utility workflow."""
    return create_persisted_utility_workflow(
        workflow_type=PREPARE_DATASET_JOB_TYPE,
        request_payload=req.model_dump(),
    )


def create_train_model_workflow(req: CreateTrainModelJobRequest) -> str:
    """Create a persisted training utility workflow."""
    return create_persisted_utility_workflow(
        workflow_type=TRAIN_MODEL_JOB_TYPE,
        request_payload=req.model_dump(),
    )


def create_ocr_box_workflow(req: CreateOcrBoxJobRequest) -> str:
    """Create ocr box workflow."""
    try:
        return create_persisted_ocr_box_workflow(
            OcrBoxWorkflowInput(
                profile_id=str(req.profileId or "").strip(),
                volume_id=str(req.volumeId or "").strip(),
                filename=str(req.filename or "").strip(),
                x=float(req.x),
                y=float(req.y),
                width=float(req.width),
                height=float(req.height),
                box_id=int(req.boxId or 0),
                box_order=req.boxOrder,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_ocr_page_workflow(req: CreateOcrPageJobRequest) -> str:
    """Create ocr page workflow."""
    raw_profile_ids = req.profileIds if isinstance(req.profileIds, list) else []
    selected_profile_id = str(req.profileId or "").strip()
    if not selected_profile_id and raw_profile_ids:
        selected_profile_id = str(raw_profile_ids[0] or "").strip()
    try:
        return create_persisted_ocr_page_workflow(
            OcrPageWorkflowInput(
                profile_ids=[selected_profile_id] if selected_profile_id else list(raw_profile_ids),
                volume_id=str(req.volumeId or "").strip(),
                filename=str(req.filename or "").strip(),
                skip_existing=bool(req.skipExisting),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_translate_box_workflow(req: CreateTranslateBoxJobRequest) -> str:
    """Create translate box workflow."""
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
