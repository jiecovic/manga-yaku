from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from core.usecases.translation.profiles import get_translation_profile
from core.usecases.translation.task_runner import run_translation_task_with_retries
from infra.jobs.store import Job, JobStore

from .base import JobHandler
from .utils import apply_model_metadata, make_snippet


class TranslateBoxResult(TypedDict):
    box_id: int
    profile_id: str
    status: str
    translation: str
    attempt: int
    latency_ms: int
    model_id: str | None
    max_output_tokens: int | None
    reasoning_effort: str | None
    error_message: str | None


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
        payload_state = dict(job.payload)
        data = TranslateBoxInput.from_payload(payload_state)

        profile = get_translation_profile(data.profile_id)
        payload_state = apply_model_metadata(payload_state, profile.get("config", {}) or {})
        store.update_job(job, payload=payload_state, progress=5, message="Running translation")

        def on_attempt(event: dict[str, Any]) -> None:
            nonlocal payload_state
            attempt = int(event.get("attempt") or 1)
            status = str(event.get("status") or "unknown")
            latency_ms = int(event.get("latency_ms") or 0)
            model_id = event.get("model_id")
            max_output_tokens = event.get("max_output_tokens")
            reasoning_effort = event.get("reasoning_effort")
            translation = str(event.get("translation") or "").strip()
            error_message = str(event.get("error_message") or "").strip()

            payload_update = dict(payload_state)
            if model_id:
                payload_update["modelId"] = str(model_id)
            if max_output_tokens is not None:
                try:
                    payload_update["maxOutputTokens"] = int(max_output_tokens)
                except (TypeError, ValueError):
                    pass
            if reasoning_effort:
                payload_update["reasoningEffort"] = str(reasoning_effort)
            payload_state = payload_update

            detail = f"Attempt {attempt}: {status}"
            if latency_ms > 0:
                detail += f" ({latency_ms}ms)"
            if status == "ok" and translation:
                detail = f"{detail} | {make_snippet(translation)}"
            if status == "error" and error_message:
                detail = f"{detail} | {error_message[:120]}"
            store.update_job(
                job,
                payload=payload_state,
                progress=min(95, 15 + (attempt * 25)),
                message=detail,
            )

        outcome = await asyncio.to_thread(
            run_translation_task_with_retries,
            profile_id=data.profile_id,
            volume_id=data.volume_id,
            filename=data.filename,
            box_id=data.box_id,
            use_page_context=data.use_page_context,
            on_attempt=on_attempt,
        )

        result = outcome.to_result_json()
        status = str(result.get("status") or "")
        translation = str(result.get("translation") or "").strip()
        if status == "ok":
            store.update_job(
                job,
                message=f"Translation done: {make_snippet(translation)}",
                progress=100,
            )
            return result
        if status == "no_text":
            store.update_job(job, message="No text detected in source box", progress=100)
            return result

        error_message = str(result.get("error_message") or "").strip()
        if not error_message:
            if status == "invalid":
                error_message = "Translation returned invalid or empty structured output"
            else:
                error_message = "Translation failed"
        raise RuntimeError(error_message)
