# backend-python/infra/jobs/db_translate_worker.py
"""Database-backed translation task worker entrypoint."""

from __future__ import annotations

import asyncio
import logging
from threading import Event
from typing import Any

from core.usecases.translation.execution import (
    resolve_translation_prompt_version,
    run_translation_task_async,
)
from core.usecases.translation.profiles import get_translation_profile
from infra.jobs.handlers.utils import make_snippet
from infra.jobs.job_modes import TRANSLATE_BOX_WORKFLOW_TYPE
from infra.jobs.task_attempt_events import (
    build_reasoning_params_snapshot,
    persist_task_attempt_event,
)
from infra.jobs.workflow_repo import (
    claim_next_task,
    get_workflow_run,
    list_task_runs,
    requeue_stale_running_tasks,
    update_task_run,
    update_workflow_run,
)
from infra.logging.correlation import append_correlation, normalize_correlation

logger = logging.getLogger(__name__)

_TRANSLATE_WORKFLOW_TYPE = TRANSLATE_BOX_WORKFLOW_TYPE
_TRANSLATE_STAGE = "translate_box"
_TERMINAL_TASK_STATUSES = {"completed", "failed", "canceled", "timed_out"}
_DEFAULT_LEASE_SECONDS = 180
_DEFAULT_TASK_TIMEOUT_SECONDS = 180
_DEFAULT_IDLE_SLEEP_SECONDS = 0.4
_DEFAULT_ERROR_SLEEP_SECONDS = 1.0
_DEFAULT_WORKER_COUNT = 2


def _translate_correlation(
    *,
    component: str,
    task_id: str | None = None,
    workflow_id: str | None = None,
    volume_id: str | None = None,
    filename: str | None = None,
    box_id: int | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    return normalize_correlation(
        {
            "component": component,
            "task_run_id": task_id,
            "workflow_run_id": workflow_id,
            "volume_id": volume_id,
            "filename": filename,
        },
        box_id=box_id,
        profile_id=profile_id,
    )


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
    base["progress"] = int(max(0, min(100, progress)))
    base["message"] = str(message)
    if extra:
        base.update(extra)
    return base


def _cancel_pending_tasks_for_workflow(workflow_id: str) -> None:
    tasks = list_task_runs(workflow_id, stage=_TRANSLATE_STAGE)
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

    tasks = list_task_runs(workflow_id, stage=_TRANSLATE_STAGE)
    total_tasks = len(tasks)
    queued_or_running = sum(
        1 for task in tasks if str(task.get("status") or "") in {"queued", "running"}
    )

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

    if total_tasks <= 0:
        result_json = _compose_result_json(
            run,
            progress=100,
            message="No translation task",
            extra={"status": "error"},
        )
        update_workflow_run(
            workflow_id,
            state="failed",
            status="failed",
            error_message="No translation task",
            result_json=result_json,
        )
        return

    if queued_or_running > 0:
        result_json = _compose_result_json(
            run,
            progress=50,
            message="Translating box",
        )
        update_workflow_run(
            workflow_id,
            state="running",
            status="running",
            result_json=result_json,
        )
        return

    task = tasks[0]
    task_status = str(task.get("status") or "")
    task_result = task.get("result_json")
    result_payload = dict(task_result) if isinstance(task_result, dict) else {}
    result_status = str(result_payload.get("status") or "")
    translation = str(result_payload.get("translation") or "").strip()
    error_text = str(
        result_payload.get("error_message") or task.get("error_code") or "Translation failed"
    ).strip()
    if not error_text:
        error_text = "Translation failed"

    if task_status == "completed" and result_status in {"ok", "no_text"}:
        if result_status == "ok" and translation:
            message = f"Translation done: {make_snippet(translation)}"
        elif result_status == "no_text":
            message = "No text detected in source box"
        else:
            message = "Translation complete"
        result_json = _compose_result_json(
            run,
            progress=100,
            message=message,
            extra=result_payload,
        )
        update_workflow_run(
            workflow_id,
            state="completed",
            status="completed",
            result_json=result_json,
        )
        return

    result_json = _compose_result_json(
        run,
        progress=100,
        message=error_text[:160],
        extra=result_payload if result_payload else {"status": "error"},
    )
    update_workflow_run(
        workflow_id,
        state="failed",
        status="failed",
        error_message=error_text,
        result_json=result_json,
    )


def _claim_next_task(*, lease_seconds: int) -> dict[str, Any] | None:
    claimed = claim_next_task(
        workflow_types=(_TRANSLATE_WORKFLOW_TYPE,),
        stage=_TRANSLATE_STAGE,
        lease_seconds=lease_seconds,
    )
    if not claimed:
        return None
    payload = claimed.get("input_json") if isinstance(claimed.get("input_json"), dict) else {}
    return {
        "task_id": str(claimed.get("task_id") or ""),
        "workflow_id": str(claimed.get("workflow_id") or ""),
        "volume_id": str(claimed.get("volume_id") or ""),
        "filename": str(claimed.get("filename") or ""),
        "box_id": int(claimed.get("box_id") or payload.get("box_id") or 0),
        "profile_id": str(claimed.get("profile_id") or payload.get("profile_id") or ""),
        "use_page_context": bool(payload.get("use_page_context", False)),
    }


def _requeue_stale_running_tasks(*, lease_seconds: int) -> int:
    _ = lease_seconds  # retained for call-site compatibility
    return requeue_stale_running_tasks(
        workflow_types=(_TRANSLATE_WORKFLOW_TYPE,),
        stage=_TRANSLATE_STAGE,
    )


async def _run_claimed_task(
    claimed: dict[str, Any],
    *,
    task_timeout_seconds: int,
) -> None:
    task_id = str(claimed.get("task_id") or "")
    workflow_id = str(claimed.get("workflow_id") or "")
    profile_id = str(claimed.get("profile_id") or "")
    if not task_id or not workflow_id or not profile_id:
        return

    try:
        profile = get_translation_profile(profile_id)
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

    if not profile.get("enabled", True):
        update_task_run(
            task_id,
            status="failed",
            finished=True,
            error_code="profile_disabled",
            error_detail="Selected translation profile is disabled",
        )
        await asyncio.to_thread(_update_workflow_progress_after_task, workflow_id)
        return

    prompt_file = resolve_translation_prompt_version(profile_id)

    def persist_attempt_event(event: dict[str, Any]) -> None:
        persist_task_attempt_event(
            task_id=task_id,
            attempt_event=event,
            tool_name="translate_tool",
            prompt_version=prompt_file,
            params_snapshot=build_reasoning_params_snapshot(event),
        )

    def on_attempt(event: dict[str, Any]) -> None:
        try:
            persist_attempt_event(event)
        except Exception:
            logger.exception(
                append_correlation(
                    "Failed to persist translation attempt event",
                    _translate_correlation(
                        component="jobs.db_translate.attempt",
                        task_id=task_id,
                        workflow_id=workflow_id,
                        volume_id=str(claimed.get("volume_id") or ""),
                        filename=str(claimed.get("filename") or ""),
                        box_id=int(claimed.get("box_id") or 0),
                        profile_id=profile_id,
                    ),
                )
            )

    outcome = await run_translation_task_async(
        profile_id=profile_id,
        volume_id=str(claimed.get("volume_id") or ""),
        filename=str(claimed.get("filename") or ""),
        box_id=int(claimed.get("box_id") or 0),
        use_page_context=bool(claimed.get("use_page_context", False)),
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


async def run_translate_db_worker(stop_event: Event) -> None:
    lease_seconds = max(30, _DEFAULT_LEASE_SECONDS)
    task_timeout_seconds = max(15, _DEFAULT_TASK_TIMEOUT_SECONDS)
    worker_count = max(1, _DEFAULT_WORKER_COUNT)

    try:
        stale = await asyncio.to_thread(
            _requeue_stale_running_tasks,
            lease_seconds=lease_seconds,
        )
    except Exception:
        logger.exception(
            append_correlation(
                "Failed to requeue stale translation tasks on startup",
                {"component": "jobs.db_translate.startup"},
            )
        )
        stale = 0
    if stale > 0:
        logger.info(
            append_correlation(
                "Requeued stale translation tasks",
                {"component": "jobs.db_translate.startup"},
                stale=stale,
            )
        )

    async def worker_loop(worker_idx: int) -> None:
        idle_sleep = float(_DEFAULT_IDLE_SLEEP_SECONDS)
        error_sleep = float(_DEFAULT_ERROR_SLEEP_SECONDS)
        while not stop_event.is_set():
            try:
                claimed = await asyncio.to_thread(_claim_next_task, lease_seconds=lease_seconds)
            except Exception:
                logger.exception(
                    append_correlation(
                        "Translate DB worker failed to claim task",
                        {"component": "jobs.db_translate.claim"},
                        worker_idx=worker_idx,
                    )
                )
                await asyncio.sleep(error_sleep)
                continue
            if not claimed:
                await asyncio.sleep(idle_sleep)
                continue
            try:
                await _run_claimed_task(
                    claimed,
                    task_timeout_seconds=task_timeout_seconds,
                )
            except Exception:
                logger.exception(
                    append_correlation(
                        "Translate DB worker failed claimed task",
                        _translate_correlation(
                            component="jobs.db_translate.task",
                            task_id=str(claimed.get("task_id") or ""),
                            workflow_id=str(claimed.get("workflow_id") or ""),
                            volume_id=str(claimed.get("volume_id") or ""),
                            filename=str(claimed.get("filename") or ""),
                            box_id=int(claimed.get("box_id") or 0),
                            profile_id=str(claimed.get("profile_id") or ""),
                        ),
                        worker_idx=worker_idx,
                    )
                )
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
                        logger.exception(
                            append_correlation(
                                "Translate DB worker failed to mark task as failed",
                                _translate_correlation(
                                    component="jobs.db_translate.task_mark_failed",
                                    task_id=task_id,
                                    workflow_id=workflow_id,
                                    volume_id=str(claimed.get("volume_id") or ""),
                                    filename=str(claimed.get("filename") or ""),
                                    box_id=int(claimed.get("box_id") or 0),
                                    profile_id=str(claimed.get("profile_id") or ""),
                                ),
                                worker_idx=worker_idx,
                            )
                        )
                if workflow_id:
                    try:
                        await asyncio.to_thread(_update_workflow_progress_after_task, workflow_id)
                    except Exception:
                        logger.exception(
                            append_correlation(
                                "Translate DB worker failed to update workflow progress after worker error",
                                _translate_correlation(
                                    component="jobs.db_translate.workflow_progress",
                                    task_id=task_id,
                                    workflow_id=workflow_id,
                                    volume_id=str(claimed.get("volume_id") or ""),
                                    filename=str(claimed.get("filename") or ""),
                                    box_id=int(claimed.get("box_id") or 0),
                                    profile_id=str(claimed.get("profile_id") or ""),
                                ),
                                worker_idx=worker_idx,
                            )
                        )
                await asyncio.sleep(error_sleep)

    workers = [asyncio.create_task(worker_loop(idx)) for idx in range(worker_count)]
    try:
        await asyncio.gather(*workers)
    finally:
        for task in workers:
            task.cancel()
