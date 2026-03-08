# backend-python/core/usecases/ocr/workflow_creation.py
"""Creation helpers for persisted OCR workflows."""

from __future__ import annotations

from dataclasses import dataclass

from core.usecases.ocr.profiles import get_ocr_profile
from core.usecases.page_boxes import list_text_boxes
from infra.db.store_volume_page import load_page
from infra.db.workflow_store import create_task_runs, create_workflow_run, update_workflow_run
from infra.jobs.job_modes import OCR_BOX_WORKFLOW_TYPE, OCR_PAGE_WORKFLOW_TYPE

OCR_TASK_STAGE = "ocr"


@dataclass(frozen=True)
class OcrBoxWorkflowInput:
    profile_id: str
    volume_id: str
    filename: str
    x: float
    y: float
    width: float
    height: float
    box_id: int
    box_order: int | None = None


@dataclass(frozen=True)
class OcrPageWorkflowInput:
    profile_ids: list[str]
    volume_id: str
    filename: str
    skip_existing: bool = True


def normalize_profile_ids(
    *,
    raw_profile_ids: list[str] | None,
    fallback_profile_id: str | None = None,
) -> list[str]:
    """Normalize OCR profile ids while preserving order."""
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
    """Return only enabled OCR profiles."""
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


def _create_ocr_workflow_with_tasks(
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


def create_ocr_box_workflow(data: OcrBoxWorkflowInput) -> str:
    """Create one persisted OCR workflow for a single box."""
    volume_id = str(data.volume_id or "").strip()
    filename = str(data.filename or "").strip()
    box_id = int(data.box_id or 0)
    if box_id <= 0:
        raise ValueError("boxId is required for OCR box workflow")

    profile_ids = normalize_profile_ids(raw_profile_ids=[str(data.profile_id or "").strip()])
    valid_profiles = resolve_enabled_ocr_profiles(profile_ids)
    if not valid_profiles:
        raise ValueError("No enabled OCR profile selected")

    profile_id = valid_profiles[0]
    request_payload = {
        "profileId": profile_id,
        "profileIds": [profile_id],
        "volumeId": volume_id,
        "filename": filename,
        "x": float(data.x),
        "y": float(data.y),
        "width": float(data.width),
        "height": float(data.height),
        "boxId": box_id,
        "boxOrder": data.box_order,
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
                "x": float(data.x),
                "y": float(data.y),
                "width": float(data.width),
                "height": float(data.height),
            },
        }
    ]
    return _create_ocr_workflow_with_tasks(
        workflow_type=OCR_BOX_WORKFLOW_TYPE,
        volume_id=volume_id,
        filename=filename,
        request_payload=request_payload,
        total_boxes=1,
        skipped=0,
        processable_boxes=1,
        queued_tasks=queued_tasks,
    )


def create_ocr_page_workflow(data: OcrPageWorkflowInput) -> str:
    """Create a persisted OCR workflow for all text boxes on a page."""
    profile_ids = normalize_profile_ids(
        raw_profile_ids=list(data.profile_ids or []),
        fallback_profile_id="manga_ocr_default",
    )
    valid_profiles = resolve_enabled_ocr_profiles(profile_ids)
    if not valid_profiles:
        raise ValueError("No enabled OCR profiles selected")

    volume_id = str(data.volume_id or "").strip()
    filename = str(data.filename or "").strip()
    skip_existing = bool(data.skip_existing)

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

    return _create_ocr_workflow_with_tasks(
        workflow_type=OCR_PAGE_WORKFLOW_TYPE,
        volume_id=volume_id,
        filename=filename,
        request_payload=request_payload,
        total_boxes=total_boxes,
        skipped=skipped,
        processable_boxes=len(processable_boxes),
        queued_tasks=queued_tasks,
    )
