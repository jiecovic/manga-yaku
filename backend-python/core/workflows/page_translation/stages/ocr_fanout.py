# backend-python/core/workflows/page_translation/stages/ocr_fanout.py
"""Workflow stage handler for page translation: ocr fanout."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.usecases.ocr.profiles.registry import get_ocr_profile
from core.usecases.ocr.runtime.execution import resolve_ocr_prompt_version, run_ocr_task_async
from core.usecases.ocr.selection import select_box_ocr_texts
from core.usecases.ocr.tasks.runner import OcrTaskOutcome
from infra.db.store_boxes import set_box_ocr_text_by_id
from infra.db.workflow_store import create_task_run, update_task_run

from ..orchestration.context import WorkflowRunContext
from ..orchestration.progress import emit_workflow_progress
from ..orchestration.resolution import resolve_parallel_limits
from ..persistence.events import append_ocr_attempt_events
from ..state.types import WorkflowState

CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class _OcrTaskSpec:
    task_run_id: str
    box_id: int
    profile_id: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class OcrFanoutResult:
    candidates: dict[int, dict[str, str]]
    no_text_candidates: dict[int, set[str]]
    error_candidates: dict[int, set[str]]
    invalid_candidates: dict[int, set[str]]
    llm_profiles: set[str]
    usable_ocr: bool


async def run_ocr_fanout_stage(
    *,
    workflow_run_id: str,
    volume_id: str,
    filename: str,
    text_boxes: list[dict[str, Any]],
    ocr_profiles: list[str],
    preferred_profile_id: str | None,
    run_ctx: WorkflowRunContext,
    state: WorkflowState,
    is_canceled: CancelCheck,
) -> OcrFanoutResult:
    """Run ocr fanout stage."""
    candidates: dict[int, dict[str, str]] = {}
    no_text_candidates: dict[int, set[str]] = {}
    error_candidates: dict[int, set[str]] = {}
    invalid_candidates: dict[int, set[str]] = {}
    llm_profiles: set[str] = set()
    for profile_id in ocr_profiles:
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        if profile.get("provider") == "llm_ocr":
            llm_profiles.add(profile_id)

    specs: list[_OcrTaskSpec] = []
    for profile_id in ocr_profiles:
        for box in text_boxes:
            box_id = int(box.get("id") or 0)
            if box_id <= 0:
                continue
            task_run_id = create_task_run(
                workflow_id=workflow_run_id,
                stage="ocr",
                status="queued",
                box_id=box_id,
                profile_id=profile_id,
                input_json={
                    "volume_id": volume_id,
                    "filename": filename,
                    "box_id": box_id,
                    "profile_id": profile_id,
                    "x": float(box.get("x") or 0.0),
                    "y": float(box.get("y") or 0.0),
                    "width": float(box.get("width") or 0.0),
                    "height": float(box.get("height") or 0.0),
                },
            )
            specs.append(
                _OcrTaskSpec(
                    task_run_id=task_run_id,
                    box_id=box_id,
                    profile_id=profile_id,
                    x=float(box.get("x") or 0.0),
                    y=float(box.get("y") or 0.0),
                    width=float(box.get("width") or 0.0),
                    height=float(box.get("height") or 0.0),
                )
            )

    run_ctx.ocr_tasks_total = len(specs)
    local_parallelism, remote_parallelism = resolve_parallel_limits()
    local_sem = asyncio.Semaphore(local_parallelism)
    remote_sem = asyncio.Semaphore(remote_parallelism)

    async def run_one_task(spec: _OcrTaskSpec) -> OcrTaskOutcome | None:
        if is_canceled():
            update_task_run(
                spec.task_run_id,
                status="canceled",
                finished=True,
                error_code="cancel_requested",
                error_detail="Canceled before OCR task execution",
            )
            return None

        profile = get_ocr_profile(spec.profile_id)
        sem = remote_sem if profile.get("provider") == "llm_ocr" else local_sem
        async with sem:
            if is_canceled():
                update_task_run(
                    spec.task_run_id,
                    status="canceled",
                    finished=True,
                    error_code="cancel_requested",
                    error_detail="Canceled before OCR task execution",
                )
                return None

            update_task_run(
                spec.task_run_id,
                status="running",
                attempt=1,
                started=True,
            )

            attempt_events: list[dict[str, Any]] = []

            def on_attempt(event: dict[str, Any]) -> None:
                attempt_events.append(event)

            outcome = await run_ocr_task_async(
                profile_id=spec.profile_id,
                volume_id=volume_id,
                filename=filename,
                box_id=spec.box_id,
                x=spec.x,
                y=spec.y,
                width=spec.width,
                height=spec.height,
                on_attempt=on_attempt,
            )

            prompt_version = resolve_ocr_prompt_version(spec.profile_id)
            append_ocr_attempt_events(
                task_id=spec.task_run_id,
                prompt_version=prompt_version,
                attempt_events=attempt_events,
            )

            terminal_status = "completed" if outcome.status in {"ok", "no_text"} else "failed"
            update_task_run(
                spec.task_run_id,
                status=terminal_status,
                attempt=outcome.attempt,
                error_code=None if terminal_status == "completed" else outcome.status,
                error_detail=outcome.error_message,
                result_json=outcome.to_result_json(),
                finished=True,
            )

            run_ctx.ocr_tasks_done += 1
            progress = 20 + int((run_ctx.ocr_tasks_done / max(run_ctx.ocr_tasks_total, 1)) * 50)
            emit_workflow_progress(
                run_ctx,
                state=state,
                stage="ocr_running",
                progress=progress,
                message=f"OCR {run_ctx.ocr_tasks_done}/{run_ctx.ocr_tasks_total}",
            )
            return outcome

    outcomes: list[OcrTaskOutcome] = []
    if specs:
        raw_outcomes = await asyncio.gather(*(run_one_task(spec) for spec in specs))
        outcomes = [item for item in raw_outcomes if item is not None]

    usable_ocr = False
    for outcome in outcomes:
        box_id = outcome.box_id
        if outcome.status == "ok":
            candidates.setdefault(box_id, {})[outcome.profile_id] = outcome.text
            usable_ocr = True
        elif outcome.status == "no_text":
            no_text_candidates.setdefault(box_id, set()).add(outcome.profile_id)
            usable_ocr = True
        elif outcome.status == "invalid":
            invalid_candidates.setdefault(box_id, set()).add(outcome.profile_id)
        elif outcome.status == "error":
            error_candidates.setdefault(box_id, set()).add(outcome.profile_id)

    selected_texts = select_box_ocr_texts(
        candidates,
        box_ids=(int(box.get("id") or 0) for box in text_boxes),
        preferred_profile_ids=[preferred_profile_id] if preferred_profile_id else [],
    )
    for box_id, chosen in selected_texts.items():
        set_box_ocr_text_by_id(
            volume_id,
            filename,
            box_id=box_id,
            ocr_text=chosen,
        )

    return OcrFanoutResult(
        candidates=candidates,
        no_text_candidates=no_text_candidates,
        error_candidates=error_candidates,
        invalid_candidates=invalid_candidates,
        llm_profiles=llm_profiles,
        usable_ocr=usable_ocr,
    )
