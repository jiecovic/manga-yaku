# backend-python/api/schemas/logs.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LogFileInfo(BaseModel):
    name: str
    size: int
    updated_at: int


class LogListResponse(BaseModel):
    files: list[LogFileInfo]


class LogFileContent(BaseModel):
    name: str
    size: int
    updated_at: int
    is_json: bool
    content: Any | None = None
    raw: str | None = None


class LlmCallLogItem(BaseModel):
    id: str
    provider: str
    api: str
    component: str
    status: str
    model_id: str | None = None
    job_id: str | None = None
    workflow_run_id: str | None = None
    task_run_id: str | None = None
    attempt: int | None = None
    latency_ms: int | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    error_detail: str | None = None
    has_payload: bool = False
    created_at: int


class LlmCallLogListResponse(BaseModel):
    logs: list[LlmCallLogItem]


class LlmCallLogDetailResponse(BaseModel):
    log: LlmCallLogItem
    params_snapshot: dict[str, Any] | None = None
    request_excerpt: str | None = None
    response_excerpt: str | None = None
    payload_json: Any | None = None
    payload_raw: str | None = None
