# backend-python/infra/jobs/handlers/missing_boxes.py
"""Job handler for LLM-assisted missing text-box detection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from core.usecases.box_detection.missing_react import detect_missing_text_boxes_react
from infra.jobs.store import Job, JobStore

from .base import JobHandler


class MissingBoxDetectionResult(TypedDict):
    status: str
    volume_id: str
    filename: str
    model_id: str
    existing_text_box_count: int
    proposed_count: int
    accepted_count: int
    rejected_count: int
    created_count: int
    run_id: str | None
    accepted: list[dict[str, Any]]
    rejected: list[dict[str, Any]]


@dataclass(frozen=True)
class MissingBoxDetectionInput:
    volume_id: str
    filename: str
    model_id: str | None
    max_candidates: int
    max_attempts_per_candidate: int
    min_confidence: float
    overlap_iou_threshold: float
    max_image_side: int
    crop_padding_px: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> MissingBoxDetectionInput:
        return cls(
            volume_id=str(payload["volumeId"]),
            filename=str(payload["filename"]),
            model_id=(str(payload.get("modelId") or "").strip() or None),
            max_candidates=int(payload.get("maxCandidates") or 8),
            max_attempts_per_candidate=int(payload.get("maxAttemptsPerCandidate") or 3),
            min_confidence=float(payload.get("minConfidence") or 0.75),
            overlap_iou_threshold=float(payload.get("overlapIouThreshold") or 0.45),
            max_image_side=int(payload.get("maxImageSide") or 1536),
            crop_padding_px=int(payload.get("cropPaddingPx") or 6),
        )


class MissingBoxDetectionJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> MissingBoxDetectionResult:
        trial_history: list[dict[str, Any]] = []
        log_context = {
            "job_id": job.id,
            "workflow_run_id": str(job.payload.get("workflowRunId") or "").strip() or None,
            "task_run_id": str(job.payload.get("taskRunId") or "").strip() or None,
        }
        log_context = {key: value for key, value in log_context.items() if value}

        def _append_trial_to_history(event: dict[str, Any]) -> None:
            latest_trial = event.get("latest_trial")
            if not isinstance(latest_trial, dict):
                return
            try:
                trial_key = (
                    int(latest_trial.get("candidate_index") or 0),
                    int(latest_trial.get("attempt_index") or 0),
                )
            except (TypeError, ValueError):
                return
            for idx in range(len(trial_history) - 1, -1, -1):
                existing = trial_history[idx]
                existing_key = (
                    int(existing.get("candidate_index") or 0),
                    int(existing.get("attempt_index") or 0),
                )
                if existing_key == trial_key:
                    trial_history[idx] = dict(latest_trial)
                    break
            else:
                trial_history.append(dict(latest_trial))
            if len(trial_history) > 20:
                del trial_history[:-20]

        def _event_progress(value: Any, fallback: int) -> int:
            try:
                parsed = int(float(value))
            except (TypeError, ValueError):
                return fallback
            return max(0, min(99, parsed))

        def _event_message(event: dict[str, Any]) -> str:
            phase = str(event.get("phase") or "").strip().lower()
            status = str(event.get("status") or "").strip().lower()
            candidate_index = int(event.get("candidate_index") or 0)
            candidates_total = int(event.get("candidates_total") or 0)
            attempt_index = int(event.get("attempt_index") or 0)
            attempts_per_candidate = int(event.get("attempts_per_candidate") or 0)
            if phase == "propose":
                if status == "started":
                    return "Proposing missing text regions"
                if status == "completed":
                    count = int(event.get("proposed_count") or 0)
                    return f"Proposed {count} missing-text candidates"
            if phase == "verify":
                if candidate_index > 0 and candidates_total > 0:
                    base = f"Verify candidate {candidate_index}/{candidates_total}"
                    if attempt_index > 0 and attempts_per_candidate > 0:
                        base += f" attempt {attempt_index}/{attempts_per_candidate}"
                else:
                    base = "Verifying candidate boxes"
                if status == "attempting":
                    return base
                if status == "accepted":
                    return f"{base} accepted"
                if status == "candidate_valid":
                    return f"{base} valid; trying smaller box"
                if status == "retrying":
                    return f"{base} retrying"
                if status == "verification_error":
                    error_kind = str(event.get("error_kind") or "").strip().replace("_", " ")
                    if error_kind:
                        return f"{base} {error_kind}"
                    return f"{base} verification error"
                if status in {"rejected", "overlap_skip"}:
                    return f"{base} {status.replace('_', ' ')}"
                return base
            if phase == "persist":
                accepted_count = int(event.get("accepted_count") or 0)
                return f"Persisting {accepted_count} accepted missing boxes"
            if phase == "completed":
                created_count = int(event.get("created_count") or 0)
                return f"Missing-box detection complete: created {created_count} boxes"
            return str(event.get("message") or "").strip() or "Running missing-box detection"

        data = MissingBoxDetectionInput.from_payload(dict(job.payload))
        store.update_job(
            job,
            progress=5,
            message="Finding missing text boxes (LLM ReAct loop)",
        )
        loop = asyncio.get_running_loop()
        finalized = False

        def _apply_runtime_event(event: dict[str, Any]) -> None:
            nonlocal finalized
            if finalized:
                return
            _append_trial_to_history(event)
            progress_value = _event_progress(event.get("progress"), int(job.progress or 5))
            runtime_event = dict(event)
            runtime_event["trial_history"] = list(trial_history)
            store.update_job(
                job,
                progress=progress_value,
                message=_event_message(event),
                metrics={"missing_box_runtime": runtime_event},
            )

        def _on_runtime_event(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(_apply_runtime_event, dict(event))

        result = await asyncio.to_thread(
            detect_missing_text_boxes_react,
            volume_id=data.volume_id,
            filename=data.filename,
            model_id=data.model_id,
            max_candidates=data.max_candidates,
            max_attempts_per_candidate=data.max_attempts_per_candidate,
            min_confidence=data.min_confidence,
            overlap_iou_threshold=data.overlap_iou_threshold,
            max_image_side=data.max_image_side,
            crop_padding_px=data.crop_padding_px,
            log_context=log_context,
            on_runtime_event=_on_runtime_event,
        )
        finalized = True
        created_count = int(result.get("created_count") or 0)
        accepted_count = int(result.get("accepted_count") or 0)
        proposed_count = int(result.get("proposed_count") or 0)
        store.update_job(
            job,
            progress=100,
            message=(
                f"Missing-box detection complete: created {created_count} boxes "
                f"(accepted {accepted_count}/{proposed_count} proposals)"
            ),
            metrics={
                "missing_box_runtime": {
                    "phase": "completed",
                    "status": "completed",
                    "progress": 100,
                    "proposed_count": proposed_count,
                    "accepted_count": accepted_count,
                    "rejected_count": int(result.get("rejected_count") or 0),
                    "created_count": created_count,
                    "latest_trial": None,
                    "trial_history": [],
                }
            },
        )
        return result
