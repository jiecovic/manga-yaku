# backend-python/api/routers/logs/routes.py
"""HTTP routes for logs endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from api.schemas.logs import (
    LlmCallLogDetailResponse,
    LlmCallLogItem,
    LlmCallLogListResponse,
    LogFileContent,
    LogFileInfo,
    LogListResponse,
)
from config import safe_join
from fastapi import APIRouter, HTTPException
from infra.db.llm_call_log_store import (
    clear_llm_call_logs,
    delete_llm_call_log,
    get_llm_call_log,
    list_llm_call_logs,
)
from infra.logging.artifacts import page_translation_debug_dir

router = APIRouter(tags=["logs"])


def _log_dir() -> Path:
    return page_translation_debug_dir(create=False)


def _resolve_log_path(filename: str) -> Path:
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    try:
        return safe_join(_log_dir(), filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid filename") from exc


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_llm_log_item(raw: dict) -> LlmCallLogItem:
    return LlmCallLogItem(
        id=str(raw.get("id") or ""),
        provider=str(raw.get("provider") or "openai"),
        api=str(raw.get("api") or ""),
        component=str(raw.get("component") or ""),
        status=str(raw.get("status") or ""),
        model_id=str(raw.get("model_id")) if raw.get("model_id") else None,
        job_id=str(raw.get("job_id")) if raw.get("job_id") else None,
        workflow_run_id=(str(raw.get("workflow_run_id")) if raw.get("workflow_run_id") else None),
        task_run_id=str(raw.get("task_run_id")) if raw.get("task_run_id") else None,
        session_id=str(raw.get("session_id")) if raw.get("session_id") else None,
        volume_id=str(raw.get("volume_id")) if raw.get("volume_id") else None,
        filename=str(raw.get("filename")) if raw.get("filename") else None,
        request_id=str(raw.get("request_id")) if raw.get("request_id") else None,
        box_id=_optional_int(raw.get("box_id")),
        profile_id=str(raw.get("profile_id")) if raw.get("profile_id") else None,
        attempt=int(raw["attempt"]) if raw.get("attempt") is not None else None,
        latency_ms=(int(raw["latency_ms"]) if raw.get("latency_ms") is not None else None),
        finish_reason=(str(raw.get("finish_reason")) if raw.get("finish_reason") else None),
        input_tokens=(int(raw["input_tokens"]) if raw.get("input_tokens") is not None else None),
        output_tokens=(int(raw["output_tokens"]) if raw.get("output_tokens") is not None else None),
        total_tokens=(int(raw["total_tokens"]) if raw.get("total_tokens") is not None else None),
        error_detail=str(raw.get("error_detail")) if raw.get("error_detail") else None,
        has_payload=bool(raw.get("has_payload")),
        created_at=int(raw.get("created_at") or 0),
    )


@router.get("/logs/llm-calls", response_model=LlmCallLogListResponse)
async def list_llm_logs(
    limit: int = 200,
    component: str | None = None,
    status: str | None = None,
) -> LlmCallLogListResponse:
    """List llm logs."""
    normalized_status = str(status or "").strip().lower() if status else None
    if normalized_status and normalized_status not in {"success", "error"}:
        raise HTTPException(status_code=400, detail="status must be success or error")

    logs = list_llm_call_logs(
        limit=limit,
        component=str(component or "").strip() or None,
        status=normalized_status,
    )
    return LlmCallLogListResponse(logs=[_to_llm_log_item(item) for item in logs])


@router.get("/logs/llm-calls/{log_id}", response_model=LlmCallLogDetailResponse)
async def get_llm_log(log_id: str) -> LlmCallLogDetailResponse:
    """Return llm log."""
    row = get_llm_call_log(log_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Log not found")
    return LlmCallLogDetailResponse(
        log=_to_llm_log_item(row),
        params_snapshot=row.get("params_snapshot"),
        request_excerpt=str(row.get("request_excerpt") or ""),
        response_excerpt=str(row.get("response_excerpt") or ""),
        payload_json=row.get("payload_json"),
        payload_raw=row.get("payload_raw"),
    )


@router.delete("/logs/llm-calls/{log_id}")
async def delete_llm_log(log_id: str) -> dict[str, int]:
    """Delete llm log."""
    deleted = delete_llm_call_log(log_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"deleted": 1}


@router.delete("/logs/llm-calls")
async def delete_llm_logs() -> dict[str, int]:
    """Delete llm logs."""
    deleted = clear_llm_call_logs()
    return {"deleted": deleted}


@router.get("/logs/page-translation", response_model=LogListResponse)
async def list_page_translation_logs() -> LogListResponse:
    """List page-translation logs."""
    root = _log_dir()
    if not root.exists():
        return LogListResponse(files=[])
    if not root.is_dir():
        raise HTTPException(status_code=500, detail="Log directory invalid")

    files: list[LogFileInfo] = []
    for item in root.iterdir():
        if not item.is_file():
            continue
        if item.name.startswith("."):
            continue
        stat = item.stat()
        files.append(
            LogFileInfo(
                name=item.name,
                size=stat.st_size,
                updated_at=item.stat().st_mtime_ns // 1_000_000_000,
            )
        )

    files.sort(key=lambda entry: entry.updated_at, reverse=True)
    return LogListResponse(files=files)


@router.get("/logs/page-translation/{filename}", response_model=LogFileContent)
async def get_page_translation_log(filename: str) -> LogFileContent:
    """Return page-translation log."""
    path = _resolve_log_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Invalid log file")

    text = path.read_text(encoding="utf-8", errors="replace")
    stat = path.stat()
    try:
        content = json.loads(text)
        return LogFileContent(
            name=path.name,
            size=stat.st_size,
            updated_at=stat.st_mtime_ns // 1_000_000_000,
            is_json=True,
            content=content,
        )
    except json.JSONDecodeError:
        return LogFileContent(
            name=path.name,
            size=stat.st_size,
            updated_at=stat.st_mtime_ns // 1_000_000_000,
            is_json=False,
            raw=text,
        )


@router.delete("/logs/page-translation/{filename}")
async def delete_page_translation_log(filename: str) -> dict[str, int]:
    """Delete page-translation log."""
    path = _resolve_log_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Invalid log file")
    path.unlink()
    return {"deleted": 1}


@router.delete("/logs/page-translation")
async def delete_page_translation_logs() -> dict[str, int]:
    """Delete page-translation logs."""
    root = _log_dir()
    if not root.exists():
        return {"deleted": 0}
    if not root.is_dir():
        raise HTTPException(status_code=500, detail="Log directory invalid")
    deleted = 0
    for item in root.iterdir():
        if item.is_file():
            item.unlink()
            deleted += 1
    return {"deleted": deleted}
