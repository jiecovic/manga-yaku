# backend-python/api/routers/jobs.py
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
    create_ocr_box_workflow,
    create_ocr_page_workflow,
    create_translate_box_workflow,
    enqueue_memory_job,
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
    get_resume_agent_payload,
    list_job_public_records,
)
from api.services.jobs_workflow_helpers import AGENT_WORKFLOW_TYPE
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from infra.jobs.runtime import STORE
from infra.jobs.store import JobPublic
from infra.training.catalog import resolve_prepared_dataset, resolve_training_sources

router = APIRouter(tags=["jobs"])

_TRANSLATE_PAGE_DISABLED_REASON = (
    "Standalone translation jobs are temporarily disabled during workflow rewrite. "
    "Use agent translate page workflow path."
)

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

@router.post("/jobs/ocr_box", response_model=CreateJobResponse)
async def create_ocr_box_job(req: CreateOcrBoxJobRequest) -> CreateJobResponse:
    workflow_run_id = create_ocr_box_workflow(req)
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/ocr_page", response_model=CreateJobResponse)
async def create_ocr_page_job(
    req: CreateOcrPageJobRequest,
) -> CreateJobResponse:
    workflow_run_id = create_ocr_page_workflow(req)
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/translate_box", response_model=CreateJobResponse)
async def create_translate_box_job(
    req: CreateTranslateBoxJobRequest,
) -> CreateJobResponse:
    workflow_run_id = create_translate_box_workflow(req)
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/translate_page", response_model=CreateJobResponse)
async def create_translate_page_job(
    req: CreateTranslatePageJobRequest,
) -> CreateJobResponse:
    raise HTTPException(
        status_code=409,
        detail=_TRANSLATE_PAGE_DISABLED_REASON,
    )


@router.post("/jobs/agent_translate_page", response_model=CreateJobResponse)
async def create_agent_translate_page_job(
    req: CreateAgentTranslatePageJobRequest,
) -> CreateJobResponse:
    job_id = enqueue_memory_job(
        store=STORE,
        job_type=AGENT_WORKFLOW_TYPE,
        payload=req.dict(),
        progress=0,
        message="Queued",
    )
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.get("/jobs/capabilities", response_model=JobsCapabilitiesResponse)
async def get_job_capabilities() -> JobsCapabilitiesResponse:
    return _JOB_CAPABILITIES


@router.post("/jobs/box_detection", response_model=CreateJobResponse)
async def create_box_detection_job(
    req: CreateBoxDetectionJobRequest,
) -> CreateJobResponse:
    job_id = enqueue_memory_job(
        store=STORE,
        job_type="box_detection",
        payload=req.dict(),
    )
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/prepare_dataset", response_model=CreateJobResponse)
async def create_prepare_dataset_job(
    req: CreatePrepareDatasetJobRequest,
) -> CreateJobResponse:
    if not req.sources:
        raise HTTPException(status_code=400, detail="No sources selected")
    try:
        resolve_training_sources(req.sources, allowed_types={"manga109s"})
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Source not found"):
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    job_id = enqueue_memory_job(
        store=STORE,
        job_type="prepare_dataset",
        payload=req.dict(),
        progress=0,
        message="Queued",
    )
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/train_model", response_model=CreateJobResponse)
async def create_train_model_job(
    req: CreateTrainModelJobRequest,
) -> CreateJobResponse:
    try:
        resolve_prepared_dataset(req.dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    job_id = enqueue_memory_job(
        store=STORE,
        job_type="train_model",
        payload=req.dict(),
        progress=0,
        message="Queued",
    )
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.get("/jobs", response_model=list[JobPublic])
async def list_jobs() -> list[JobPublic]:
    return list_job_public_records(store=STORE)


@router.get("/jobs/stream")
async def stream_jobs(request: Request) -> StreamingResponse:
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
                payload = {"jobs": [job.model_dump() for job in list_job_public_records(store=STORE)]}
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
    job = STORE.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.type != "train_model":
        raise HTTPException(status_code=400, detail="Logs available for training jobs only")

    async def event_generator():
        offset = 0
        while True:
            if await request.is_disconnected():
                break
            log_path = STORE.logs.get(job_id)
            if log_path and log_path.is_file():
                try:
                    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
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
    return get_job_public(job_id=job_id, store=STORE)


@router.get("/jobs/{job_id}/tasks")
async def get_job_tasks(job_id: str) -> dict:
    return get_job_tasks_payload(job_id=job_id, store=STORE)


@router.post("/jobs/{job_id}/resume", response_model=CreateJobResponse)
async def resume_job(job_id: str) -> CreateJobResponse:
    payload = get_resume_agent_payload(job_id=job_id, store=STORE)

    new_job_id = enqueue_memory_job(
        store=STORE,
        job_type=AGENT_WORKFLOW_TYPE,
        payload=payload,
        progress=0,
        message="Queued (resume)",
    )
    await STORE.queue.put(new_job_id)
    return CreateJobResponse(jobId=new_job_id)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    status = cancel_job_record(job_id=job_id, store=STORE)
    return {"status": status}


@router.delete("/jobs/finished")
async def clear_finished_jobs() -> dict:
    deleted = clear_finished_jobs_record(store=STORE)
    return {"deleted": deleted}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    deleted = delete_job_record(job_id=job_id, store=STORE)
    return {"deleted": deleted}
