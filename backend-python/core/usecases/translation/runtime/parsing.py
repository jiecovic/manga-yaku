# backend-python/core/usecases/translation/runtime/parsing.py
"""Structured-output parsing helpers for single-box translation."""

from __future__ import annotations

import json
import re
from typing import Any

from .utils import normalize_translation_output


def json_translation_validator(text: str) -> tuple[bool, str | None]:
    try:
        parse_structured_translation(text)
    except Exception as exc:
        return False, str(exc).strip() or repr(exc)
    return True, None


def build_text_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "single_box_translation",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["ok", "no_text"],
                },
                "translation": {"type": "string"},
            },
            "required": ["status", "translation"],
        },
        "strict": True,
    }


def extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise ValueError("Empty response")
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("JSON response must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    snippet = text[start : end + 1]
    parsed = json.loads(snippet)
    if not isinstance(parsed, dict):
        raise ValueError("JSON response must be an object")
    return parsed


def parse_structured_translation(raw: str) -> dict[str, str]:
    payload = extract_json(raw)
    status = str(payload.get("status") or "").strip().lower()
    translation = normalize_translation_output(str(payload.get("translation") or ""))
    if status not in {"ok", "no_text"}:
        raise ValueError("status must be 'ok' or 'no_text'")
    if status == "ok" and not translation:
        raise ValueError("translation is empty for status=ok")
    if status == "no_text":
        translation = ""
    return {
        "status": status,
        "translation": translation,
    }
