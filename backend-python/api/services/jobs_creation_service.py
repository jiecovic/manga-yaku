# backend-python/api/services/jobs_creation_service.py
"""Service-layer helpers for jobs creation service operations."""

from __future__ import annotations

from typing import TypedDict

from api.schemas.jobs import (
    CreateAgentTranslatePageJobRequest,
    CreateBoxDetectionJobRequest,
    CreateOcrBoxJobRequest,
    CreateOcrPageJobRequest,
    CreatePrepareDatasetJobRequest,
    CreateTrainModelJobRequest,
    CreateTranslateBoxJobRequest,
)
from fastapi import HTTPException
from infra.jobs.operations import (
    enqueue_box_detection_operation,
    enqueue_ocr_box_operation,
    enqueue_ocr_page_operation,
    enqueue_page_translation_operation,
    enqueue_prepare_dataset_operation,
    enqueue_train_model_operation,
    enqueue_translate_box_operation,
)


class PageTranslationEnqueueResult(TypedDict):
    """Result tuple for creating/reusing a page-translation workflow."""

    job_id: str
    queued: bool


def create_page_translation_job(
    *,
    req: CreateAgentTranslatePageJobRequest,
    idempotency_key: str | None = None,
) -> PageTranslationEnqueueResult:
    """Create or reuse a page-translation workflow."""
    decision = enqueue_page_translation_operation(
        req.model_dump(),
        idempotency_key=idempotency_key,
    )
    status = str(decision.get("status") or "")
    if status == "invalid":
        raise HTTPException(status_code=400, detail=decision.get("detail") or "Invalid request")
    if status in {"conflict", "in_progress"}:
        raise HTTPException(status_code=409, detail=decision.get("detail") or "Job conflict")
    if status == "error":
        raise HTTPException(
            status_code=500, detail=decision.get("detail") or "Failed to enqueue job"
        )
    job_id = str(decision.get("job_id") or "").strip()
    if not job_id:
        raise HTTPException(status_code=500, detail="Failed to resolve job id")
    return {"job_id": job_id, "queued": bool(decision.get("queued"))}


def create_box_detection_workflow(req: CreateBoxDetectionJobRequest) -> str:
    """Create a persisted box-detection utility workflow."""
    return enqueue_box_detection_operation(req.model_dump())


def create_prepare_dataset_workflow(req: CreatePrepareDatasetJobRequest) -> str:
    """Create a persisted dataset-preparation utility workflow."""
    return enqueue_prepare_dataset_operation(req.model_dump())


def create_train_model_workflow(req: CreateTrainModelJobRequest) -> str:
    """Create a persisted training utility workflow."""
    return enqueue_train_model_operation(req.model_dump())


def create_ocr_box_workflow(req: CreateOcrBoxJobRequest) -> str:
    """Create ocr box workflow."""
    try:
        return enqueue_ocr_box_operation(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_ocr_page_workflow(req: CreateOcrPageJobRequest) -> str:
    """Create ocr page workflow."""
    try:
        return enqueue_ocr_page_operation(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_translate_box_workflow(req: CreateTranslateBoxJobRequest) -> str:
    """Create translate box workflow."""
    try:
        return enqueue_translate_box_operation(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
