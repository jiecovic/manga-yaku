# backend-python/infra/logging/artifacts.py
"""Shared helpers for file-backed debug artifacts and payload captures."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DEBUG_LOGS_DIR

_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _clean_token(value: str, *, fallback: str = "artifact") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    cleaned = _SAFE_TOKEN_RE.sub("_", text).strip("._-")
    return cleaned or fallback


def artifact_root(*, create: bool = True) -> Path:
    if create:
        DEBUG_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return DEBUG_LOGS_DIR


def artifact_dir(*parts: str, create: bool = True) -> Path:
    path = artifact_root(create=create)
    for part in parts:
        cleaned = _clean_token(part, fallback="")
        if cleaned:
            path = path / cleaned
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def llm_calls_dir(*, create: bool = True) -> Path:
    return artifact_dir("llm_calls", create=create)


def page_translation_debug_dir(*parts: str, create: bool = True) -> Path:
    return artifact_dir("page_translation", *parts, create=create)


def timestamped_artifact_name(
    *,
    prefix: str,
    suffix: str = ".json",
    timestamp: datetime | None = None,
) -> str:
    stamp = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    safe_prefix = _clean_token(prefix, fallback="artifact")
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{safe_prefix}_{stamp}{normalized_suffix}"


def write_json_artifact(
    *,
    directory: Path,
    filename: str,
    payload: Any,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _clean_token(filename, fallback="artifact.json")
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def write_text_artifact(
    *,
    directory: Path,
    filename: str,
    text: str,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _clean_token(filename, fallback="artifact.txt")
    path.write_text(text, encoding="utf-8")
    return path
