# backend-python/core/usecases/page_translation/schema/json_tools.py
"""JSON extraction and response validation helpers for page translation."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from json_repair import repair_json

JsonParser = Callable[[dict[str, Any]], dict[str, Any]]


def extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise ValueError("Empty response")
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("JSON response must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    snippet = raw[start : end + 1]
    try:
        parsed = json.loads(snippet)
        if not isinstance(parsed, dict):
            raise ValueError("JSON response must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    repaired = repair_json(snippet, logging=False, return_objects=False)
    parsed = json.loads(repaired)
    if not isinstance(parsed, dict):
        raise ValueError("JSON response must be an object")
    return parsed


def json_result_validator(parser: JsonParser) -> Callable[[str], tuple[bool, str | None]]:
    def _validate(text: str) -> tuple[bool, str | None]:
        try:
            parser(extract_json(text))
            return True, None
        except Exception as exc:
            return False, str(exc).strip() or repr(exc)

    return _validate


def should_retry(response: Any) -> bool:
    status = getattr(response, "status", None)
    if status is None and isinstance(response, dict):
        status = response.get("status")
    if status != "incomplete":
        return False

    details = getattr(response, "incomplete_details", None)
    if details is None and isinstance(response, dict):
        details = response.get("incomplete_details") or {}
    if isinstance(details, dict):
        reason = details.get("reason")
    else:
        reason = getattr(details, "reason", None)
    return reason == "max_output_tokens"
