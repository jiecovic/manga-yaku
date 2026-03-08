# backend-python/api/routers/agent/reply_stream_fallback.py
"""Fallback and recovery helpers for streamed agent replies."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from core.usecases.agent.engine import run_agent_chat
from core.usecases.agent.grounding.turn_state import (
    get_active_page_text_box_count,
    sanitize_agent_reply_text,
    stale_context_warning_message,
)
from infra.db.agent_store import add_agent_message
from infra.logging.correlation import append_correlation

from .helpers import (
    extract_request_id,
    is_provider_server_error,
    log_agent_sdk_attempt,
    persist_action_event_messages,
    provider_error_fallback_reply,
    try_text_repair_reply,
)

logger = logging.getLogger(__name__)


class StreamReplyFallbackWorker(Protocol):
    """Minimal worker surface required by stream fallback helpers."""

    session_id: str
    volume_id: str
    model_id: str
    payload: list[dict[str, object]]
    runtime_active_filename: str | None
    action_events: list[dict[str, str]]
    stream_started_at: float
    stop_event: object

    def _corr(self, **extras: object) -> dict[str, object]: ...

    def _emit(self, payload: dict[str, object]) -> None: ...


def recover_empty_primary_output(worker: StreamReplyFallbackWorker) -> tuple[str, bool]:
    """Recover after the primary stream produced no final text."""
    primary_stream_used_retry = True
    log_agent_sdk_attempt(
        component="agent.chat.stream.sdk",
        status="error",
        session_id=worker.session_id,
        volume_id=worker.volume_id,
        filename=worker.runtime_active_filename,
        model_id=worker.model_id,
        messages=worker.payload,
        action_events=worker.action_events,
        error_detail="Streamed SDK run completed without final text",
        latency_ms=round((time.monotonic() - worker.stream_started_at) * 1000),
        finish_reason="empty_output",
        phase="stream_primary",
    )
    logger.warning(
        append_correlation(
            "agent stream empty output; retrying sync once",
            worker._corr(),
        )
    )

    retry_started_at = time.monotonic()
    try:
        retry_text = run_agent_chat(
            worker.payload,
            model_id=worker.model_id,
            volume_id=worker.volume_id,
            current_filename=worker.runtime_active_filename,
            session_id=worker.session_id,
        ).strip()
    except Exception as retry_exc:
        retry_error_text = str(retry_exc).strip()
        retry_request_id = str(getattr(retry_exc, "request_id", "") or "").strip()
        if not retry_request_id:
            retry_request_id = extract_request_id(retry_error_text)
        log_agent_sdk_attempt(
            component="agent.chat.sync.sdk",
            status="error",
            session_id=worker.session_id,
            volume_id=worker.volume_id,
            filename=worker.runtime_active_filename,
            model_id=worker.model_id,
            messages=worker.payload,
            action_events=worker.action_events,
            error_detail=retry_error_text,
            request_id=retry_request_id,
            latency_ms=round((time.monotonic() - retry_started_at) * 1000),
            finish_reason=(
                "provider_error"
                if is_provider_server_error(exc=retry_exc, text=retry_error_text)
                else "exception"
            ),
            phase="stream_empty_retry_sync",
        )
        if is_provider_server_error(exc=retry_exc, text=retry_error_text):
            response_text = provider_error_fallback_reply(
                request_id=retry_request_id,
                active_filename=worker.runtime_active_filename,
            )
            worker.action_events.append(
                {
                    "type": "activity",
                    "message": (
                        f"Streaming empty-output retry hit provider server error ({retry_request_id}); returned deterministic provider fallback"
                        if retry_request_id
                        else "Streaming empty-output retry hit provider server error; returned deterministic provider fallback"
                    ),
                }
            )
            logger.warning(
                append_correlation(
                    "agent stream empty-output sync retry provider error",
                    worker._corr(request_id=retry_request_id),
                )
            )
            return response_text, primary_stream_used_retry

        logger.exception(
            append_correlation(
                "agent stream empty-output sync retry failed",
                worker._corr(),
            )
        )
        return "", primary_stream_used_retry

    if retry_text:
        log_agent_sdk_attempt(
            component="agent.chat.sync.sdk",
            status="success",
            session_id=worker.session_id,
            volume_id=worker.volume_id,
            filename=worker.runtime_active_filename,
            model_id=worker.model_id,
            messages=worker.payload,
            action_events=worker.action_events,
            response_text=retry_text,
            latency_ms=round((time.monotonic() - retry_started_at) * 1000),
            finish_reason="completed",
            phase="stream_empty_retry_sync",
        )
        worker.action_events.append(
            {
                "type": "activity",
                "message": "Streaming produced empty output; recovered via sync retry",
            }
        )
        return retry_text, primary_stream_used_retry

    repair_text = try_text_repair_reply(
        messages=worker.payload,
        action_events=worker.action_events,
        session_id=worker.session_id,
        volume_id=worker.volume_id,
        filename=worker.runtime_active_filename,
        model_id=worker.model_id,
    )
    if repair_text:
        worker.action_events.append(
            {
                "type": "activity",
                "message": "Recovered empty output via text-only repair fallback",
            }
        )
        return repair_text, primary_stream_used_retry

    log_agent_sdk_attempt(
        component="agent.chat.sync.sdk",
        status="error",
        session_id=worker.session_id,
        volume_id=worker.volume_id,
        filename=worker.runtime_active_filename,
        model_id=worker.model_id,
        messages=worker.payload,
        action_events=worker.action_events,
        error_detail="Sync retry after empty stream returned no final text",
        latency_ms=round((time.monotonic() - retry_started_at) * 1000),
        finish_reason="empty_output",
        phase="stream_empty_retry_sync",
    )
    worker.action_events.append(
        {
            "type": "activity",
            "message": "Streaming and sync retry returned empty output; applied deterministic fallback",
        }
    )
    return "", primary_stream_used_retry


def handle_stream_failure(worker: StreamReplyFallbackWorker, exc: Exception) -> None:
    """Handle primary-stream failure and attempt the sync fallback path."""
    error_text = str(exc).strip()
    request_id = str(getattr(exc, "request_id", "") or "").strip()
    if not request_id:
        request_id = extract_request_id(error_text)

    provider_server_error = is_provider_server_error(exc=exc, text=error_text)
    log_agent_sdk_attempt(
        component="agent.chat.stream.sdk",
        status="error",
        session_id=worker.session_id,
        volume_id=worker.volume_id,
        filename=worker.runtime_active_filename,
        model_id=worker.model_id,
        messages=worker.payload,
        action_events=worker.action_events,
        error_detail=error_text,
        request_id=request_id,
        latency_ms=round((time.monotonic() - worker.stream_started_at) * 1000),
        finish_reason="provider_error" if provider_server_error else "exception",
        phase="stream_primary",
    )
    if provider_server_error:
        logger.warning(
            append_correlation(
                "agent stream provider server error; attempting sync fallback",
                worker._corr(request_id=request_id),
            )
        )
    else:
        logger.exception(
            append_correlation("agent stream failed", worker._corr(request_id=request_id))
        )
    if request_id:
        log_fn = logger.warning if provider_server_error else logger.error
        log_fn(
            append_correlation("agent stream provider error", worker._corr(request_id=request_id))
        )

    if not worker.stop_event.is_set() and _emit_sync_fallback_reply(worker, request_id=request_id):
        return

    worker._emit({"type": "error", "message": error_text})


def _emit_sync_fallback_reply(
    worker: StreamReplyFallbackWorker,
    *,
    request_id: str | None,
) -> bool:
    try:
        logger.info(append_correlation("agent stream fallback sync", worker._corr()))
        fallback_text = ""
        for attempt in range(2):
            fallback_attempt_started_at = time.monotonic()
            try:
                fallback_text = run_agent_chat(
                    worker.payload,
                    model_id=worker.model_id,
                    volume_id=worker.volume_id,
                    current_filename=worker.runtime_active_filename,
                    session_id=worker.session_id,
                ).strip()
            except Exception as fallback_attempt_exc:
                fallback_attempt_text = str(fallback_attempt_exc).strip()
                fallback_attempt_request_id = str(
                    getattr(fallback_attempt_exc, "request_id", "") or ""
                ).strip()
                if not fallback_attempt_request_id:
                    fallback_attempt_request_id = extract_request_id(fallback_attempt_text)
                if not request_id and fallback_attempt_request_id:
                    request_id = fallback_attempt_request_id
                log_agent_sdk_attempt(
                    component="agent.chat.sync.sdk",
                    status="error",
                    session_id=worker.session_id,
                    volume_id=worker.volume_id,
                    filename=worker.runtime_active_filename,
                    model_id=worker.model_id,
                    messages=worker.payload,
                    action_events=worker.action_events,
                    error_detail=fallback_attempt_text,
                    request_id=fallback_attempt_request_id,
                    latency_ms=round((time.monotonic() - fallback_attempt_started_at) * 1000),
                    finish_reason=(
                        "provider_error"
                        if is_provider_server_error(
                            exc=fallback_attempt_exc,
                            text=fallback_attempt_text,
                        )
                        else "exception"
                    ),
                    phase="stream_fallback_sync",
                    attempt=attempt + 1,
                )
                if attempt == 0 and is_provider_server_error(
                    exc=fallback_attempt_exc,
                    text=fallback_attempt_text,
                ):
                    logger.warning(
                        append_correlation(
                            "agent stream fallback sync provider error; retrying once",
                            worker._corr(
                                request_id=fallback_attempt_request_id,
                                attempt=attempt + 1,
                            ),
                        )
                    )
                    continue
                raise

            if fallback_text:
                log_agent_sdk_attempt(
                    component="agent.chat.sync.sdk",
                    status="success",
                    session_id=worker.session_id,
                    volume_id=worker.volume_id,
                    filename=worker.runtime_active_filename,
                    model_id=worker.model_id,
                    messages=worker.payload,
                    action_events=worker.action_events,
                    response_text=fallback_text,
                    request_id=request_id,
                    latency_ms=round((time.monotonic() - fallback_attempt_started_at) * 1000),
                    finish_reason="completed",
                    phase="stream_fallback_sync",
                    attempt=attempt + 1,
                )
                break

            if attempt == 0:
                log_agent_sdk_attempt(
                    component="agent.chat.sync.sdk",
                    status="error",
                    session_id=worker.session_id,
                    volume_id=worker.volume_id,
                    filename=worker.runtime_active_filename,
                    model_id=worker.model_id,
                    messages=worker.payload,
                    action_events=worker.action_events,
                    error_detail="Sync fallback attempt completed without final text",
                    request_id=request_id,
                    latency_ms=round((time.monotonic() - fallback_attempt_started_at) * 1000),
                    finish_reason="empty_output",
                    phase="stream_fallback_sync",
                    attempt=attempt + 1,
                )
                logger.warning(
                    append_correlation(
                        "agent stream fallback attempt empty; retrying once",
                        worker._corr(attempt=attempt + 1),
                    )
                )

        return _emit_terminal_fallback_reply(
            worker,
            fallback_text=fallback_text,
            request_id=request_id,
        )
    except Exception as fallback_exc:
        fallback_error_text = str(fallback_exc).strip()
        fallback_request_id = str(getattr(fallback_exc, "request_id", "") or "").strip()
        if not fallback_request_id:
            fallback_request_id = extract_request_id(fallback_error_text)
        if is_provider_server_error(exc=fallback_exc, text=fallback_error_text):
            final_request_id = fallback_request_id or request_id
            log_agent_sdk_attempt(
                component="agent.chat.sync.sdk",
                status="error",
                session_id=worker.session_id,
                volume_id=worker.volume_id,
                filename=worker.runtime_active_filename,
                model_id=worker.model_id,
                messages=worker.payload,
                action_events=worker.action_events,
                error_detail=fallback_error_text,
                request_id=final_request_id,
                finish_reason="provider_error",
                phase="stream_fallback_final_reply",
            )
            fallback_text = provider_error_fallback_reply(
                request_id=final_request_id,
                active_filename=worker.runtime_active_filename,
            )
            fallback_actions = list(worker.action_events)
            fallback_actions.append(
                {
                    "type": "activity",
                    "message": (
                        f"Streaming+fallback hit provider server error ({final_request_id}); returned deterministic provider message"
                        if final_request_id
                        else "Streaming+fallback hit provider server error; returned deterministic provider message"
                    ),
                }
            )
            _emit_fallback_message(
                worker,
                fallback_text=fallback_text,
                fallback_actions=fallback_actions,
            )
            logger.warning(
                append_correlation(
                    "agent stream fallback provider error; returned deterministic provider fallback",
                    worker._corr(request_id=final_request_id),
                )
            )
            return True

        logger.exception(
            append_correlation(
                "agent stream fallback failed",
                worker._corr(request_id=fallback_request_id),
            )
        )
        return False


def _emit_terminal_fallback_reply(
    worker: StreamReplyFallbackWorker,
    *,
    fallback_text: str,
    request_id: str | None,
) -> bool:
    fallback_text_box_count = get_active_page_text_box_count(
        volume_id=worker.volume_id,
        current_filename=worker.runtime_active_filename,
    )
    fallback_text, guard_reason = sanitize_agent_reply_text(
        response_text=fallback_text,
        messages=worker.payload,
        active_filename=worker.runtime_active_filename,
        active_text_box_count=fallback_text_box_count,
    )
    if guard_reason == "empty_output":
        repair_text = try_text_repair_reply(
            messages=worker.payload,
            action_events=worker.action_events,
            session_id=worker.session_id,
            volume_id=worker.volume_id,
            filename=worker.runtime_active_filename,
            model_id=worker.model_id,
        )
        if repair_text:
            fallback_text, guard_reason = sanitize_agent_reply_text(
                response_text=repair_text,
                messages=worker.payload,
                active_filename=worker.runtime_active_filename,
                active_text_box_count=fallback_text_box_count,
            )
            if guard_reason != "empty_output":
                worker.action_events.append(
                    {
                        "type": "activity",
                        "message": "Recovered fallback empty output via text-only repair fallback",
                    }
                )
            else:
                repair_text = ""
        if not repair_text:
            log_agent_sdk_attempt(
                component="agent.chat.sync.sdk",
                status="error",
                session_id=worker.session_id,
                volume_id=worker.volume_id,
                filename=worker.runtime_active_filename,
                model_id=worker.model_id,
                messages=worker.payload,
                action_events=worker.action_events,
                error_detail="Sync fallback returned no final text after retries",
                request_id=request_id,
                finish_reason="empty_output",
                phase="stream_fallback_sync",
            )
            fallback_text = provider_error_fallback_reply(
                request_id=request_id,
                active_filename=worker.runtime_active_filename,
            )
            guard_reason = "provider_error_empty"

    fallback_actions = list(worker.action_events)
    if guard_reason == "stale_context_warning":
        fallback_actions.append(
            {
                "type": "activity",
                "message": stale_context_warning_message(
                    active_filename=worker.runtime_active_filename,
                    active_text_box_count=fallback_text_box_count,
                ),
            }
        )
    elif guard_reason == "empty_output_no_boxes":
        fallback_actions.append(
            {
                "type": "activity",
                "message": "Fallback produced empty output; returned no-box deterministic reply",
            }
        )
    elif guard_reason == "empty_output":
        fallback_actions.append(
            {
                "type": "activity",
                "message": "Fallback produced empty output; returned deterministic reply",
            }
        )
    elif guard_reason == "provider_error_empty":
        fallback_actions.append(
            {
                "type": "activity",
                "message": (
                    f"Provider server error ({request_id}); returned deterministic provider fallback"
                    if request_id
                    else "Provider server error; returned deterministic provider fallback"
                ),
            }
        )
    fallback_actions.append(
        {
            "type": "activity",
            "message": (
                f"Streaming failed ({request_id}), used sync fallback reply"
                if request_id
                else "Streaming failed, used sync fallback reply"
            ),
        }
    )
    _emit_fallback_message(
        worker,
        fallback_text=fallback_text,
        fallback_actions=fallback_actions,
    )
    log_agent_sdk_attempt(
        component="agent.chat.sync.sdk",
        status="error" if guard_reason == "provider_error_empty" else "success",
        session_id=worker.session_id,
        volume_id=worker.volume_id,
        filename=worker.runtime_active_filename,
        model_id=worker.model_id,
        messages=worker.payload,
        action_events=fallback_actions,
        response_text=fallback_text,
        request_id=request_id,
        error_detail=(
            "Provider error fallback reply used because no final text was produced"
            if guard_reason == "provider_error_empty"
            else None
        ),
        finish_reason="provider_error" if guard_reason == "provider_error_empty" else "completed",
        phase="stream_fallback_final_reply",
    )
    logger.info(
        append_correlation(
            "agent stream fallback done",
            worker._corr(request_id=request_id),
            response_chars=len(fallback_text),
        )
    )
    return True


def _emit_fallback_message(
    worker: StreamReplyFallbackWorker,
    *,
    fallback_text: str,
    fallback_actions: list[dict[str, str]],
) -> None:
    fallback_meta: dict[str, object] = {"source": "agent_reply_fallback"}
    if fallback_actions:
        fallback_meta["actions"] = fallback_actions[-40:]
    persisted_timeline = persist_action_event_messages(worker.session_id, fallback_actions)
    fallback_message = add_agent_message(
        worker.session_id,
        role="assistant",
        content=fallback_text,
        meta=fallback_meta,
    )
    worker._emit(
        {
            "type": "done",
            "message": fallback_message,
            "timelineMessages": persisted_timeline,
        }
    )
