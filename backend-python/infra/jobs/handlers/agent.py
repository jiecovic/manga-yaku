# backend-python/infra/jobs/handlers/agent.py
"""Job handler implementation for agent tasks."""

from __future__ import annotations

from typing import Any

from core.workflows.agent_translate_page import run_agent_translate_page_workflow
from core.workflows.agent_translate_page.types import AgentTranslateWorkflowSnapshot
from infra.jobs.store import Job, JobStatus, JobStore

from .base import JobHandler


class AgentTranslatePageJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> dict[str, Any]:
        if job.status == JobStatus.canceled:
            return {
                "state": "canceled",
                "stage": "queued",
                "processed": 0,
                "total": 0,
                "updated": 0,
                "orderApplied": False,
                "message": "Canceled",
            }

        def on_progress(snapshot: AgentTranslateWorkflowSnapshot) -> None:
            payload = dict(job.payload)
            if snapshot.workflow_run_id:
                payload["workflowRunId"] = snapshot.workflow_run_id
            if snapshot.stage:
                payload["workflowStage"] = snapshot.stage
            store.update_job(
                job,
                payload=payload,
                progress=snapshot.progress,
                message=snapshot.message,
            )

        def is_canceled() -> bool:
            return job.status == JobStatus.canceled

        result = await run_agent_translate_page_workflow(
            payload=dict(job.payload),
            on_progress=on_progress,
            is_canceled=is_canceled,
        )

        if result.get("state") == "canceled" and job.status != JobStatus.canceled:
            store.update_job(job, status=JobStatus.canceled, progress=100, message="Canceled")

        return result
