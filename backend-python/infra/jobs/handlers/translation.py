# backend-python/infra/jobs/handlers/translation.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from core.usecases.translation.engine import run_translate_box_with_context
from core.usecases.translation.profiles import get_translation_profile
from infra.db.db_store import load_page
from infra.jobs.store import Job, JobStatus, JobStore

from .base import JobHandler
from .utils import apply_model_metadata, list_text_boxes, make_snippet


class TranslateBoxResult(TypedDict):
    translation: str


class TranslatePageResult(TypedDict):
    processed: int
    total: int
    skipped: int
    failures: int
    updated: int


@dataclass(frozen=True)
class TranslateBoxInput:
    profile_id: str
    volume_id: str
    filename: str
    box_id: int
    use_page_context: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TranslateBoxInput:
        return cls(
            profile_id=str(payload["profileId"]),
            volume_id=str(payload["volumeId"]),
            filename=str(payload["filename"]),
            box_id=int(payload["boxId"]),
            use_page_context=bool(payload.get("usePageContext", False)),
        )


@dataclass(frozen=True)
class TranslatePageInput:
    profile_id: str
    volume_id: str
    filename: str
    skip_existing: bool
    use_page_context: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TranslatePageInput:
        return cls(
            profile_id=str(payload.get("profileId") or "openai_fast_translate"),
            volume_id=str(payload["volumeId"]),
            filename=str(payload["filename"]),
            skip_existing=bool(payload.get("skipExisting", True)),
            use_page_context=bool(payload.get("usePageContext", False)),
        )


class TranslateBoxJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> TranslateBoxResult:
        payload = dict(job.payload)
        data = TranslateBoxInput.from_payload(payload)
        profile = get_translation_profile(data.profile_id)
        payload = apply_model_metadata(payload, profile.get("config", {}) or {})
        store.update_job(job, payload=payload)
        translation = await asyncio.to_thread(
            run_translate_box_with_context,
            profile_id=data.profile_id,
            volume_id=data.volume_id,
            filename=data.filename,
            box_id=data.box_id,
            use_page_context=data.use_page_context,
        )
        if isinstance(translation, str) and translation.strip():
            store.update_job(job, message=f"Translation done: {make_snippet(translation)}")
        return {"translation": translation}


class TranslatePageJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> TranslatePageResult:
        payload = dict(job.payload)
        data = TranslatePageInput.from_payload(payload)

        page = load_page(data.volume_id, data.filename)
        text_boxes = list_text_boxes(page)

        total = len(text_boxes)
        if total == 0:
            store.update_job(job, progress=100, message="No text boxes to translate")
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
            if data.skip_existing and str(box.get("translation") or "").strip():
                skipped += 1
                processed += 1
                percent = int((processed / total) * 100)
                store.update_job(
                    job,
                    progress=percent,
                    message=f"{processed}/{total} Translate (box #{order}, skipped)",
                )
                continue
            if not str(box.get("text") or "").strip():
                skipped += 1
                processed += 1
                percent = int((processed / total) * 100)
                store.update_job(
                    job,
                    progress=percent,
                    message=f"{processed}/{total} Translate (box #{order}, no text)",
                )
                continue

            translation = ""
            try:
                translation = await asyncio.to_thread(
                    run_translate_box_with_context,
                    profile_id=data.profile_id,
                    volume_id=data.volume_id,
                    filename=data.filename,
                    box_id=int(box.get("id") or 0),
                    use_page_context=data.use_page_context,
                )
            except Exception:
                failures += 1
            if translation:
                updated += 1
            if job.status == JobStatus.canceled:
                store.update_job(job, message="Canceled")
                break
            processed += 1
            percent = int((processed / total) * 100)
            store.update_job(
                job,
                progress=percent,
                message=f"{processed}/{total} Translate (box #{order})",
            )

        return {
            "processed": processed,
            "total": total,
            "skipped": skipped,
            "failures": failures,
            "updated": updated,
        }
