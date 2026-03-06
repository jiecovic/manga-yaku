# backend-python/api/services/jobs_service.py
"""Service-layer helpers for jobs service operations."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from infra.db.workflow_store import (
    cancel_workflow_run,
    delete_terminal_workflow_runs,
    delete_workflow_run,
    get_workflow_run,
    list_task_attempt_events,
    list_task_runs,
)
from infra.jobs.store import JobPublic, JobStatus, JobStore

from .jobs_workflow_helpers import (
    AGENT_WORKFLOW_TYPE,
    PERSISTED_WORKFLOW_TYPES,
    cancel_pending_tasks,
    combined_jobs,
    extract_workflow_run_id,
    restore_agent_payload_from_workflow,
    workflow_run_to_job_public,
    workflow_status_to_job_status,
)


def list_job_public_records(*, store: JobStore) -> list[JobPublic]:
    """List job public records."""
    return combined_jobs(store)


def get_job_public(*, job_id: str, store: JobStore) -> JobPublic:
    """Return job public."""
    job = store.get_job(job_id)
    if job is not None:
        return store.public_job(job)

    run = get_workflow_run(job_id)
    if run and str(run.get("workflow_type")) in PERSISTED_WORKFLOW_TYPES:
        return workflow_run_to_job_public(run, store=store)

    raise HTTPException(status_code=404, detail="Job not found")


def get_job_tasks_payload(*, job_id: str, store: JobStore) -> dict[str, Any]:
    """Return job tasks payload."""
    job = store.get_job(job_id)
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


def get_resume_agent_payload(*, job_id: str, store: JobStore) -> dict:
    """Return resume agent payload."""
    payload: dict

    memory_job = store.get_job(job_id)
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
    return payload


def cancel_job(*, job_id: str, store: JobStore) -> JobStatus:
    """Cancel job."""
    job = store.get_job(job_id)
    if job is not None:
        if job.status in (JobStatus.finished, JobStatus.failed, JobStatus.canceled):
            return job.status

        store.update_job(job, status=JobStatus.canceled, message="Canceled")
        workflow_run_id = extract_workflow_run_id(job)
        if workflow_run_id and job.type in PERSISTED_WORKFLOW_TYPES:
            cancel_workflow_run(workflow_run_id, message="Canceled")
            cancel_pending_tasks(workflow_run_id)
        if job.type == "train_model":
            log_path = store.logs.get(job_id)
            if log_path and log_path.is_file():
                try:
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write("\nCanceled by user.\n")
                except OSError:
                    pass
        return job.status

    run = get_workflow_run(job_id)
    if not run or str(run.get("workflow_type")) not in PERSISTED_WORKFLOW_TYPES:
        raise HTTPException(status_code=404, detail="Job not found")
    status = workflow_status_to_job_status(str(run.get("status") or "failed"))
    if status in (JobStatus.finished, JobStatus.failed, JobStatus.canceled):
        return status
    cancel_workflow_run(job_id, message="Canceled")
    cancel_pending_tasks(job_id)
    return JobStatus.canceled


def clear_finished_jobs(*, store: JobStore) -> int:
    """Clear finished jobs."""
    to_delete = [
        job_id
        for job_id, job in store.jobs.items()
        if job.status in (JobStatus.finished, JobStatus.failed, JobStatus.canceled)
    ]

    for job_id in to_delete:
        store.remove_job(job_id, tombstone=True)

    db_deleted = 0
    for workflow_type in PERSISTED_WORKFLOW_TYPES:
        db_deleted += delete_terminal_workflow_runs(workflow_type=workflow_type)
    return len(to_delete) + db_deleted


def delete_job(*, job_id: str, store: JobStore) -> int:
    """Delete job."""
    job = store.get_job(job_id)
    if job is not None:
        if job.status == JobStatus.running:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a running job. Cancel it first.",
            )

        deleted = 0
        if store.remove_job(job_id, tombstone=True):
            deleted += 1

        workflow_run_id = extract_workflow_run_id(job)
        if workflow_run_id and job.type in PERSISTED_WORKFLOW_TYPES:
            if delete_workflow_run(workflow_run_id):
                deleted += 1
        return deleted or 1

    if delete_workflow_run(job_id):
        return 1

    raise HTTPException(status_code=404, detail="Job not found")
