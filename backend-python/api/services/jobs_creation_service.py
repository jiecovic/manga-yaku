# backend-python/api/services/jobs_creation_service.py
"""Service-layer helpers for jobs creation service operations."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, TypedDict
from uuid import uuid4

from fastapi import HTTPException

from api.schemas.jobs import (
    CreateAgentTranslatePageJobRequest,
    CreateOcrBoxJobRequest,
    CreateOcrPageJobRequest,
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
from infra.db.idempotency_store import (
    claim_idempotency_key,
    finalize_idempotency_key,
    release_idempotency_claim,
)
from infra.db.workflow_store import find_latest_active_workflow_run
from infra.jobs.job_modes import (
    AGENT_WORKFLOW_TYPE,
)
from infra.jobs.store import Job, JobStatus, JobStore
from infra.logging.correlation import append_correlation

from .jobs_workflow_helpers import (
    create_translate_workflow_with_task,
)

_ACTIVE_MEMORY_STATUSES = {JobStatus.queued, JobStatus.running}
logger = logging.getLogger(__name__)


class AgentTranslatePageEnqueueResult(TypedDict):
    """Result tuple for creating/reusing an agent translate page job."""

    job_id: str
    queued: bool


def _normalize_optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_profile_ids(raw_profile_ids: list[str] | None) -> list[str] | None:
    if not isinstance(raw_profile_ids, list):
        return None
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_profile_ids:
        profile_id = str(raw or "").strip()
        if not profile_id or profile_id in seen:
            continue
        seen.add(profile_id)
        out.append(profile_id)
    return out or None


def _normalize_agent_translate_payload(req: CreateAgentTranslatePageJobRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "volumeId": str(req.volumeId or "").strip(),
        "filename": str(req.filename or "").strip(),
        "detectionProfileId": _normalize_optional_str(req.detectionProfileId),
        "ocrProfiles": _normalize_profile_ids(req.ocrProfiles),
        "sourceLanguage": _normalize_optional_str(req.sourceLanguage),
        "targetLanguage": _normalize_optional_str(req.targetLanguage),
        "modelId": _normalize_optional_str(req.modelId),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _idempotency_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_idempotency_key(raw_key: str | None) -> str | None:
    key = str(raw_key or "").strip()
    return key or None


def _find_active_memory_agent_job_id(
    *,
    store: JobStore,
    volume_id: str,
    filename: str,
) -> str | None:
    active_jobs = [
        job
        for job in store.jobs.values()
        if job.type == AGENT_WORKFLOW_TYPE
        and job.status in _ACTIVE_MEMORY_STATUSES
        and str(job.payload.get("volumeId") or "").strip() == volume_id
        and str(job.payload.get("filename") or "").strip() == filename
    ]
    if not active_jobs:
        return None
    active_jobs.sort(key=lambda item: (item.updated_at, item.created_at), reverse=True)
    return active_jobs[0].id


def _find_active_persisted_agent_run_id(
    *,
    volume_id: str,
    filename: str,
) -> str | None:
    try:
        run = find_latest_active_workflow_run(
            workflow_type=AGENT_WORKFLOW_TYPE,
            volume_id=volume_id,
            filename=filename,
        )
    except Exception:
        logger.exception(
            append_correlation(
                "Failed to inspect active persisted agent workflow",
                {
                    "component": "jobs.creation.agent_translate_page",
                    "volume_id": volume_id,
                    "filename": filename,
                },
            )
        )
        return None
    if not isinstance(run, dict):
        return None
    run_id = str(run.get("id") or "").strip()
    return run_id or None


def create_agent_translate_page_job(
    *,
    store: JobStore,
    req: CreateAgentTranslatePageJobRequest,
    idempotency_key: str | None = None,
) -> AgentTranslatePageEnqueueResult:
    """
    Create or reuse an agent translate-page job.

    Rules:
    - Prevent duplicate active runs for the same page.
    - Optionally enforce request idempotency via Idempotency-Key.
    - Allow re-translate after terminal completion.
    """
    payload = _normalize_agent_translate_payload(req)
    volume_id = str(payload.get("volumeId") or "").strip()
    filename = str(payload.get("filename") or "").strip()
    if not volume_id or not filename:
        raise HTTPException(status_code=400, detail="volumeId and filename are required")

    active_memory_id = _find_active_memory_agent_job_id(
        store=store,
        volume_id=volume_id,
        filename=filename,
    )
    if active_memory_id:
        return {"job_id": active_memory_id, "queued": False}

    active_run_id = _find_active_persisted_agent_run_id(
        volume_id=volume_id,
        filename=filename,
    )
    if active_run_id:
        return {"job_id": active_run_id, "queued": False}

    force_rerun = bool(req.forceRerun)
    normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
    request_hash = _idempotency_request_hash(payload)
    claimed = False
    if normalized_idempotency_key and not force_rerun:
        claim = claim_idempotency_key(
            job_type=AGENT_WORKFLOW_TYPE,
            idempotency_key=normalized_idempotency_key,
            request_hash=request_hash,
        )
        claim_status = str(claim.get("status") or "")
        if claim_status == "replay":
            resource_id = str(claim.get("resource_id") or "").strip()
            if resource_id:
                return {"job_id": resource_id, "queued": False}
        elif claim_status == "conflict":
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key conflicts with a different request payload",
            )
        elif claim_status == "in_progress":
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key request is already in progress",
            )
        claimed = claim_status == "claimed"

    try:
        job_id = enqueue_memory_job(
            store=store,
            job_type=AGENT_WORKFLOW_TYPE,
            payload=payload,
            progress=0,
            message="Queued",
        )
    except Exception:
        if normalized_idempotency_key and claimed:
            release_idempotency_claim(
                job_type=AGENT_WORKFLOW_TYPE,
                idempotency_key=normalized_idempotency_key,
                request_hash=request_hash,
            )
        raise

    if normalized_idempotency_key and claimed:
        try:
            resource_id = finalize_idempotency_key(
                job_type=AGENT_WORKFLOW_TYPE,
                idempotency_key=normalized_idempotency_key,
                request_hash=request_hash,
                resource_id=job_id,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key conflicts with a different request payload",
            ) from exc
        if resource_id != job_id:
            # Another request finalized first; drop newly created duplicate before queueing.
            if store.jobs.pop(job_id, None) is not None:
                store.broadcast_snapshot()
            return {"job_id": resource_id, "queued": False}

    return {"job_id": job_id, "queued": True}


def enqueue_memory_job(
    *,
    store: JobStore,
    job_type: str,
    payload: dict,
    progress: float | None = None,
    message: str | None = None,
) -> str:
    """Handle enqueue memory job."""
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
