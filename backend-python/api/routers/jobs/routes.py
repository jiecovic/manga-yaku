# backend-python/api/routers/jobs/routes.py
"""HTTP routes for jobs endpoints."""

from __future__ import annotations

import asyncio

from api.schemas.jobs import (
    CreateAgentTranslatePageJobRequest,
    CreateBoxDetectionJobRequest,
    CreateJobResponse,
    CreateOcrBoxJobRequest,
    CreateOcrPageJobRequest,
    CreatePrepareDatasetJobRequest,
    CreateTrainModelJobRequest,
    CreateTranslateBoxJobRequest,
    CreateTranslatePageJobRequest,
    JobCapability,
    JobsCapabilitiesResponse,
)
from api.services.jobs_creation_service import (
    create_box_detection_workflow,
    create_ocr_box_workflow,
    create_ocr_page_workflow,
    create_prepare_dataset_workflow,
    create_train_model_workflow,
    create_translate_box_workflow,
)
from api.services.jobs_creation_service import (
    create_page_translation_job as create_page_translation_job_record,
)
from api.services.jobs_service import (
    cancel_job as cancel_job_record,
)
from api.services.jobs_service import (
    clear_finished_jobs as clear_finished_jobs_record,
)
from api.services.jobs_service import (
    delete_job as delete_job_record,
)
from api.services.jobs_service import (
    get_job_public,
    get_job_tasks_payload,
    get_resume_page_translation_payload,
    get_training_log_path,
    list_job_public_records,
)
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from infra.jobs.runtime import STORE
from infra.jobs.store import JobPublic
from infra.training.catalog import resolve_prepared_dataset, resolve_training_sources

router = APIRouter(tags=["jobs"])

_TRANSLATE_PAGE_DISABLED_REASON = (
    "Standalone translation page jobs are not supported. Use the page-translation workflow."
)
# Job mode boundary:
# - DB task workflows are persisted and executed by DB workers.
# - Utility jobs are persisted single-task workflows executed by the DB utility worker.
# - Page translation is a persisted workflow executed by a DB worker.

_JOB_CAPABILITIES = JobsCapabilitiesResponse(
    ocr_page=JobCapability(enabled=True),
    ocr_box=JobCapability(enabled=True),
    translate_page=JobCapability(
        enabled=False,
        reason=_TRANSLATE_PAGE_DISABLED_REASON,
    ),
    translate_box=JobCapability(enabled=True),
    agent_translate_page=JobCapability(enabled=True),
)


def _notify_jobs_changed() -> None:
    STORE.broadcast_snapshot()


@router.post("/jobs/ocr_box", response_model=CreateJobResponse)
async def create_ocr_box_job(req: CreateOcrBoxJobRequest) -> CreateJobResponse:
    """Create ocr box job."""
    workflow_run_id = create_ocr_box_workflow(req)
    _notify_jobs_changed()
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/ocr_page", response_model=CreateJobResponse)
async def create_ocr_page_job(
    req: CreateOcrPageJobRequest,
) -> CreateJobResponse:
    """Create ocr page job."""
    workflow_run_id = create_ocr_page_workflow(req)
    _notify_jobs_changed()
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/translate_box", response_model=CreateJobResponse)
async def create_translate_box_job(
    req: CreateTranslateBoxJobRequest,
) -> CreateJobResponse:
    """Create translate box job."""
    workflow_run_id = create_translate_box_workflow(req)
    _notify_jobs_changed()
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/translate_page", response_model=CreateJobResponse)
async def create_translate_page_job(
    req: CreateTranslatePageJobRequest,
) -> CreateJobResponse:
    """Create translate page job."""
    raise HTTPException(
        status_code=409,
        detail=_TRANSLATE_PAGE_DISABLED_REASON,
    )


@router.post("/jobs/agent_translate_page", response_model=CreateJobResponse)
async def create_agent_translate_page_job(
    req: CreateAgentTranslatePageJobRequest,
    request: Request,
) -> CreateJobResponse:
    """Create the persisted page-translation workflow job."""
    decision = create_page_translation_job_record(
        req=req,
        idempotency_key=request.headers.get("Idempotency-Key"),
    )
    _notify_jobs_changed()
    return CreateJobResponse(jobId=decision["job_id"])


@router.get("/jobs/capabilities", response_model=JobsCapabilitiesResponse)
async def get_job_capabilities() -> JobsCapabilitiesResponse:
    """Return job capabilities."""
    return _JOB_CAPABILITIES


@router.post("/jobs/box_detection", response_model=CreateJobResponse)
async def create_box_detection_job(
    req: CreateBoxDetectionJobRequest,
) -> CreateJobResponse:
    """Create box detection job."""
    workflow_run_id = create_box_detection_workflow(req)
    _notify_jobs_changed()
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/prepare_dataset", response_model=CreateJobResponse)
async def create_prepare_dataset_job(
    req: CreatePrepareDatasetJobRequest,
) -> CreateJobResponse:
    """Create prepare dataset job."""
    if not req.sources:
        raise HTTPException(status_code=400, detail="No sources selected")
    try:
        resolve_training_sources(req.sources, allowed_types={"manga109s"})
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Source not found"):
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    workflow_run_id = create_prepare_dataset_workflow(req)
    _notify_jobs_changed()
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/train_model", response_model=CreateJobResponse)
async def create_train_model_job(
    req: CreateTrainModelJobRequest,
) -> CreateJobResponse:
    """Create train model job."""
    try:
        resolve_prepared_dataset(req.dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    workflow_run_id = create_train_model_workflow(req)
    _notify_jobs_changed()
    return CreateJobResponse(jobId=workflow_run_id)


@router.get("/jobs", response_model=list[JobPublic])
async def list_jobs() -> list[JobPublic]:
    """List jobs."""
    return list_job_public_records(store=STORE)


@router.get("/jobs/stream")
async def stream_jobs(request: Request) -> StreamingResponse:
    """Stream jobs."""
    queue = STORE.subscribe()

    async def event_generator():
        try:
            # keep memory and persisted workflow jobs in one snapshot for the client.
            initial = {"jobs": [job.model_dump() for job in list_job_public_records(store=STORE)]}
            yield STORE.format_sse(initial)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                payload = {
                    "jobs": [job.model_dump() for job in list_job_public_records(store=STORE)]
                }
                yield STORE.format_sse(payload)
        finally:
            STORE.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache"}
    headers.update(STORE.cors_headers_for_stream(request))
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/jobs/{job_id}/logs/stream")
async def stream_job_logs(job_id: str, request: Request) -> StreamingResponse:
    """Stream job logs."""
    log_path = get_training_log_path(job_id=job_id, store=STORE)

    async def event_generator():
        offset = 0
        while True:
            if await request.is_disconnected():
                break
            try:
                current_path = get_training_log_path(job_id=job_id, store=STORE) or log_path
            except HTTPException:
                current_path = log_path
            if current_path and current_path.is_file():
                try:
                    with current_path.open("r", encoding="utf-8", errors="replace") as handle:
                        handle.seek(offset)
                        chunk = handle.read()
                        offset = handle.tell()
                    if chunk:
                        for line in chunk.splitlines():
                            yield STORE.format_log_sse(line)
                        await asyncio.sleep(0.1)
                        continue
                except OSError:
                    pass
            yield ": keepalive\n\n"
            await asyncio.sleep(1.0)

    headers = {"Cache-Control": "no-cache"}
    headers.update(STORE.cors_headers_for_stream(request))
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/jobs/{job_id}", response_model=JobPublic)
async def get_job(job_id: str) -> JobPublic:
    """Return job."""
    return get_job_public(job_id=job_id, store=STORE)


@router.get("/jobs/{job_id}/tasks")
async def get_job_tasks(job_id: str) -> dict:
    """Return job tasks."""
    return get_job_tasks_payload(job_id=job_id, store=STORE)


@router.post("/jobs/{job_id}/resume", response_model=CreateJobResponse)
async def resume_job(job_id: str) -> CreateJobResponse:
    """Resume job."""
    payload = get_resume_page_translation_payload(job_id=job_id, store=STORE)
    req = CreateAgentTranslatePageJobRequest(**payload)
    decision = create_page_translation_job_record(
        req=req,
    )
    _notify_jobs_changed()
    return CreateJobResponse(jobId=decision["job_id"])


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    """Cancel job."""
    status = cancel_job_record(job_id=job_id, store=STORE)
    _notify_jobs_changed()
    return {"status": status}


@router.delete("/jobs/finished")
async def clear_finished_jobs() -> dict:
    """Clear finished jobs."""
    deleted = clear_finished_jobs_record(store=STORE)
    if deleted:
        _notify_jobs_changed()
    return {"deleted": deleted}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Delete job."""
    deleted = delete_job_record(job_id=job_id, store=STORE)
    if deleted:
        _notify_jobs_changed()
    return {"deleted": deleted}
