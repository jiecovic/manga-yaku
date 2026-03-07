# backend-python/infra/jobs/translate_workflow_creation.py
"""Creation helpers for persisted translate-box workflows."""

from __future__ import annotations

from infra.db.workflow_store import create_task_runs, create_workflow_run, update_workflow_run
from infra.jobs.job_modes import TRANSLATE_BOX_WORKFLOW_TYPE

TRANSLATE_TASK_STAGE = "translate_box"


def create_translate_workflow_with_task(
    *,
    volume_id: str,
    filename: str,
    request_payload: dict,
    box_id: int,
    profile_id: str,
    use_page_context: bool,
) -> str:
    """Create a persisted translate-box workflow with one queued task."""
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
