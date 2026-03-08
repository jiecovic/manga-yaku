# backend-python/core/usecases/agent/tools/context_serialization.py
"""Serialization helpers for agent memory/context tool payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def serialize_optional_timestamp(value: datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def serialize_character_entries(value: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        gender = str(item.get("gender") or "").strip()
        info = str(item.get("info") or "").strip()
        if not name and not gender and not info:
            continue
        out.append({"name": name, "gender": gender, "info": info})
    return out


def serialize_glossary_entries(value: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        translation = str(item.get("translation") or "").strip()
        note = str(item.get("note") or "").strip()
        if not term or not translation:
            continue
        out.append({"term": term, "translation": translation, "note": note})
    return out


def serialize_open_threads(value: list[str] | None) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out
