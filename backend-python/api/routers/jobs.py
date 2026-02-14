# backend-python/api/routers/jobs.py
from __future__ import annotations

import asyncio
from uuid import uuid4

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
)
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from infra.jobs.store import Job, JobPublic, JobStatus, JobStore
from infra.jobs.worker import job_worker
from infra.training.catalog import resolve_prepared_dataset, resolve_training_sources

router = APIRouter(tags=["jobs"])


STORE = JobStore()
_worker_started = False
_worker_task: asyncio.Task | None = None


@router.on_event("startup")
async def start_job_worker() -> None:
    global _worker_started, _worker_task
    if _worker_started:
        return
    _worker_started = True

    _worker_task = asyncio.create_task(job_worker(STORE))


@router.on_event("shutdown")
async def mark_jobs_shutdown() -> None:
    STORE.shutdown_event.set()
    for job in list(STORE.jobs.values()):
        if job.status == JobStatus.running:
            STORE.update_job(job, status=JobStatus.canceled, message="Canceled (shutdown)")


@router.post("/jobs/ocr_box", response_model=CreateJobResponse)
async def create_ocr_box_job(req: CreateOcrBoxJobRequest) -> CreateJobResponse:
    job_id = str(uuid4())
    now = STORE.now()

    job = Job(
        id=job_id,
        type="ocr_box",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=req.dict(),
        result=None,
        error=None,
    )

    STORE.add_job(job)
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/ocr_page", response_model=CreateJobResponse)
async def create_ocr_page_job(
    req: CreateOcrPageJobRequest,
) -> CreateJobResponse:
    job_id = str(uuid4())
    now = STORE.now()

    job = Job(
        id=job_id,
        type="ocr_page",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=req.dict(),
        result=None,
        error=None,
    )

    STORE.add_job(job)
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/translate_box", response_model=CreateJobResponse)
async def create_translate_box_job(
    req: CreateTranslateBoxJobRequest,
) -> CreateJobResponse:
    job_id = str(uuid4())
    now = STORE.now()

    job = Job(
        id=job_id,
        type="translate_box",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=req.dict(),
        result=None,
        error=None,
    )

    STORE.add_job(job)
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/translate_page", response_model=CreateJobResponse)
async def create_translate_page_job(
    req: CreateTranslatePageJobRequest,
) -> CreateJobResponse:
    job_id = str(uuid4())
    now = STORE.now()

    job = Job(
        id=job_id,
        type="translate_page",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=req.dict(),
        result=None,
        error=None,
    )

    STORE.add_job(job)
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/agent_translate_page", response_model=CreateJobResponse)
async def create_agent_translate_page_job(
    req: CreateAgentTranslatePageJobRequest,
) -> CreateJobResponse:
    job_id = str(uuid4())
    now = STORE.now()

    job = Job(
        id=job_id,
        type="agent_translate_page",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=req.dict(),
        result=None,
        error=None,
        progress=0,
        message="Queued",
    )

    STORE.add_job(job)
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/box_detection", response_model=CreateJobResponse)
async def create_box_detection_job(
    req: CreateBoxDetectionJobRequest,
) -> CreateJobResponse:
    job_id = str(uuid4())
    now = STORE.now()

    job = Job(
        id=job_id,
        type="box_detection",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=req.dict(),
        result=None,
        error=None,
    )

    STORE.add_job(job)
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

    job_id = str(uuid4())
    now = STORE.now()

    job = Job(
        id=job_id,
        type="prepare_dataset",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=req.dict(),
        result=None,
        error=None,
        progress=0,
        message="Queued",
    )

    STORE.add_job(job)
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

    job_id = str(uuid4())
    now = STORE.now()

    job = Job(
        id=job_id,
        type="train_model",
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        payload=req.dict(),
        result=None,
        error=None,
        progress=0,
        message="Queued",
    )

    STORE.add_job(job)
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.get("/jobs", response_model=list[JobPublic])
async def list_jobs() -> list[JobPublic]:
    return [STORE.public_job(job) for job in STORE.jobs.values()]


@router.get("/jobs/stream")
async def stream_jobs(request: Request) -> StreamingResponse:
    queue = STORE.subscribe()

    async def event_generator():
        try:
            yield STORE.format_sse(STORE.snapshot_payload())
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {data}\n\n"
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
    job = STORE.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return STORE.public_job(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    job = STORE.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in (JobStatus.finished, JobStatus.failed, JobStatus.canceled):
        return {"status": job.status}

    STORE.update_job(job, status=JobStatus.canceled, message="Canceled")
    if job.type == "train_model":
        log_path = STORE.logs.get(job_id)
        if log_path and log_path.is_file():
            try:
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write("\nCanceled by user.\n")
            except OSError:
                pass
    return {"status": job.status}


@router.delete("/jobs/finished")
async def clear_finished_jobs() -> dict:
    to_delete = [
        job_id
        for job_id, job in STORE.jobs.items()
        if job.status in (JobStatus.finished, JobStatus.failed, JobStatus.canceled)
    ]

    for job_id in to_delete:
        del STORE.jobs[job_id]
        STORE.logs.pop(job_id, None)

    STORE.broadcast_snapshot()
    return {"deleted": len(to_delete)}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    job = STORE.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == JobStatus.running:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a running job. Cancel it first.",
        )

    del STORE.jobs[job_id]
    STORE.logs.pop(job_id, None)
    STORE.broadcast_snapshot()
    return {"deleted": 1}
