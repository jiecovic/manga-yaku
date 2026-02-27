from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from config import DEBUG_LOGS_DIR
from sqlalchemy import desc

from .db import LlmCallLog, get_session

LLM_CALLS_DIR = DEBUG_LOGS_DIR / "llm_calls"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: str) -> UUID:
    return UUID(str(value).strip())


def _ensure_log_dir() -> Path:
    LLM_CALLS_DIR.mkdir(parents=True, exist_ok=True)
    return LLM_CALLS_DIR


def _safe_excerpt(value: Any, *, limit: int = 8000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=True, default=str)
        except Exception:
            text = repr(value)
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _row_to_dict(row: LlmCallLog) -> dict[str, Any]:
    created_at = row.created_at
    created_unix = int(created_at.timestamp()) if created_at else 0
    return {
        "id": str(row.id),
        "provider": row.provider,
        "api": row.api,
        "component": row.component,
        "status": row.status,
        "model_id": row.model_id,
        "job_id": row.job_id,
        "workflow_run_id": row.workflow_run_id,
        "task_run_id": row.task_run_id,
        "attempt": row.attempt,
        "latency_ms": row.latency_ms,
        "finish_reason": row.finish_reason,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "total_tokens": row.total_tokens,
        "error_detail": row.error_detail,
        "params_snapshot": row.params_snapshot,
        "request_excerpt": row.request_excerpt,
        "response_excerpt": row.response_excerpt,
        "payload_path": row.payload_path,
        "has_payload": bool(row.payload_path),
        "created_at": created_unix,
    }


def create_llm_call_log(
    *,
    provider: str,
    api: str,
    component: str,
    status: str,
    model_id: str | None = None,
    job_id: str | None = None,
    workflow_run_id: str | None = None,
    task_run_id: str | None = None,
    attempt: int | None = None,
    latency_ms: int | None = None,
    finish_reason: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    error_detail: str | None = None,
    params_snapshot: dict[str, Any] | None = None,
    request_excerpt: Any = None,
    response_excerpt: Any = None,
    payload: dict[str, Any] | None = None,
) -> str:
    now = _utc_now()
    payload_path: str | None = None

    with get_session() as session:
        row = LlmCallLog(
            provider=str(provider or "openai"),
            api=str(api or "unknown"),
            component=str(component or "unknown"),
            status=str(status or "success"),
            model_id=str(model_id) if model_id else None,
            job_id=str(job_id) if job_id else None,
            workflow_run_id=str(workflow_run_id) if workflow_run_id else None,
            task_run_id=str(task_run_id) if task_run_id else None,
            attempt=attempt if attempt and attempt >= 1 else None,
            latency_ms=max(0, int(latency_ms)) if latency_ms is not None else None,
            finish_reason=str(finish_reason) if finish_reason else None,
            input_tokens=max(0, int(input_tokens)) if input_tokens is not None else None,
            output_tokens=max(0, int(output_tokens)) if output_tokens is not None else None,
            total_tokens=max(0, int(total_tokens)) if total_tokens is not None else None,
            error_detail=str(error_detail) if error_detail else None,
            params_snapshot=params_snapshot or None,
            request_excerpt=_safe_excerpt(request_excerpt) or None,
            response_excerpt=_safe_excerpt(response_excerpt) or None,
            created_at=now,
        )
        session.add(row)
        session.flush()
        log_id = str(row.id)

        if payload is not None:
            path = _ensure_log_dir() / f"{log_id}.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2, default=str),
                encoding="utf-8",
            )
            payload_path = str(path)
            row.payload_path = payload_path
            session.flush()

    return log_id


def list_llm_call_logs(
    *,
    limit: int = 200,
    component: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 1000))
    with get_session() as session:
        query = session.query(LlmCallLog)
        if component:
            query = query.filter(LlmCallLog.component == component)
        if status:
            query = query.filter(LlmCallLog.status == status)
        rows = (
            query.order_by(desc(LlmCallLog.created_at))
            .limit(safe_limit)
            .all()
        )
        return [_row_to_dict(row) for row in rows]


def get_llm_call_log(log_id: str) -> dict[str, Any] | None:
    try:
        parsed = _parse_uuid(log_id)
    except Exception:
        return None
    with get_session() as session:
        row = session.get(LlmCallLog, parsed)
        if row is None:
            return None
        data = _row_to_dict(row)
        payload_text = None
        payload_path = row.payload_path
        if payload_path:
            path = Path(payload_path)
            if path.is_file():
                payload_text = path.read_text(encoding="utf-8", errors="replace")
        data["payload_raw"] = payload_text
        if payload_text:
            try:
                data["payload_json"] = json.loads(payload_text)
            except Exception:
                data["payload_json"] = None
        else:
            data["payload_json"] = None
        return data


def delete_llm_call_log(log_id: str) -> bool:
    try:
        parsed = _parse_uuid(log_id)
    except Exception:
        return False

    payload_path: str | None = None
    with get_session() as session:
        row = session.get(LlmCallLog, parsed)
        if row is None:
            return False
        payload_path = row.payload_path
        session.delete(row)

    if payload_path:
        path = Path(payload_path)
        if path.is_file():
            try:
                path.unlink()
            except Exception:
                pass
    return True


def clear_llm_call_logs() -> int:
    with get_session() as session:
        rows = session.query(LlmCallLog).all()
        payload_paths = [row.payload_path for row in rows if row.payload_path]
        count = len(rows)
        for row in rows:
            session.delete(row)

    for payload_path in payload_paths:
        path = Path(str(payload_path))
        if path.is_file():
            try:
                path.unlink()
            except Exception:
                pass
    return count
