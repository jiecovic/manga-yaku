# backend-python/api/schemas/logs.py
"""Schemas for log browsing and LLM call telemetry API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LogFileInfo(BaseModel):
    """Metadata for one log file in the logs directory."""

    name: str
    size: int
    updated_at: int


class LogListResponse(BaseModel):
    """Response wrapper for the log file listing endpoint."""

    files: list[LogFileInfo]


class LogFileContent(BaseModel):
    """Structured log file payload with parsed JSON or raw text."""

    name: str
    size: int
    updated_at: int
    is_json: bool
    content: Any | None = None
    raw: str | None = None


class LlmCallLogItem(BaseModel):
    """Summary row for one persisted LLM API call."""

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
    """Response wrapper for paged/sliced LLM call log summaries."""

    logs: list[LlmCallLogItem]


class LlmCallLogDetailResponse(BaseModel):
    """Detailed payload for one LLM call, including excerpts and snapshots."""

    log: LlmCallLogItem
    params_snapshot: dict[str, Any] | None = None
    request_excerpt: str | None = None
    response_excerpt: str | None = None
    payload_json: Any | None = None
    payload_raw: str | None = None
