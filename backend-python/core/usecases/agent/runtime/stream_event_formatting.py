# backend-python/core/usecases/agent/runtime/stream_event_formatting.py
"""Formatting helpers for streamed agent activity and tool events."""

from __future__ import annotations

import json
from collections.abc import Callable
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


ToolOutputSummarizer = Callable[[dict[str, Any]], str | None]


def _status(output_dict: dict[str, Any]) -> str:
    return str(output_dict.get("status") or "").strip().lower()


def _filename(output_dict: dict[str, Any]) -> str:
    return str(output_dict.get("filename") or "").strip()


def _summary_count_details(
    *,
    prefix: str,
    characters: Any,
    open_threads: Any,
    glossary: Any,
) -> str:
    details: list[str] = []
    if isinstance(characters, list):
        details.append(f"{len(characters)} characters")
    if isinstance(open_threads, list):
        details.append(f"{len(open_threads)} open threads")
    if isinstance(glossary, list):
        details.append(f"{len(glossary)} glossary terms")
    if details:
        return prefix + ": " + ", ".join(details)
    return prefix


def _summarize_list_volume_pages(output_dict: dict[str, Any]) -> str | None:
    page_count = output_dict.get("page_count")
    if isinstance(page_count, int):
        return f"{page_count} pages"
    return None


def _summarize_set_active_page(output_dict: dict[str, Any]) -> str | None:
    filename = _filename(output_dict)
    if _status(output_dict) != "ok" or not filename:
        return None
    text_box_count = output_dict.get("text_box_count")
    if isinstance(text_box_count, int):
        return f"active page switched to {filename} ({text_box_count} text boxes)"
    return f"active page switched to {filename}"


def _summarize_shift_active_page(output_dict: dict[str, Any]) -> str | None:
    filename = _filename(output_dict)
    if _status(output_dict) != "ok" or not filename:
        return None
    moved_by = output_dict.get("moved_by")
    if isinstance(moved_by, int):
        if moved_by > 0:
            return f"active page moved forward to {filename}"
        if moved_by < 0:
            return f"active page moved backward to {filename}"
    return f"active page switched to {filename}"


def _summarize_get_volume_context(output_dict: dict[str, Any]) -> str | None:
    return _summary_count_details(
        prefix="context loaded",
        characters=output_dict.get("active_characters"),
        open_threads=output_dict.get("open_threads"),
        glossary=output_dict.get("glossary"),
    )


def _summarize_get_page_memory(output_dict: dict[str, Any]) -> str | None:
    return _summary_count_details(
        prefix="page memory loaded",
        characters=output_dict.get("characters"),
        open_threads=output_dict.get("open_threads"),
        glossary=output_dict.get("glossary"),
    )


def _summarize_update_volume_context(output_dict: dict[str, Any]) -> str | None:
    if _status(output_dict) != "ok":
        return None
    glossary = output_dict.get("glossary")
    if isinstance(glossary, list):
        return f"context updated ({len(glossary)} glossary terms)"
    return "context updated"


def _summarize_update_page_memory(output_dict: dict[str, Any]) -> str | None:
    if _status(output_dict) != "ok":
        return None
    filename = _filename(output_dict)
    if filename:
        return f"page memory updated for {filename}"
    return "page memory updated"


def _summarize_list_text_boxes(output_dict: dict[str, Any]) -> str | None:
    total = output_dict.get("total")
    if not isinstance(total, int):
        return None
    filename = _filename(output_dict)
    ocr_filled_count = output_dict.get("ocr_filled_count")
    translated_count = output_dict.get("translated_count")
    if filename and isinstance(ocr_filled_count, int) and isinstance(translated_count, int):
        return (
            f"{total} text boxes on {filename} "
            f"({ocr_filled_count} OCR, {translated_count} translated)"
        )
    if filename:
        return f"{total} text boxes on {filename}"
    return f"{total} text boxes"


def _summarize_search_volume_text_boxes(output_dict: dict[str, Any]) -> str | None:
    total = output_dict.get("total")
    if not isinstance(total, int):
        return None
    query = str(output_dict.get("query") or "").strip()
    if query:
        return f"{total} matches for '{truncate_text(query, limit=60, collapse_whitespace=True)}'"
    return f"{total} matches"


def _summarize_get_text_box_detail(output_dict: dict[str, Any]) -> str | None:
    box = output_dict.get("box")
    if not isinstance(box, dict):
        return None
    box_id = box.get("id")
    text_preview = truncate_text(
        str(box.get("text") or "").strip(),
        limit=80,
        collapse_whitespace=True,
    )
    if box_id is not None and text_preview:
        return f"box #{box_id}: {text_preview}"
    if box_id is not None:
        return f"box #{box_id}"
    return None


def _summarize_update_text_box_fields(output_dict: dict[str, Any]) -> str | None:
    if _status(output_dict) != "ok":
        return None
    box_id = output_dict.get("box_id")
    filename = _filename(output_dict)
    updated_fields = output_dict.get("updated_fields")
    updated_note = isinstance(updated_fields, dict) and bool(updated_fields.get("note"))
    if updated_note and box_id is not None and filename:
        return f"updated note for box #{box_id} on {filename}"
    if box_id is not None and filename:
        return f"updated box #{box_id} on {filename}"
    if box_id is not None:
        return f"updated box #{box_id}"
    return "box updated"


def _summarize_set_text_box_note(output_dict: dict[str, Any]) -> str | None:
    if _status(output_dict) != "ok":
        return None
    box_id = output_dict.get("box_id")
    filename = _filename(output_dict)
    if box_id is not None and filename:
        return f"updated note for box #{box_id} on {filename}"
    if box_id is not None:
        return f"updated note for box #{box_id}"
    return "box note updated"


def _summarize_list_ocr_profiles(output_dict: dict[str, Any]) -> str | None:
    total = output_dict.get("total")
    if isinstance(total, int):
        return f"{total} OCR profiles"
    return None


def _summarize_translate_active_page(output_dict: dict[str, Any]) -> str | None:
    status = _status(output_dict)
    filename = _filename(output_dict)
    updated = output_dict.get("updated")
    total = output_dict.get("total")
    translated_count = output_dict.get("translated_count")
    text_box_count = output_dict.get("text_box_count")
    started_now = bool(output_dict.get("started_now"))
    reused = bool(output_dict.get("resource_reused"))
    if status == "already_translated":
        if filename and isinstance(translated_count, int) and isinstance(text_box_count, int):
            return f"page {filename} was already translated ({translated_count}/{text_box_count} boxes)"
        if filename:
            return f"page {filename} was already translated"
        return "page was already translated"
    if status == "completed":
        if filename and isinstance(updated, int) and isinstance(total, int):
            return f"page workflow completed for {filename} ({updated}/{total} boxes updated)"
        if filename:
            return f"page workflow completed for {filename}"
        return "page workflow completed"
    if status == "queued":
        if filename and started_now:
            return f"started page workflow for {filename}"
        if filename and reused:
            return f"page workflow already running for {filename}"
        job_id = str(output_dict.get("job_id") or "").strip()
        if job_id:
            return f"queued page workflow {job_id}"
        return "queued page workflow"
    return None


def _summarize_ocr_text_box(output_dict: dict[str, Any]) -> str | None:
    status = _status(output_dict)
    box_id = output_dict.get("box_id")
    filename = _filename(output_dict)
    profile_id = str(output_dict.get("profile_id") or "").strip()
    idempotency_state = str(output_dict.get("idempotency_state") or "").strip().lower()
    if status == "skipped_existing":
        if box_id is not None and filename:
            return f"skipped OCR for box #{box_id} on {filename}; text already exists"
        if box_id is not None:
            return f"skipped OCR for box #{box_id}; text already exists"
        return "skipped OCR; text already exists"
    if status == "ok":
        if idempotency_state == "replay" and box_id is not None and filename:
            return f"reused OCR result for box #{box_id} on {filename}"
        if box_id is not None and filename and profile_id:
            return f"OCR box #{box_id} on {filename} via {profile_id}"
        if box_id is not None:
            return f"OCR box #{box_id}"
        return "OCR complete"
    if status == "no_text":
        if box_id is not None and filename:
            return f"box #{box_id} on {filename}: no text found"
        return "no text found"
    if status == "queued":
        workflow_run_id = str(output_dict.get("workflow_run_id") or "").strip()
        if idempotency_state == "in_progress":
            return "equivalent OCR workflow already in progress"
        if idempotency_state == "replay" and workflow_run_id:
            return f"reused OCR workflow {workflow_run_id}"
        if workflow_run_id:
            return f"queued OCR workflow {workflow_run_id}"
        return "queued OCR workflow"
    return None


def _summarize_list_box_detection_profiles(output_dict: dict[str, Any]) -> str | None:
    total = output_dict.get("total")
    if isinstance(total, int):
        return f"{total} detection profiles"
    return None


def _summarize_detect_text_boxes(output_dict: dict[str, Any]) -> str | None:
    status = _status(output_dict)
    filename = _filename(output_dict)
    new_box_count = output_dict.get("new_box_count")
    if not isinstance(new_box_count, int):
        new_box_count = output_dict.get("detected_count")
    text_box_count = output_dict.get("text_box_count")
    if not isinstance(text_box_count, int):
        text_box_count = output_dict.get("total_text_box_count")
    replace_existing = bool(output_dict.get("replace_existing"))
    idempotency_state = str(output_dict.get("idempotency_state") or "").strip().lower()
    if status == "ok":
        if idempotency_state == "replay" and filename:
            return f"reused detection result for {filename}"
        if (
            isinstance(new_box_count, int)
            and new_box_count == 0
            and filename
            and not replace_existing
        ):
            return f"no new text boxes detected on {filename}; preserved existing boxes"
        if isinstance(new_box_count, int) and isinstance(text_box_count, int) and filename:
            return (
                f"detected {new_box_count} new text boxes on {filename}; "
                f"total text boxes now {text_box_count}"
            )
        if isinstance(new_box_count, int):
            return f"detected {new_box_count} text boxes"
    if status == "queued":
        job_id = str(output_dict.get("job_id") or "").strip()
        if idempotency_state == "in_progress":
            return "equivalent detection job already in progress"
        if idempotency_state == "replay" and job_id:
            return f"reused detection job {job_id}"
        if job_id:
            return f"queued detection job {job_id}"
        return "queued detection job"
    return None


def _summarize_view_text_box(output_dict: dict[str, Any]) -> str | None:
    box_id = output_dict.get("box_id")
    filename = _filename(output_dict)
    if box_id is not None and filename:
        return f"loaded visual crop for box #{box_id} on {filename}"
    if box_id is not None:
        return f"loaded visual crop for box #{box_id}"
    return "loaded box visual crop"


_TOOL_OUTPUT_SUMMARIZERS: dict[str, ToolOutputSummarizer] = {
    "list_volume_pages": _summarize_list_volume_pages,
    "set_active_page": _summarize_set_active_page,
    "shift_active_page": _summarize_shift_active_page,
    "get_volume_context": _summarize_get_volume_context,
    "get_page_memory": _summarize_get_page_memory,
    "update_volume_context": _summarize_update_volume_context,
    "update_page_memory": _summarize_update_page_memory,
    "list_text_boxes": _summarize_list_text_boxes,
    "search_volume_text_boxes": _summarize_search_volume_text_boxes,
    "get_text_box_detail": _summarize_get_text_box_detail,
    "update_text_box_fields": _summarize_update_text_box_fields,
    "set_text_box_note": _summarize_set_text_box_note,
    "list_ocr_profiles": _summarize_list_ocr_profiles,
    "translate_active_page": _summarize_translate_active_page,
    "ocr_text_box": _summarize_ocr_text_box,
    "list_box_detection_profiles": _summarize_list_box_detection_profiles,
    "detect_text_boxes": _summarize_detect_text_boxes,
    "view_text_box": _summarize_view_text_box,
}


def _fallback_dict_summary(output_dict: dict[str, Any]) -> str | None:
    details: list[str] = []
    for key in ("filename", "volume_id", "total", "page_count"):
        value = output_dict.get(key)
        if value is None or isinstance(value, (dict, list)):
            continue
        details.append(f"{key}={value}")
    for key in ("boxes", "filenames"):
        value = output_dict.get(key)
        if isinstance(value, list):
            details.append(f"{key}={len(value)}")
    if details:
        return ", ".join(details)
    return None


def summarize_tool_output(tool_name: str, output: Any) -> str:
    output_dict = coerce_tool_output_dict(output)
    if isinstance(output_dict, dict):
        error = output_dict.get("error")
        if error:
            return f"error: {truncate_text(str(error), limit=160, collapse_whitespace=True)}"

        summarizer = _TOOL_OUTPUT_SUMMARIZERS.get(tool_name)
        if summarizer is not None:
            summary = summarizer(output_dict)
            if summary:
                return summary

        fallback_summary = _fallback_dict_summary(output_dict)
        if fallback_summary:
            return fallback_summary

    if isinstance(output, list):
        return f"{len(output)} items"
    if output is None:
        return "ok"
    return truncate_text(str(output), limit=180, collapse_whitespace=True)


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
