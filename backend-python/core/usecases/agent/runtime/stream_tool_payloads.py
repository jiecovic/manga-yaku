# backend-python/core/usecases/agent/runtime/stream_tool_payloads.py
"""Parsing and formatting helpers for streamed agent tool payloads."""

from __future__ import annotations

import json
from typing import Any

from infra.text_utils import truncate_text


def _try_parse_json_dict(raw: str | None) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def coerce_tool_output_dict(output: Any) -> dict[str, Any] | None:
    """Best-effort conversion of raw streamed tool output into a JSON dict."""
    if isinstance(output, dict):
        output_type = str(output.get("type") or "").strip().lower()
        if output_type in {"text", "input_text"} and "text" in output:
            parsed_text = _try_parse_json_dict(output.get("text"))
            if parsed_text is not None:
                return parsed_text
        return output
    if isinstance(output, str):
        return _try_parse_json_dict(output)
    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict):
                item_type = str(item.get("type") or "").strip().lower()
                if item_type in {"input_text", "text"}:
                    parsed = _try_parse_json_dict(item.get("text"))
                    if parsed is not None:
                        return parsed
    return None


def preview_tool_arguments(arguments: Any) -> str | None:
    """Render a compact preview string for streamed tool arguments."""
    if arguments is None:
        return None

    payload: Any = arguments
    if isinstance(arguments, str):
        raw = arguments.strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw

    if isinstance(payload, (dict, list)):
        try:
            return truncate_text(
                json.dumps(payload, ensure_ascii=False),
                limit=220,
                collapse_whitespace=True,
            )
        except Exception:
            return truncate_text(str(payload), limit=220, collapse_whitespace=True)
    text = str(payload or "").strip()
    if not text:
        return None
    return truncate_text(text, limit=220, collapse_whitespace=True)


def format_tool_called_message(tool_name: str, args_preview: str | None) -> str:
    if args_preview:
        return f"{tool_name}({args_preview})"
    return f"{tool_name}()"


def format_tool_output_message(tool_name: str, summary: str) -> str:
    summary_text = summary.strip() or "ok"
    return f"{tool_name} -> {summary_text}"


def extract_page_switch_filename(tool_name: str, output: Any) -> str | None:
    if tool_name not in {"set_active_page", "shift_active_page"}:
        return None
    output_dict = coerce_tool_output_dict(output)
    if not isinstance(output_dict, dict):
        return None
    if str(output_dict.get("status") or "").strip().lower() != "ok":
        return None
    filename = str(output_dict.get("filename") or "").strip()
    return filename or None


def format_exception_details(exc: Exception) -> str:
    parts = [f"{exc.__class__.__name__}: {str(exc).strip()}"]

    for name in ("status_code", "request_id", "type", "code", "param"):
        value = getattr(exc, name, None)
        if value not in (None, ""):
            parts.append(f"{name}={value}")

    request = getattr(exc, "request", None)
    method = getattr(request, "method", None)
    url = getattr(request, "url", None)
    if method and url:
        parts.append(f"request={method} {url}")

    body = getattr(exc, "body", None)
    if body not in (None, ""):
        try:
            if isinstance(body, (dict, list)):
                body_text = json.dumps(body, ensure_ascii=True)
            else:
                body_text = str(body)
            parts.append(f"body={truncate_text(body_text, limit=400, collapse_whitespace=True)}")
        except Exception:
            pass

    return " | ".join(parts)
