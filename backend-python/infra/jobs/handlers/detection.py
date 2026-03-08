# backend-python/infra/jobs/handlers/detection.py
"""Job handler implementation for detection tasks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from core.usecases.box_detection.profiles.registry import (
    get_box_detection_profile,
    pick_default_box_detection_profile_id,
)
from core.usecases.box_detection.runtime.engine import (
    detect_boxes_for_page,
)
from core.usecases.box_detection.runtime.inference import (
    resolve_detection_thresholds,
)
from infra.jobs.exceptions import JobCanceled
from infra.jobs.store import Job, JobStore

from .base import JobHandler


class BoxDetectionResult(TypedDict):
    boxes: list[dict[str, Any]]
    task: str | None
    count: int


@dataclass(frozen=True)
class BoxDetectionInput:
    volume_id: str
    filename: str
    profile_id: str | None
    task: str | None
    replace_existing: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> BoxDetectionInput:
        return cls(
            volume_id=str(payload["volumeId"]),
            filename=str(payload["filename"]),
            profile_id=payload.get("profileId"),
            task=payload.get("task"),
            replace_existing=bool(payload.get("replaceExisting", True)),
        )


class BoxDetectionJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> BoxDetectionResult:
        data = BoxDetectionInput.from_payload(dict(job.payload))
        raw_should_stop = getattr(store, "should_stop", None)
        stop_check = raw_should_stop if callable(raw_should_stop) else None
        if stop_check is None:
            raw_is_canceled = getattr(store, "is_canceled", None)
            stop_check = raw_is_canceled if callable(raw_is_canceled) else None
        boxes = await asyncio.to_thread(
            detect_boxes_for_page,
            data.volume_id,
            data.filename,
            data.profile_id,
            task=data.task,
            replace_existing=data.replace_existing,
            is_canceled=stop_check,
        )
        if callable(stop_check) and stop_check():
            raise JobCanceled("Canceled")
        conf_iou_label = ""
        profile_id = data.profile_id or pick_default_box_detection_profile_id()
        if profile_id:
            try:
                profile = get_box_detection_profile(profile_id)
                conf_th, iou_th = resolve_detection_thresholds(profile)
                conf_iou_label = f" (conf={conf_th:.2f}, iou={iou_th:.2f})"
            except Exception:
                conf_iou_label = ""
        task_label = data.task or ""
        box_count = len(boxes) if isinstance(boxes, list) else 0
        if task_label:
            message = f"Detected {box_count} {task_label} boxes{conf_iou_label}"
        else:
            message = f"Detected {box_count} boxes{conf_iou_label}"
        store.update_job(job, message=message)
        return {
            "boxes": boxes,
            "task": data.task,
            "count": box_count,
        }
