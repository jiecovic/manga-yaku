# backend-python/api/routers/logs.py
from __future__ import annotations

import json
from pathlib import Path

from api.schemas.logs import LogFileContent, LogFileInfo, LogListResponse
from config import AGENT_DEBUG_DIR, safe_join
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["logs"])


def _log_dir() -> Path:
    return AGENT_DEBUG_DIR / "translate_page"


def _resolve_log_path(filename: str) -> Path:
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    try:
        return safe_join(_log_dir(), filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid filename") from exc


@router.get("/logs/agent/translate_page", response_model=LogListResponse)
async def list_agent_translate_logs() -> LogListResponse:
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
                updated_at=item.stat().st_mtime_ns
                // 1_000_000_000,
            )
        )

    files.sort(key=lambda entry: entry.updated_at, reverse=True)
    return LogListResponse(files=files)


@router.get("/logs/agent/translate_page/{filename}", response_model=LogFileContent)
async def get_agent_translate_log(filename: str) -> LogFileContent:
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


@router.delete("/logs/agent/translate_page/{filename}")
async def delete_agent_translate_log(filename: str) -> dict[str, int]:
    path = _resolve_log_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Invalid log file")
    path.unlink()
    return {"deleted": 1}


@router.delete("/logs/agent/translate_page")
async def delete_agent_translate_logs() -> dict[str, int]:
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
