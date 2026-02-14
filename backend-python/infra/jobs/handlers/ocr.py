# backend-python/infra/jobs/handlers/ocr.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from core.usecases.ocr.engine import run_ocr_box
from core.usecases.ocr.profiles import get_ocr_profile
from infra.db.db_store import load_page
from infra.jobs.store import Job, JobStatus, JobStore

from .base import JobHandler
from .utils import apply_model_metadata, list_text_boxes, make_snippet


class OcrBoxResult(TypedDict):
    text: str


class OcrPageResult(TypedDict):
    processed: int
    total: int
    skipped: int
    failures: int
    updated: int


@dataclass(frozen=True)
class OcrBoxInput:
    profile_id: str
    volume_id: str
    filename: str
    x: float
    y: float
    width: float
    height: float
    box_id: int | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> OcrBoxInput:
        raw_box_id = payload.get("boxId")
        box_id = int(raw_box_id) if raw_box_id not in (None, "") else None
        if box_id == 0:
            box_id = None
        return cls(
            profile_id=str(payload["profileId"]),
            volume_id=str(payload["volumeId"]),
            filename=str(payload["filename"]),
            x=float(payload["x"]),
            y=float(payload["y"]),
            width=float(payload["width"]),
            height=float(payload["height"]),
            box_id=box_id,
        )


@dataclass(frozen=True)
class OcrPageInput:
    profile_id: str
    volume_id: str
    filename: str
    skip_existing: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> OcrPageInput:
        return cls(
            profile_id=str(payload.get("profileId") or "manga_ocr_default"),
            volume_id=str(payload["volumeId"]),
            filename=str(payload["filename"]),
            skip_existing=bool(payload.get("skipExisting", True)),
        )


class OcrBoxJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> OcrBoxResult:
        payload = dict(job.payload)
        data = OcrBoxInput.from_payload(payload)
        profile = get_ocr_profile(data.profile_id)
        payload = apply_model_metadata(payload, profile.get("config", {}) or {})
        store.update_job(job, payload=payload)
        text = await asyncio.to_thread(
            run_ocr_box,
            data.profile_id,
            data.volume_id,
            data.filename,
            data.box_id,
            data.x,
            data.y,
            data.width,
            data.height,
        )
        if isinstance(text, str) and text.strip():
            store.update_job(job, message=f"OCR done: {make_snippet(text)}")
        return {"text": text}


class OcrPageJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> OcrPageResult:
        payload = dict(job.payload)
        data = OcrPageInput.from_payload(payload)

        page = load_page(data.volume_id, data.filename)
        text_boxes = list_text_boxes(page)

        total = len(text_boxes)
        if total == 0:
            store.update_job(job, progress=100, message="No text boxes to OCR")
            return {"processed": 0, "total": 0, "skipped": 0, "failures": 0, "updated": 0}

        processed = 0
        skipped = 0
        failures = 0
        updated = 0

        for box in text_boxes:
            if job.status == JobStatus.canceled:
                store.update_job(job, message="Canceled")
                break
            order = int(box.get("orderIndex") or box.get("id") or processed + 1)
            if data.skip_existing and str(box.get("text") or "").strip():
                skipped += 1
                processed += 1
                percent = int((processed / total) * 100)
                store.update_job(
                    job,
                    progress=percent,
                    message=f"{processed}/{total} OCR (box #{order}, skipped)",
                )
                continue

            try:
                text = await asyncio.to_thread(
                    run_ocr_box,
                    data.profile_id,
                    data.volume_id,
                    data.filename,
                    int(box.get("id") or 0) or None,
                    float(box.get("x") or 0.0),
                    float(box.get("y") or 0.0),
                    float(box.get("width") or 0.0),
                    float(box.get("height") or 0.0),
                )
                if text:
                    updated += 1
            except Exception:
                failures += 1
            if job.status == JobStatus.canceled:
                store.update_job(job, message="Canceled")
                break
            processed += 1
            percent = int((processed / total) * 100)
            store.update_job(
                job,
                progress=percent,
                message=f"{processed}/{total} OCR (box #{order})",
            )

        return {
            "processed": processed,
            "total": total,
            "skipped": skipped,
            "failures": failures,
            "updated": updated,
        }
