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
