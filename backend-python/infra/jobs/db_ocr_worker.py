from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from threading import Event
from typing import Any

from sqlalchemy import select

from core.usecases.ocr.execution import resolve_ocr_prompt_version, run_ocr_task_async
from core.usecases.ocr.profiles import get_ocr_profile
from core.usecases.settings.service import resolve_ocr_parallelism_settings
from infra.db.db import TaskRun, WorkflowRun, get_session
from infra.db.db_store import set_box_ocr_text_by_id
from infra.db.workflow_store import (
    append_task_attempt_event,
    get_workflow_run,
    list_task_runs,
    update_task_run,
    update_workflow_run,
)

logger = logging.getLogger(__name__)

_OCR_WORKFLOW_TYPES = ("ocr_page", "ocr_box")
_OCR_STAGE = "ocr"
_TERMINAL_TASK_STATUSES = {"completed", "failed", "canceled", "timed_out"}
_DEFAULT_LEASE_SECONDS = 180
_DEFAULT_TASK_TIMEOUT_SECONDS = 180
_DEFAULT_IDLE_SLEEP_SECONDS = 0.4
_DEFAULT_ERROR_SLEEP_SECONDS = 1.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _extract_request_payload(run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    result_json = run.get("result_json")
    if not isinstance(result_json, dict):
        return {}
    request = result_json.get("request")
    if not isinstance(request, dict):
        return {}
    return dict(request)


def _compose_result_json(
    run: dict[str, Any] | None,
    *,
    progress: int,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {}
    request = _extract_request_payload(run)
    if request:
        base["request"] = request

    if isinstance(run, dict):
        result_json = run.get("result_json")
        if isinstance(result_json, dict):
            for key in ("total_boxes", "skipped", "processable_boxes"):
                if key in result_json:
                    base[key] = result_json[key]

    base["progress"] = int(max(0, min(100, progress)))
    base["message"] = str(message)
    if extra:
        base.update(extra)
    return base


def _profile_order_for_run(tasks: list[dict[str, Any]], request_payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    raw = request_payload.get("profileIds")
    if isinstance(raw, list):
        for item in raw:
            profile_id = str(item).strip()
            if not profile_id or profile_id in seen:
                continue
            seen.add(profile_id)
            out.append(profile_id)
    if out:
        return out

    for task in tasks:
        profile_id = str(task.get("profile_id") or "").strip()
        if not profile_id or profile_id in seen:
            continue
        seen.add(profile_id)
        out.append(profile_id)
    return out


def _cancel_pending_tasks_for_workflow(workflow_id: str) -> None:
    tasks = list_task_runs(workflow_id, stage=_OCR_STAGE)
    for task in tasks:
        status = str(task.get("status") or "")
        if status in _TERMINAL_TASK_STATUSES:
            continue
        update_task_run(
            str(task.get("id")),
            status="canceled",
            finished=True,
            error_code="cancel_requested",
            error_detail="Canceled",
        )


def _update_workflow_progress_after_task(workflow_id: str) -> None:
    run = get_workflow_run(workflow_id)
    if not run:
        return

    tasks = list_task_runs(workflow_id, stage=_OCR_STAGE)
    total_tasks = len(tasks)
    queued_or_running = sum(
        1
        for task in tasks
        if str(task.get("status") or "") in {"queued", "running"}
    )
    done_tasks = total_tasks - queued_or_running
    request_payload = _extract_request_payload(run)

    if bool(run.get("cancel_requested")) or str(run.get("status") or "") == "canceled":
        _cancel_pending_tasks_for_workflow(workflow_id)
        result_json = _compose_result_json(
            run,
            progress=100,
            message="Canceled",
        )
        update_workflow_run(
            workflow_id,
            state="canceled",
            status="canceled",
            error_message="Canceled",
            result_json=result_json,
        )
        return

    if total_tasks == 0:
        result_json = _compose_result_json(
            run,
            progress=100,
            message="No OCR tasks",
            extra={
                "processed": int(run.get("result_json", {}).get("total_boxes") or 0)
                if isinstance(run.get("result_json"), dict)
                else 0,
                "total": int(run.get("result_json", {}).get("total_boxes") or 0)
                if isinstance(run.get("result_json"), dict)
                else 0,
                "updated": 0,
                "failures": 0,
                "skipped": int(run.get("result_json", {}).get("skipped") or 0)
                if isinstance(run.get("result_json"), dict)
                else 0,
            },
        )
        update_workflow_run(
            workflow_id,
            state="completed",
            status="completed",
            result_json=result_json,
        )
        return

    if queued_or_running > 0:
        progress = 5 + int((done_tasks / max(total_tasks, 1)) * 90)
        result_json = _compose_result_json(
            run,
            progress=progress,
            message=f"OCR {done_tasks}/{total_tasks} tasks",
        )
        update_workflow_run(
            workflow_id,
            state="running",
            status="running",
            result_json=result_json,
        )
        return

    # All tasks terminal -> finalize box writes.
    profile_order = _profile_order_for_run(tasks, request_payload)
    by_box: dict[int, dict[str, str]] = {}
    box_had_failure: dict[int, bool] = {}
    processable_box_ids: set[int] = set()

    for task in tasks:
        box_raw = task.get("box_id")
        if box_raw is None:
            continue
        box_id = int(box_raw)
        processable_box_ids.add(box_id)
        task_status = str(task.get("status") or "")
        result = task.get("result_json")
        result_status = ""
        text = ""
        profile_id = str(task.get("profile_id") or "").strip()
        if isinstance(result, dict):
            result_status = str(result.get("status") or "").strip()
            text = str(result.get("text") or "")
            if not profile_id:
                profile_id = str(result.get("profile_id") or "").strip()

        if task_status == "completed" and result_status == "ok" and text.strip():
            by_box.setdefault(box_id, {})[profile_id] = text.strip()
            continue

        if task_status in {"failed", "timed_out"} or result_status in {"error", "invalid", "timed_out"}:
            box_had_failure[box_id] = True

    updated = 0
    failures = 0
    volume_id = str(run.get("volume_id") or "").strip()
    filename = str(run.get("filename") or "").strip()
    try:
        for box_id in sorted(processable_box_ids):
            per_profile = by_box.get(box_id, {})
            chosen = ""
            for profile_id in profile_order:
                candidate = per_profile.get(profile_id, "")
                if candidate:
                    chosen = candidate
                    break
            if not chosen:
                for candidate in per_profile.values():
                    if candidate:
                        chosen = candidate
                        break
            if chosen:
                set_box_ocr_text_by_id(
                    volume_id,
                    filename,
                    box_id=box_id,
                    ocr_text=chosen,
                )
                updated += 1
            elif box_had_failure.get(box_id):
                failures += 1
    except Exception as exc:
        error_text = str(exc).strip() or repr(exc)
        result_json = _compose_result_json(
            run,
            progress=100,
            message=error_text[:160],
        )
        update_workflow_run(
            workflow_id,
            state="failed",
            status="failed",
            error_message=error_text,
            result_json=result_json,
        )
        return

    result_json_source = run.get("result_json")
    total_boxes = 0
    skipped = 0
    if isinstance(result_json_source, dict):
        total_boxes = _to_int(result_json_source.get("total_boxes"), default=0)
        skipped = _to_int(result_json_source.get("skipped"), default=0)
    if total_boxes <= 0:
        total_boxes = len(processable_box_ids) + max(skipped, 0)

    result_json = _compose_result_json(
        run,
        progress=100,
        message=f"OCR complete ({updated} updated, {failures} failed boxes)",
        extra={
            "processed": total_boxes,
            "total": total_boxes,
            "updated": updated,
            "failures": failures,
            "skipped": max(skipped, 0),
        },
    )
    update_workflow_run(
        workflow_id,
        state="completed",
        status="completed",
        result_json=result_json,
    )


def _claim_next_task(*, lease_seconds: int) -> dict[str, Any] | None:
    now = _utc_now()
    lease_until = now + timedelta(seconds=max(30, lease_seconds))
    with get_session() as session:
        stmt = (
            select(TaskRun, WorkflowRun)
            .join(WorkflowRun, TaskRun.workflow_id == WorkflowRun.id)
            .where(WorkflowRun.workflow_type.in_(_OCR_WORKFLOW_TYPES))
            .where(WorkflowRun.status.in_(["queued", "running"]))
            .where(WorkflowRun.cancel_requested.is_(False))
            .where(TaskRun.stage == _OCR_STAGE)
            .where(TaskRun.status == "queued")
            .order_by(TaskRun.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = session.execute(stmt).first()
        if row is None:
            return None
        task_row, workflow_row = row

        task_row.status = "running"
        task_row.started_at = task_row.started_at or now
        task_row.updated_at = now
        task_row.lease_until = lease_until
        task_row.error_code = None
        task_row.error_detail = None
        if workflow_row.status == "queued":
            workflow_row.status = "running"
        if workflow_row.state == "queued":
            workflow_row.state = "running"
        workflow_row.updated_at = now

        payload = task_row.input_json if isinstance(task_row.input_json, dict) else {}
        return {
            "task_id": str(task_row.id),
            "workflow_id": str(workflow_row.id),
            "volume_id": str(workflow_row.volume_id),
            "filename": str(workflow_row.filename),
            "box_id": int(task_row.box_id or payload.get("box_id") or 0),
            "profile_id": str(task_row.profile_id or payload.get("profile_id") or ""),
            "x": float(payload.get("x") or 0.0),
            "y": float(payload.get("y") or 0.0),
            "width": float(payload.get("width") or 0.0),
            "height": float(payload.get("height") or 0.0),
        }


def _requeue_stale_running_tasks(*, lease_seconds: int) -> int:
    now = _utc_now()
    changed = 0
    with get_session() as session:
        stmt = (
            select(TaskRun, WorkflowRun)
            .join(WorkflowRun, TaskRun.workflow_id == WorkflowRun.id)
            .where(WorkflowRun.workflow_type.in_(_OCR_WORKFLOW_TYPES))
            .where(TaskRun.stage == _OCR_STAGE)
            .where(TaskRun.status == "running")
            .where((TaskRun.lease_until.is_(None)) | (TaskRun.lease_until < now))
            .with_for_update(skip_locked=True)
        )
        rows = session.execute(stmt).all()
        for task_row, workflow_row in rows:
            if workflow_row.cancel_requested or workflow_row.status == "canceled":
                task_row.status = "canceled"
                task_row.finished_at = now
                task_row.error_code = "cancel_requested"
                task_row.error_detail = "Canceled"
            else:
                task_row.status = "queued"
                task_row.error_code = "lease_expired"
                task_row.error_detail = "Requeued after worker restart"
            task_row.lease_until = None
            task_row.updated_at = now
            changed += 1
    return changed


async def _run_claimed_task(
    claimed: dict[str, Any],
    *,
    local_sem: asyncio.Semaphore,
    remote_sem: asyncio.Semaphore,
    task_timeout_seconds: int,
) -> None:
    task_id = str(claimed.get("task_id") or "")
    workflow_id = str(claimed.get("workflow_id") or "")
    profile_id = str(claimed.get("profile_id") or "")
    if not task_id or not workflow_id or not profile_id:
        return

    try:
        profile = get_ocr_profile(profile_id)
    except Exception as exc:
        error_text = str(exc).strip() or repr(exc)
        update_task_run(
            task_id,
            status="failed",
            finished=True,
            error_code="profile_missing",
            error_detail=error_text,
        )
        await asyncio.to_thread(_update_workflow_progress_after_task, workflow_id)
        return

    provider = str(profile.get("provider") or "")
    sem = remote_sem if provider in {"llm_ocr", "llm_ocr_chat"} else local_sem
    prompt_file = resolve_ocr_prompt_version(profile_id)

    async with sem:
        def persist_attempt_event(event: dict[str, Any]) -> None:
            attempt = max(1, _to_int(event.get("attempt"), default=1))
            latency_ms = max(0, _to_int(event.get("latency_ms"), default=0))
            max_output_raw = event.get("max_output_tokens")
            max_output_tokens = (
                _to_int(max_output_raw, default=0) or None
                if max_output_raw is not None
                else None
            )
            append_task_attempt_event(
                task_id=task_id,
                attempt=attempt,
                tool_name="ocr_tool",
                model_id=event.get("model_id"),
                prompt_version=prompt_file,
                params_snapshot={
                    "max_output_tokens": max_output_tokens,
                    "reasoning_effort": event.get("reasoning_effort"),
                },
                finish_reason=event.get("status"),
                latency_ms=latency_ms,
                error_detail=event.get("error_message"),
            )
            # Persist running attempt progress so the UI can reflect retries in near real-time.
            update_task_run(task_id, attempt=attempt)

        def on_attempt(event: dict[str, Any]) -> None:
            try:
                persist_attempt_event(event)
            except Exception:
                logger.exception("Failed to persist OCR attempt event for task %s", task_id)

        outcome = await run_ocr_task_async(
            profile_id=profile_id,
            volume_id=str(claimed.get("volume_id") or ""),
            filename=str(claimed.get("filename") or ""),
            box_id=int(claimed.get("box_id") or 0),
            x=float(claimed.get("x") or 0.0),
            y=float(claimed.get("y") or 0.0),
            width=float(claimed.get("width") or 0.0),
            height=float(claimed.get("height") or 0.0),
            timeout_seconds=max(15, task_timeout_seconds),
            on_attempt=on_attempt,
        )

        terminal_status = "completed" if outcome.status in {"ok", "no_text"} else "failed"
        update_task_run(
            task_id,
            status=terminal_status,
            attempt=outcome.attempt,
            error_code=None if terminal_status == "completed" else outcome.status,
            error_detail=outcome.error_message,
            result_json=outcome.to_result_json(),
            finished=True,
        )
        await asyncio.to_thread(_update_workflow_progress_after_task, workflow_id)


async def run_ocr_db_worker(stop_event: Event) -> None:
    parallelism = resolve_ocr_parallelism_settings()
    lease_seconds = max(30, _to_int(parallelism.lease_seconds, default=_DEFAULT_LEASE_SECONDS))
    task_timeout_seconds = max(
        15,
        _to_int(
            parallelism.task_timeout_seconds,
            default=_DEFAULT_TASK_TIMEOUT_SECONDS,
        ),
    )
    local_limit = max(1, _to_int(parallelism.local, default=4))
    remote_limit = max(1, _to_int(parallelism.remote, default=2))
    worker_cap = max(1, _to_int(parallelism.max_workers, default=6))
    worker_count = max(1, min(local_limit + remote_limit, worker_cap))

    local_sem = asyncio.Semaphore(min(local_limit, 32))
    remote_sem = asyncio.Semaphore(min(remote_limit, 32))

    try:
        stale = await asyncio.to_thread(_requeue_stale_running_tasks, lease_seconds=lease_seconds)
    except Exception:
        logger.exception("Failed to requeue stale OCR tasks on startup")
        stale = 0
    if stale > 0:
        logger.info("Requeued %s stale OCR tasks", stale)

    async def worker_loop(worker_idx: int) -> None:
        idle_sleep = float(_DEFAULT_IDLE_SLEEP_SECONDS)
        error_sleep = float(_DEFAULT_ERROR_SLEEP_SECONDS)
        while not stop_event.is_set():
            try:
                claimed = await asyncio.to_thread(_claim_next_task, lease_seconds=lease_seconds)
            except Exception:
                logger.exception("OCR DB worker #%s failed to claim task", worker_idx)
                await asyncio.sleep(error_sleep)
                continue
            if not claimed:
                await asyncio.sleep(idle_sleep)
                continue
            try:
                await _run_claimed_task(
                    claimed,
                    local_sem=local_sem,
                    remote_sem=remote_sem,
                    task_timeout_seconds=task_timeout_seconds,
                )
            except Exception:
                logger.exception("OCR DB worker #%s failed claimed task", worker_idx)
                task_id = str(claimed.get("task_id") or "")
                workflow_id = str(claimed.get("workflow_id") or "")
                if task_id:
                    try:
                        update_task_run(
                            task_id,
                            status="failed",
                            finished=True,
                            error_code="worker_error",
                            error_detail="Unhandled worker failure",
                        )
                    except Exception:
                        logger.exception("OCR DB worker #%s failed to mark task as failed", worker_idx)
                if workflow_id:
                    try:
                        await asyncio.to_thread(_update_workflow_progress_after_task, workflow_id)
                    except Exception:
                        logger.exception(
                            "OCR DB worker #%s failed to update workflow progress after worker error",
                            worker_idx,
                        )
                await asyncio.sleep(error_sleep)

    workers = [asyncio.create_task(worker_loop(idx)) for idx in range(worker_count)]
    try:
        await asyncio.gather(*workers)
    finally:
        for task in workers:
            task.cancel()
