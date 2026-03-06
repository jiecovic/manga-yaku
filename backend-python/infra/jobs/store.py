# backend-python/infra/jobs/store.py
"""In-memory job store and stream subscription primitives."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import Request
from pydantic import BaseModel

from infra.http import cors_headers_for_stream as build_cors_headers
from infra.logging.ansi import strip_ansi
from infra.logging.correlation import append_correlation


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    finished = "finished"
    failed = "failed"
    canceled = "canceled"


class Job(BaseModel):
    id: str
    type: str
    status: JobStatus
    created_at: float
    updated_at: float
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    progress: float | None = None
    message: str | None = None
    metrics: dict[str, Any] | None = None
    warnings: list[str] | None = None


class JobPublic(BaseModel):
    id: str
    type: str
    status: JobStatus
    created_at: float
    updated_at: float
    result: dict[str, Any] | None = None
    error: str | None = None
    payload: dict[str, Any]
    progress: float | None = None
    message: str | None = None
    metrics: dict[str, Any] | None = None
    warnings: list[str] | None = None


logger = logging.getLogger(__name__)


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _sanitize_json_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(item) for item in value]
    return value


class JobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.subscribers: set[asyncio.Queue[str]] = set()
        self.logs: dict[str, Path] = {}
        self.shutdown_event = threading.Event()

    @staticmethod
    def now() -> float:
        return time.time()

    def add_job(self, job: Job) -> None:
        self.jobs[job.id] = job
        self.broadcast_snapshot()

    def update_job(self, job: Job, **updates: Any) -> Job:
        if job.id not in self.jobs:
            return job
        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = self.now()
        self.jobs[job.id] = job
        self.broadcast_snapshot()
        return job

    def remove_job(self, job_id: str) -> bool:
        existed = job_id in self.jobs or job_id in self.logs
        self.jobs.pop(job_id, None)
        self.logs.pop(job_id, None)
        if existed:
            self.broadcast_snapshot()
        return existed

    def get_job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def public_job(self, job: Job) -> JobPublic:
        return JobPublic(
            id=job.id,
            type=job.type,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            result=job.result,
            error=job.error,
            payload=job.payload,
            progress=job.progress,
            message=job.message,
            metrics=job.metrics,
            warnings=job.warnings,
        )

    def snapshot_payload(self) -> dict:
        return {"jobs": [self.public_job(job).model_dump() for job in self.jobs.values()]}

    @staticmethod
    def _safe_json_dumps(payload: dict) -> str:
        try:
            return json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            logger.warning(
                append_correlation(
                    f"Failed to serialize job payload: {exc}",
                    {"component": "jobs.store.serialize"},
                )
            )
            sanitized = _sanitize_json_value(payload)
            return json.dumps(sanitized, allow_nan=False, default=str)

    @staticmethod
    def format_sse(payload: dict) -> str:
        data = JobStore._safe_json_dumps(payload)
        return f"data: {data}\n\n"

    @staticmethod
    def format_log_sse(line: str) -> str:
        clean = strip_ansi(line)
        return f"data: {clean}\n\n"

    @staticmethod
    def _queue_latest(queue: asyncio.Queue[str], data: str) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    def broadcast_snapshot(self) -> None:
        if not self.subscribers:
            return
        payload = self.snapshot_payload()
        data = self._safe_json_dumps(payload)
        for queue in list(self.subscribers):
            self._queue_latest(queue, data)

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self.subscribers.discard(queue)

    @staticmethod
    def cors_headers_for_stream(request: Request) -> dict[str, str]:
        return build_cors_headers(request)
