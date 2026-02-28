"""Shared row mapping and SQL helper utilities for db stores."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from .db import Box, BoxDetectionRun, TextBoxContent


def default_page() -> dict[str, Any]:
    return {
        "boxes": [],
        "pageContext": "",
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def coerce_uuid(raw: str | UUID | None) -> UUID | None:
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def normalize_box_type(raw: str | None) -> str:
    if not raw:
        return "text"
    key = str(raw).strip().lower()
    if key in {"textbox", "speech"}:
        return "text"
    if key in {"frame"}:
        return "panel"
    if key in {"text", "panel", "face", "body"}:
        return key
    return "text"


def normalize_box_source(raw: str | None) -> str:
    if not raw:
        return "manual"
    key = str(raw).strip().lower()
    if key in {"detect", "detected", "auto"}:
        return "detect"
    return "manual"


def box_row_to_dict(
    box: Box,
    text_content: TextBoxContent | None,
    run: BoxDetectionRun | None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": box.box_id,
        "orderIndex": int(box.order_index or 0),
        "x": float(box.x),
        "y": float(box.y),
        "width": float(box.width),
        "height": float(box.height),
        "type": normalize_box_type(box.type),
        "source": normalize_box_source(box.source),
        "runId": str(box.run_id) if box.run_id else None,
    }

    if run:
        data.update(
            {
                "modelId": run.model_id,
                "modelLabel": run.model_label,
                "modelVersion": run.model_version,
                "modelPath": run.model_path,
                "modelHash": run.model_hash,
                "modelTask": run.task,
            }
        )

    if text_content:
        data["text"] = text_content.ocr_text or ""
        data["translation"] = text_content.translation or ""
    elif data["type"] == "text":
        data["text"] = ""
        data["translation"] = ""

    return data


def normalize_json_blob(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, ensure_ascii=True, default=str))
    except (TypeError, ValueError):
        return None
