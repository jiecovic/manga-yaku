# backend-python/infra/jobs/handlers/ocr.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from core.usecases.ocr.engine import run_ocr_box
from core.usecases.ocr.profiles import get_ocr_profile
from infra.jobs.store import Job, JobStore

from .base import JobHandler
from .utils import apply_model_metadata, make_snippet


class OcrBoxResult(TypedDict):
    text: str


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
