# backend-python/api/services/jobs_workflow_helpers.py
"""Service-layer helpers for jobs workflow helpers operations."""

from __future__ import annotations

from core.usecases.ocr.profiles import get_ocr_profile
from infra.db.workflow_store import (
    create_task_runs,
    create_workflow_run,
    list_task_runs,
    list_workflow_runs,
    update_task_run,
    update_workflow_run,
)
from infra.jobs.store import Job, JobPublic, JobStatus, JobStore

AGENT_WORKFLOW_TYPE = "agent_translate_page"
OCR_PAGE_WORKFLOW_TYPE = "ocr_page"
OCR_BOX_WORKFLOW_TYPE = "ocr_box"
TRANSLATE_BOX_WORKFLOW_TYPE = "translate_box"
OCR_TASK_STAGE = "ocr"
TRANSLATE_TASK_STAGE = "translate_box"
PERSISTED_WORKFLOW_TYPES = {
    AGENT_WORKFLOW_TYPE,
    OCR_PAGE_WORKFLOW_TYPE,
    OCR_BOX_WORKFLOW_TYPE,
    TRANSLATE_BOX_WORKFLOW_TYPE,
}


def workflow_status_to_job_status(status: str) -> JobStatus:
    """Handle workflow status to job status."""
    if status == "queued":
        return JobStatus.queued
    if status == "running":
        return JobStatus.running
    if status == "completed":
        return JobStatus.finished
    if status == "canceled":
        return JobStatus.canceled
    return JobStatus.failed


def state_progress_fallback(state: str) -> int:
    """Handle state progress fallback."""
    return {
        "queued": 0,
        "running": 50,
        "detecting_boxes": 5,
        "ocr_running": 50,
        "translating": 80,
        "committing": 90,
        "completed": 100,
        "failed": 100,
        "canceled": 100,
    }.get(state, 0)


def extract_request_payload_from_result(result_json: dict | None) -> dict:
    """Extract request payload from result."""
    if not isinstance(result_json, dict):
        return {}
    request = result_json.get("request")
    if isinstance(request, dict):
        return dict(request)
    return {}


def extract_workflow_run_id(job: JobPublic | Job) -> str | None:
    """Extract workflow run id."""
    payload = dict(job.payload or {})
    workflow_run_id = payload.get("workflowRunId")
    if isinstance(workflow_run_id, str) and workflow_run_id.strip():
        return workflow_run_id.strip()
    result = job.result if isinstance(job.result, dict) else {}
    result_workflow_id = result.get("workflowRunId")
    if isinstance(result_workflow_id, str) and result_workflow_id.strip():
        return result_workflow_id.strip()
    return None


def workflow_run_to_job_public(run: dict, *, store: JobStore) -> JobPublic:
    """Handle workflow run to job public."""
    result_json = run.get("result_json") if isinstance(run.get("result_json"), dict) else {}
    request_payload = extract_request_payload_from_result(result_json)
    payload = dict(request_payload)
    payload.setdefault("volumeId", run.get("volume_id"))
    payload.setdefault("filename", run.get("filename"))
    payload["workflowRunId"] = str(run.get("id"))

    result: dict | None = None
    if result_json:
        result = dict(result_json)
        result.pop("request", None)
        if not result:
            result = None

    status = workflow_status_to_job_status(str(run.get("status") or "failed"))
    error_message = str(run.get("error_message") or "").strip() or None
    message = None
    if result and isinstance(result.get("message"), str):
        message = str(result.get("message"))
    if not message and error_message:
        message = error_message
    if not message:
        message = str(run.get("state") or "queued")

    progress = None
    if result and isinstance(result.get("progress"), int | float):
        progress = float(result["progress"])
    if progress is None:
        progress = float(state_progress_fallback(str(run.get("state") or "queued")))

    created_at = run.get("created_at")
    updated_at = run.get("updated_at")
    created_ts = created_at.timestamp() if hasattr(created_at, "timestamp") else store.now()
    updated_ts = updated_at.timestamp() if hasattr(updated_at, "timestamp") else created_ts

    workflow_type = str(run.get("workflow_type") or "").strip()
    job_type = workflow_type if workflow_type in PERSISTED_WORKFLOW_TYPES else AGENT_WORKFLOW_TYPE

    return JobPublic(
        id=str(run.get("id")),
        type=job_type,
        status=status,
        created_at=created_ts,
        updated_at=updated_ts,
        result=result,
        error=error_message,
        payload=payload,
        progress=progress,
        message=message,
    )


def combined_jobs(store: JobStore) -> list[JobPublic]:
    """Handle combined jobs."""
    memory_jobs = [store.public_job(job) for job in store.jobs.values()]
    workflow_ids_in_memory = {
        workflow_id
        for workflow_id in (extract_workflow_run_id(job) for job in memory_jobs)
        if workflow_id
    }

    try:
        persisted_runs = [
            run
            for run in list_workflow_runs()
            if str(run.get("workflow_type")) in PERSISTED_WORKFLOW_TYPES
        ]
    except Exception:
        persisted_runs = []
    persisted_jobs = [
        workflow_run_to_job_public(run, store=store)
        for run in persisted_runs
        if str(run.get("id")) not in workflow_ids_in_memory
    ]

    jobs = memory_jobs + persisted_jobs
    jobs.sort(key=lambda item: item.created_at, reverse=True)
    return jobs


def restore_agent_payload_from_workflow(run: dict) -> dict:
    """Handle restore agent payload from workflow."""
    result_json = run.get("result_json") if isinstance(run.get("result_json"), dict) else {}
    payload = extract_request_payload_from_result(result_json)
    payload.setdefault("volumeId", run.get("volume_id"))
    payload.setdefault("filename", run.get("filename"))

    if not payload.get("detectionProfileId"):
        detect_id = result_json.get("detectionProfileId")
        if isinstance(detect_id, str) and detect_id.strip():
            payload["detectionProfileId"] = detect_id.strip()

    if not payload.get("ocrProfiles"):
        tasks = list_task_runs(str(run.get("id")), stage=OCR_TASK_STAGE)
        profile_ids = sorted(
            {
                str(task.get("profile_id")).strip()
                for task in tasks
                if task.get("profile_id")
            }
        )
        if profile_ids:
            payload["ocrProfiles"] = profile_ids

    return payload


def cancel_pending_tasks(workflow_run_id: str) -> None:
    """Cancel pending tasks."""
    tasks = list_task_runs(workflow_run_id)
    for task in tasks:
        status = str(task.get("status") or "")
        if status in {"completed", "failed", "canceled", "timed_out"}:
            continue
        update_task_run(
            str(task.get("id")),
            status="canceled",
            finished=True,
            error_code="cancel_requested",
            error_detail="Canceled",
        )


def normalize_profile_ids(
    *,
    raw_profile_ids: list[str] | None,
    fallback_profile_id: str | None = None,
) -> list[str]:
    """Normalize profile ids."""
    out: list[str] = []
    seen: set[str] = set()

    for raw in raw_profile_ids or []:
        profile_id = str(raw).strip()
        if not profile_id or profile_id in seen:
            continue
        seen.add(profile_id)
        out.append(profile_id)

    fallback = str(fallback_profile_id or "").strip()
    if fallback and fallback not in seen:
        out.append(fallback)
    return out


def resolve_enabled_ocr_profiles(profile_ids: list[str]) -> list[str]:
    """Resolve enabled ocr profiles."""
    valid_profiles: list[str] = []
    for profile_id in profile_ids:
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        if not profile.get("enabled", True):
            continue
        valid_profiles.append(profile_id)
    return valid_profiles


def create_ocr_workflow_with_tasks(
    *,
    workflow_type: str,
    volume_id: str,
    filename: str,
    request_payload: dict,
    total_boxes: int,
    skipped: int,
    processable_boxes: int,
    queued_tasks: list[dict],
) -> str:
    """Create ocr workflow with tasks."""
    workflow_run_id = create_workflow_run(
        workflow_type=workflow_type,
        volume_id=volume_id,
        filename=filename,
        state="queued",
        status="queued",
    )

    base_result: dict = {
        "request": request_payload,
        "progress": 0,
        "message": "Queued",
        "total_boxes": total_boxes,
        "skipped": skipped,
        "processable_boxes": processable_boxes,
    }

    if total_boxes <= 0:
        result_json = dict(base_result)
        result_json.update(
            {
                "progress": 100,
                "message": "No text boxes to OCR",
                "processed": 0,
                "total": 0,
                "updated": 0,
                "failures": 0,
                "skipped": 0,
            }
        )
        update_workflow_run(
            workflow_run_id,
            state="completed",
            status="completed",
            result_json=result_json,
        )
        return workflow_run_id

    if processable_boxes <= 0:
        result_json = dict(base_result)
        result_json.update(
            {
                "progress": 100,
                "message": "All text boxes already have OCR",
                "processed": total_boxes,
                "total": total_boxes,
                "updated": 0,
                "failures": 0,
            }
        )
        update_workflow_run(
            workflow_run_id,
            state="completed",
            status="completed",
            result_json=result_json,
        )
        return workflow_run_id

    update_workflow_run(
        workflow_run_id,
        state="queued",
        status="queued",
        result_json=base_result,
    )

    created_tasks = create_task_runs(
        workflow_id=workflow_run_id,
        stage=OCR_TASK_STAGE,
        tasks=queued_tasks,
    )
    if created_tasks == 0:
        result_json = dict(base_result)
        result_json.update(
            {
                "progress": 100,
                "message": "No valid OCR tasks",
                "processed": total_boxes,
                "total": total_boxes,
                "updated": 0,
                "failures": 0,
            }
        )
        update_workflow_run(
            workflow_run_id,
            state="completed",
            status="completed",
            result_json=result_json,
        )

    return workflow_run_id


def create_translate_workflow_with_task(
    *,
    volume_id: str,
    filename: str,
    request_payload: dict,
    box_id: int,
    profile_id: str,
    use_page_context: bool,
) -> str:
    """Create translate workflow with task."""
    workflow_run_id = create_workflow_run(
        workflow_type=TRANSLATE_BOX_WORKFLOW_TYPE,
        volume_id=volume_id,
        filename=filename,
        state="queued",
        status="queued",
    )

    base_result: dict = {
        "request": request_payload,
        "progress": 0,
        "message": "Queued",
    }
    update_workflow_run(
        workflow_run_id,
        state="queued",
        status="queued",
        result_json=base_result,
    )

    created_tasks = create_task_runs(
        workflow_id=workflow_run_id,
        stage=TRANSLATE_TASK_STAGE,
        tasks=[
            {
                "status": "queued",
                "box_id": box_id,
                "profile_id": profile_id,
                "input_json": {
                    "volume_id": volume_id,
                    "filename": filename,
                    "box_id": box_id,
                    "profile_id": profile_id,
                    "use_page_context": bool(use_page_context),
                },
            }
        ],
    )
    if created_tasks == 0:
        result_json = dict(base_result)
        result_json.update(
            {
                "progress": 100,
                "message": "No valid translation tasks",
                "status": "error",
            }
        )
        update_workflow_run(
            workflow_run_id,
            state="failed",
            status="failed",
            error_message="No valid translation tasks",
            result_json=result_json,
        )

    return workflow_run_id
