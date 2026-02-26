from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from core.usecases.translation.engine import run_translate_box_with_context
from core.usecases.translation.profiles import get_translation_profile
from infra.jobs.store import Job, JobStore

from .base import JobHandler
from .utils import apply_model_metadata, make_snippet


class TranslateBoxResult(TypedDict):
    translation: str


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
            store.update_job(
                job,
                message=f"Translation done: {make_snippet(translation)}",
            )

        return {"translation": translation}
