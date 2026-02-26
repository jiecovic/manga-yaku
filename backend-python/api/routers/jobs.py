from __future__ import annotations

import asyncio
import logging
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
from core.usecases.settings.service import get_setting_value
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from infra.db.db_store import load_page
from infra.db.workflow_store import (
    cancel_workflow_run,
    delete_terminal_workflow_runs,
    delete_workflow_run,
    get_workflow_run,
    list_task_attempt_events,
    list_task_runs,
    mark_running_workflows_interrupted,
)
from infra.jobs.db_ocr_worker import run_ocr_db_worker
from infra.jobs.handlers.utils import list_text_boxes
from infra.jobs.store import Job, JobPublic, JobStatus, JobStore
from infra.jobs.worker import job_worker
from infra.training.catalog import resolve_prepared_dataset, resolve_training_sources

from .jobs_workflow_helpers import (
    AGENT_WORKFLOW_TYPE,
    OCR_BOX_WORKFLOW_TYPE,
    OCR_PAGE_WORKFLOW_TYPE,
    PERSISTED_WORKFLOW_TYPES,
    cancel_pending_tasks,
    combined_jobs,
    create_ocr_workflow_with_tasks,
    extract_workflow_run_id,
    normalize_profile_ids,
    resolve_enabled_ocr_profiles,
    restore_agent_payload_from_workflow,
    workflow_run_to_job_public,
    workflow_status_to_job_status,
)

router = APIRouter(tags=["jobs"])
logger = logging.getLogger(__name__)


STORE = JobStore()
_worker_started = False
_worker_task: asyncio.Task | None = None
_db_ocr_worker_task: asyncio.Task | None = None


async def _run_ocr_db_worker_supervisor() -> None:
    backoff_seconds = 1.0
    max_backoff_seconds = 10.0
    while not STORE.shutdown_event.is_set():
        try:
            await run_ocr_db_worker(STORE.shutdown_event)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "OCR DB worker crashed; restarting in %.1fs",
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)


def _enqueue_job(
    *,
    job_type: str,
    payload: dict,
    progress: float | None = None,
    message: str | None = None,
) -> str:
    job_id = str(uuid4())
    now = STORE.now()
    job = Job(
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
    STORE.add_job(job)
    return job_id


@router.on_event("startup")
async def start_job_worker() -> None:
    global _worker_started, _worker_task, _db_ocr_worker_task
    if _worker_started:
        return
    _worker_started = True
    STORE.shutdown_event.clear()

    try:
        mark_running_workflows_interrupted(
            workflow_type=AGENT_WORKFLOW_TYPE,
            message="Interrupted by backend restart",
        )
    except Exception:
        pass
    _worker_task = asyncio.create_task(job_worker(STORE))
    _db_ocr_worker_task = asyncio.create_task(_run_ocr_db_worker_supervisor())


@router.on_event("shutdown")
async def mark_jobs_shutdown() -> None:
    global _worker_started
    STORE.shutdown_event.set()
    for task in (_worker_task, _db_ocr_worker_task):
        if task is not None and not task.done():
            task.cancel()
    _worker_started = False
    for job in list(STORE.jobs.values()):
        if job.status == JobStatus.running:
            STORE.update_job(job, status=JobStatus.canceled, message="Canceled (shutdown)")


@router.post("/jobs/ocr_box", response_model=CreateJobResponse)
async def create_ocr_box_job(req: CreateOcrBoxJobRequest) -> CreateJobResponse:
    volume_id = str(req.volumeId or "").strip()
    filename = str(req.filename or "").strip()
    raw_box_id = req.boxId
    box_id = int(raw_box_id or 0)
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

    workflow_run_id = create_ocr_workflow_with_tasks(
        workflow_type=OCR_BOX_WORKFLOW_TYPE,
        volume_id=volume_id,
        filename=filename,
        request_payload=request_payload,
        total_boxes=1,
        skipped=0,
        processable_boxes=1,
        queued_tasks=queued_tasks,
    )
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/ocr_page", response_model=CreateJobResponse)
async def create_ocr_page_job(
    req: CreateOcrPageJobRequest,
) -> CreateJobResponse:
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
    workflow_run_id = create_ocr_workflow_with_tasks(
        workflow_type=OCR_PAGE_WORKFLOW_TYPE,
        volume_id=volume_id,
        filename=filename,
        request_payload=request_payload,
        total_boxes=total_boxes,
        skipped=skipped,
        processable_boxes=len(processable_boxes),
        queued_tasks=queued_tasks,
    )
    return CreateJobResponse(jobId=workflow_run_id)


@router.post("/jobs/translate_box", response_model=CreateJobResponse)
async def create_translate_box_job(
    req: CreateTranslateBoxJobRequest,
) -> CreateJobResponse:
    use_page_context: bool
    if req.usePageContext is None:
        raw = get_setting_value("translation.single_box.use_context")
        use_page_context = bool(raw) if isinstance(raw, bool) else True
    else:
        use_page_context = bool(req.usePageContext)

    payload = req.dict()
    payload["usePageContext"] = use_page_context
    job_id = _enqueue_job(
        job_type="translate_box",
        payload=payload,
        progress=0,
        message="Queued",
    )
    await STORE.queue.put(job_id)
    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/translate_page", response_model=CreateJobResponse)
async def create_translate_page_job(
    req: CreateTranslatePageJobRequest,
) -> CreateJobResponse:
    raise HTTPException(
        status_code=409,
        detail=(
            "Standalone translation jobs are temporarily disabled during workflow rewrite. "
            "Use agent translate page workflow path."
        ),
    )


@router.post("/jobs/agent_translate_page", response_model=CreateJobResponse)
async def create_agent_translate_page_job(
    req: CreateAgentTranslatePageJobRequest,
) -> CreateJobResponse:
    job_id = _enqueue_job(
        job_type=AGENT_WORKFLOW_TYPE,
        payload=req.dict(),
        progress=0,
        message="Queued",
    )
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.post("/jobs/box_detection", response_model=CreateJobResponse)
async def create_box_detection_job(
    req: CreateBoxDetectionJobRequest,
) -> CreateJobResponse:
    job_id = _enqueue_job(
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

    job_id = _enqueue_job(
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

    job_id = _enqueue_job(
        job_type="train_model",
        payload=req.dict(),
        progress=0,
        message="Queued",
    )
    await STORE.queue.put(job_id)

    return CreateJobResponse(jobId=job_id)


@router.get("/jobs", response_model=list[JobPublic])
async def list_jobs() -> list[JobPublic]:
    return combined_jobs(STORE)


@router.get("/jobs/stream")
async def stream_jobs(request: Request) -> StreamingResponse:
    queue = STORE.subscribe()

    async def event_generator():
        try:
            # keep memory and persisted workflow jobs in one snapshot for the client.
            initial = {"jobs": [job.model_dump() for job in combined_jobs(STORE)]}
            yield STORE.format_sse(initial)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                payload = {"jobs": [job.model_dump() for job in combined_jobs(STORE)]}
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
    job = STORE.get_job(job_id)
    if job is not None:
        return STORE.public_job(job)

    run = get_workflow_run(job_id)
    if run and str(run.get("workflow_type")) in PERSISTED_WORKFLOW_TYPES:
        return workflow_run_to_job_public(run, store=STORE)

    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/jobs/{job_id}/tasks")
async def get_job_tasks(job_id: str) -> dict:
    job = STORE.get_job(job_id)
    workflow_run_id: str | None = None
    if job is not None:
        if job.type not in PERSISTED_WORKFLOW_TYPES:
            raise HTTPException(status_code=400, detail="Task runs are not available for this job type")
        workflow_run_id = extract_workflow_run_id(job)
    else:
        run = get_workflow_run(job_id)
        if not run or str(run.get("workflow_type")) not in PERSISTED_WORKFLOW_TYPES:
            raise HTTPException(status_code=404, detail="Job not found")
        workflow_run_id = str(run.get("id"))

    if not workflow_run_id:
        return {"workflowRunId": None, "tasks": []}

    tasks = list_task_runs(str(workflow_run_id))
    attempt_map = list_task_attempt_events([str(task.get("id")) for task in tasks])
    for task in tasks:
        task_id = str(task.get("id"))
        task["attempt_events"] = attempt_map.get(task_id, [])
    return {
        "workflowRunId": str(workflow_run_id),
        "tasks": tasks,
    }


@router.post("/jobs/{job_id}/resume", response_model=CreateJobResponse)
async def resume_job(job_id: str) -> CreateJobResponse:
    payload: dict

    memory_job = STORE.get_job(job_id)
    if memory_job is not None:
        if memory_job.type != AGENT_WORKFLOW_TYPE:
            raise HTTPException(status_code=400, detail="Only agent jobs support resume")
        if memory_job.status in (JobStatus.queued, JobStatus.running):
            raise HTTPException(status_code=409, detail="Job is already active")
        payload = dict(memory_job.payload or {})
    else:
        run = get_workflow_run(job_id)
        if not run or str(run.get("workflow_type")) != AGENT_WORKFLOW_TYPE:
            raise HTTPException(status_code=404, detail="Job not found")
        if str(run.get("status")) == "running":
            raise HTTPException(status_code=409, detail="Workflow is marked running; cancel it first")
        payload = restore_agent_payload_from_workflow(run)

    if not payload.get("volumeId") or not payload.get("filename"):
        raise HTTPException(status_code=400, detail="Cannot resume: missing workflow input payload")

    payload.pop("workflowRunId", None)
    payload.pop("workflowStage", None)

    new_job_id = _enqueue_job(
        job_type=AGENT_WORKFLOW_TYPE,
        payload=payload,
        progress=0,
        message="Queued (resume)",
    )
    await STORE.queue.put(new_job_id)
    return CreateJobResponse(jobId=new_job_id)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    job = STORE.get_job(job_id)
    if job is not None:
        if job.status in (JobStatus.finished, JobStatus.failed, JobStatus.canceled):
            return {"status": job.status}

        STORE.update_job(job, status=JobStatus.canceled, message="Canceled")
        workflow_run_id = extract_workflow_run_id(job)
        if workflow_run_id and job.type in PERSISTED_WORKFLOW_TYPES:
            cancel_workflow_run(workflow_run_id, message="Canceled")
            cancel_pending_tasks(workflow_run_id)
        if job.type == "train_model":
            log_path = STORE.logs.get(job_id)
            if log_path and log_path.is_file():
                try:
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write("\nCanceled by user.\n")
                except OSError:
                    pass
        return {"status": job.status}

    run = get_workflow_run(job_id)
    if not run or str(run.get("workflow_type")) not in PERSISTED_WORKFLOW_TYPES:
        raise HTTPException(status_code=404, detail="Job not found")
    status = workflow_status_to_job_status(str(run.get("status") or "failed"))
    if status in (JobStatus.finished, JobStatus.failed, JobStatus.canceled):
        return {"status": status}
    cancel_workflow_run(job_id, message="Canceled")
    cancel_pending_tasks(job_id)
    return {"status": JobStatus.canceled}


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

    db_deleted = 0
    for workflow_type in PERSISTED_WORKFLOW_TYPES:
        db_deleted += delete_terminal_workflow_runs(workflow_type=workflow_type)
    STORE.broadcast_snapshot()
    return {"deleted": len(to_delete) + db_deleted}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    job = STORE.get_job(job_id)
    if job is not None:
        if job.status == JobStatus.running:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a running job. Cancel it first.",
            )

        del STORE.jobs[job_id]
        STORE.logs.pop(job_id, None)
        STORE.broadcast_snapshot()
        return {"deleted": 1}

    if delete_workflow_run(job_id):
        return {"deleted": 1}

    raise HTTPException(status_code=404, detail="Job not found")
