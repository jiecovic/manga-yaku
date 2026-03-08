# backend-python/api/routers/box_detection/routes.py
"""HTTP routes for box detection endpoints."""

from __future__ import annotations

from api.schemas.box_detection import BoxDetectionProfileInfo
from core.usecases.box_detection.engine import detect_boxes_for_page
from core.usecases.box_detection.profiles import list_box_detection_profiles_for_api
from fastapi import APIRouter, HTTPException, Query
from infra.db.store_volume_page import load_page

router = APIRouter(tags=["box-detection"])


def _normalize_task_name(raw: str) -> str | None:
    key = raw.strip().lower()
    if key in {"text", "textbox", "speech"}:
        return "text"
    if key in {"panel", "frame", "panels", "frames"}:
        return "panel"
    if key in {"face", "faces"}:
        return "face"
    if key in {"body", "bodies"}:
        return "body"
    return None


def _extract_tasks(profile: dict) -> list[str]:
    classes = profile.get("classes") or []
    tasks = {task for name in classes if (task := _normalize_task_name(str(name)))}
    return sorted(tasks)


@router.get("/box-detection/profiles", response_model=list[BoxDetectionProfileInfo])
def list_box_detection_profiles() -> list[BoxDetectionProfileInfo]:
    """List box detection profiles."""
    return [
        BoxDetectionProfileInfo(**profile, tasks=_extract_tasks(profile))
        for profile in list_box_detection_profiles_for_api()
    ]


@router.post("/pages/{volume_id}/{filename}/auto-detect")
def auto_detect_boxes_for_page(
    volume_id: str,
    filename: str,
    profile_id: str | None = Query(None),
    task: str | None = Query(None),
    replace_existing: bool = Query(False),
):
    """
    Run YOLO text box detection on a single page.

    - volume_id: folder under data/volumes/
    - filename: e.g. "006.png"
    - profile_id: which box-detection profile to use
    - replace_existing: if True, existing boxes are discarded; default preserves boxes
    """
    try:
        # This will load image, run YOLO, update page state, and return new boxes
        _ = detect_boxes_for_page(
            volume_id=volume_id,
            filename=filename,
            profile_id=profile_id,
            task=task,
            replace_existing=replace_existing,
        )
        # Reload full page state (including boxes) to return to the client
        page = load_page(volume_id, filename)
        return page

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    except ValueError as e:
        # e.g. unknown profile id
        raise HTTPException(status_code=400, detail=str(e)) from e

    except RuntimeError as e:
        # e.g. YOLO not available, model file missing, profile disabled
        raise HTTPException(status_code=500, detail=str(e)) from e

    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}") from e
