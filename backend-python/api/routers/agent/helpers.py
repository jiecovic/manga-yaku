# backend-python/api/routers/agent/helpers.py
"""Shared helper functions for agent reply routes."""

from __future__ import annotations

import logging
import re
from typing import Any

from core.usecases.agent.engine import run_agent_chat_repair
from infra.db.agent_store import add_agent_message
from infra.db.llm_call_log_store import create_llm_call_log
from infra.logging.correlation import append_correlation, normalize_correlation

logger = logging.getLogger(__name__)

_REQUEST_ID_RE = re.compile(r"\b(req_[A-Za-z0-9]+)\b")


def extract_request_id(value: str) -> str | None:
    match = _REQUEST_ID_RE.search(value or "")
    if not match:
        return None
    return match.group(1)


def provider_error_fallback_reply(
    *,
    request_id: str | None,
    active_filename: str | None,
) -> str:
    page_suffix = f" for {active_filename}" if active_filename else ""
    if request_id:
        return (
            "The model provider returned a transient server error"
            f" ({request_id}){page_suffix} and no final text was produced. Please retry."
        )
    return (
        "The model provider returned a transient server error"
        f"{page_suffix} and no final text was produced. Please retry."
    )


def _truncate_text(value: str, *, limit: int = 2000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def sanitize_agent_log_payload(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            lowered = str(key).strip().lower()
            if lowered == "image_url" and isinstance(val, str) and val.startswith("data:image/"):
                out[key] = f"<redacted:data-url:{len(val)}>"
                continue
            out[key] = sanitize_agent_log_payload(val)
        return out
    if isinstance(value, list):
        return [sanitize_agent_log_payload(item) for item in value]
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return f"<redacted:data-url:{len(value)}>"
        return _truncate_text(value, limit=12000)
    return value


def _build_agent_request_excerpt(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in messages[-6:]:
        role = str(item.get("role") or "user").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return _truncate_text("\n\n".join(lines), limit=8000)


def log_agent_sdk_attempt(
    *,
    component: str,
    status: str,
    session_id: str,
    volume_id: str,
    filename: str | None,
    model_id: str,
    messages: list[dict[str, Any]],
    action_events: list[dict[str, str]] | None,
    response_text: str | None = None,
    error_detail: str | None = None,
    request_id: str | None = None,
    latency_ms: int | None = None,
    finish_reason: str | None = None,
    attempt: int | None = None,
    phase: str | None = None,
) -> None:
    try:
        payload = sanitize_agent_log_payload(
            {
                "phase": phase,
                "session_id": session_id,
                "volume_id": volume_id,
                "filename": filename,
                "model_id": model_id,
                "request_id": request_id,
                "messages": messages,
                "action_events": action_events or [],
                "response_text": response_text or "",
                "error_detail": error_detail,
            }
        )
        params_snapshot = normalize_correlation(
            {
                "component": component,
                "session_id": session_id,
                "volume_id": volume_id,
                "filename": filename,
                "model_id": model_id,
                "request_id": request_id,
            }
        )
        if phase:
            params_snapshot["phase"] = phase

        create_llm_call_log(
            provider="openai",
            api="responses_agents_sdk",
            component=component,
            status=status,
            model_id=model_id,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            error_detail=_truncate_text(error_detail or "", limit=8000) or None,
            params_snapshot=params_snapshot,
            request_excerpt=_build_agent_request_excerpt(messages),
            response_excerpt=_truncate_text(response_text or "", limit=8000) or None,
            payload=payload,
            attempt=attempt,
        )
    except Exception:
        logger.exception(
            append_correlation(
                "failed to persist agent sdk call log",
                normalize_correlation(
                    {
                        "component": component,
                        "session_id": session_id,
                        "volume_id": volume_id,
                        "filename": filename,
                        "model_id": model_id,
                        "request_id": request_id,
                    }
                ),
            )
        )


def is_provider_server_error(*, exc: Exception | None = None, text: str | None = None) -> bool:
    if exc is not None:
        err_type = str(getattr(exc, "type", "") or "").strip().lower()
        err_code = str(getattr(exc, "code", "") or "").strip().lower()
        if err_type == "server_error" or err_code == "server_error":
            return True
    lowered = str(text or "").strip().lower()
    return "server_error" in lowered


def try_text_repair_reply(
    *,
    messages: list[dict[str, Any]],
    action_events: list[dict[str, str]],
    session_id: str,
    volume_id: str,
    filename: str | None,
    model_id: str,
) -> str:
    try:
        repaired = run_agent_chat_repair(
            messages,
            action_events=action_events,
            model_id=model_id,
            volume_id=volume_id,
            current_filename=filename,
            session_id=session_id,
        ).strip()
    except Exception:
        logger.exception(
            append_correlation(
                "agent text repair fallback failed",
                normalize_correlation(
                    {
                        "component": "agent.reply.repair",
                        "session_id": session_id,
                        "volume_id": volume_id,
                        "filename": filename,
                        "model_id": model_id,
                    }
                ),
            )
        )
        return ""
    return repaired


def build_prompt_payload(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for item in history:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "tool":
            continue
        payload.append({"role": role or "user", "content": content})
    return payload


def persist_action_event_messages(
    session_id: str,
    action_events: list[dict[str, str]],
) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    for action in action_events:
        event_type = str(action.get("type") or "").strip()
        message = str(action.get("message") or "").strip()
        if event_type not in {"activity", "tool_called", "tool_output", "page_switch"}:
            continue
        if not message:
            continue
        meta: dict[str, Any] = {
            "source": "agent_timeline",
            "timelineOnly": True,
            "eventType": event_type,
        }
        tool_name = str(action.get("tool") or "").strip()
        filename = str(action.get("filename") or "").strip()
        if tool_name:
            meta["tool"] = tool_name
        if filename:
            meta["filename"] = filename
        persisted.append(
            add_agent_message(
                session_id,
                role="tool",
                content=message,
                meta=meta,
            )
        )
    return persisted


def persist_agent_warning_message(
    session_id: str,
    *,
    message: str,
    filename: str | None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "source": "agent_timeline",
        "timelineOnly": True,
        "eventType": "activity",
        "severity": "warning",
    }
    if filename:
        meta["filename"] = filename
    return add_agent_message(
        session_id,
        role="tool",
        content=message,
        meta=meta,
    )
