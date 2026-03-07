# backend-python/core/usecases/agent/stream_event_formatting.py
"""Formatting helpers for streamed agent activity and tool events."""

from __future__ import annotations

import json
from typing import Any


def _truncate(value: str, *, max_chars: int = 120) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


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
            return _truncate(json.dumps(payload, ensure_ascii=False), max_chars=220)
        except Exception:
            return _truncate(str(payload), max_chars=220)
    text = str(payload or "").strip()
    if not text:
        return None
    return _truncate(text, max_chars=220)


def summarize_tool_output(tool_name: str, output: Any) -> str:
    output_dict = coerce_tool_output_dict(output)
    if isinstance(output_dict, dict):
        error = output_dict.get("error")
        if error:
            return f"error: {_truncate(str(error), max_chars=160)}"

        if tool_name == "list_volume_pages":
            page_count = output_dict.get("page_count")
            if isinstance(page_count, int):
                return f"{page_count} pages"
        elif tool_name == "set_active_page":
            status = str(output_dict.get("status") or "").strip().lower()
            filename = str(output_dict.get("filename") or "").strip()
            text_box_count = output_dict.get("text_box_count")
            if status == "ok" and filename:
                if isinstance(text_box_count, int):
                    return f"active page switched to {filename} ({text_box_count} text boxes)"
                return f"active page switched to {filename}"
        elif tool_name == "shift_active_page":
            status = str(output_dict.get("status") or "").strip().lower()
            filename = str(output_dict.get("filename") or "").strip()
            moved_by = output_dict.get("moved_by")
            if status == "ok" and filename:
                if isinstance(moved_by, int):
                    if moved_by > 0:
                        return f"active page moved forward to {filename}"
                    if moved_by < 0:
                        return f"active page moved backward to {filename}"
                return f"active page switched to {filename}"
        elif tool_name == "get_volume_context":
            glossary = output_dict.get("glossary")
            open_threads = output_dict.get("open_threads")
            chars = output_dict.get("active_characters")
            details: list[str] = []
            if isinstance(chars, list):
                details.append(f"{len(chars)} characters")
            if isinstance(open_threads, list):
                details.append(f"{len(open_threads)} open threads")
            if isinstance(glossary, list):
                details.append(f"{len(glossary)} glossary terms")
            if details:
                return "context loaded: " + ", ".join(details)
            return "context loaded"
        elif tool_name == "get_page_memory":
            chars = output_dict.get("characters")
            open_threads = output_dict.get("open_threads")
            glossary = output_dict.get("glossary")
            details: list[str] = []
            if isinstance(chars, list):
                details.append(f"{len(chars)} characters")
            if isinstance(open_threads, list):
                details.append(f"{len(open_threads)} open threads")
            if isinstance(glossary, list):
                details.append(f"{len(glossary)} glossary terms")
            if details:
                return "page memory loaded: " + ", ".join(details)
            return "page memory loaded"
        elif tool_name == "update_volume_context":
            status = str(output_dict.get("status") or "").strip().lower()
            if status == "ok":
                glossary = output_dict.get("glossary")
                if isinstance(glossary, list):
                    return f"context updated ({len(glossary)} glossary terms)"
                return "context updated"
        elif tool_name == "update_page_memory":
            status = str(output_dict.get("status") or "").strip().lower()
            filename = str(output_dict.get("filename") or "").strip()
            if status == "ok" and filename:
                return f"page memory updated for {filename}"
            if status == "ok":
                return "page memory updated"
        elif tool_name == "list_text_boxes":
            total = output_dict.get("total")
            filename = str(output_dict.get("filename") or "").strip()
            ocr_filled_count = output_dict.get("ocr_filled_count")
            translated_count = output_dict.get("translated_count")
            if isinstance(total, int):
                if (
                    filename
                    and isinstance(ocr_filled_count, int)
                    and isinstance(translated_count, int)
                ):
                    return (
                        f"{total} text boxes on {filename} "
                        f"({ocr_filled_count} OCR, {translated_count} translated)"
                    )
                if filename:
                    return f"{total} text boxes on {filename}"
                return f"{total} text boxes"
        elif tool_name == "search_volume_text_boxes":
            total = output_dict.get("total")
            query = str(output_dict.get("query") or "").strip()
            if isinstance(total, int):
                if query:
                    return f"{total} matches for '{_truncate(query, max_chars=60)}'"
                return f"{total} matches"
        elif tool_name == "get_text_box_detail":
            box = output_dict.get("box")
            if isinstance(box, dict):
                box_id = box.get("id")
                text_preview = _truncate(str(box.get("text") or "").strip(), max_chars=80)
                if box_id is not None and text_preview:
                    return f"box #{box_id}: {text_preview}"
                if box_id is not None:
                    return f"box #{box_id}"
        elif tool_name == "update_text_box_fields":
            status = str(output_dict.get("status") or "").strip().lower()
            box_id = output_dict.get("box_id")
            filename = str(output_dict.get("filename") or "").strip()
            if status == "ok":
                updated_fields = output_dict.get("updated_fields")
                updated_note = isinstance(updated_fields, dict) and bool(updated_fields.get("note"))
                if updated_note and box_id is not None and filename:
                    return f"updated note for box #{box_id} on {filename}"
                if box_id is not None and filename:
                    return f"updated box #{box_id} on {filename}"
                if box_id is not None:
                    return f"updated box #{box_id}"
                return "box updated"
        elif tool_name == "set_text_box_note":
            status = str(output_dict.get("status") or "").strip().lower()
            box_id = output_dict.get("box_id")
            filename = str(output_dict.get("filename") or "").strip()
            if status == "ok":
                if box_id is not None and filename:
                    return f"updated note for box #{box_id} on {filename}"
                if box_id is not None:
                    return f"updated note for box #{box_id}"
                return "box note updated"
        elif tool_name == "list_ocr_profiles":
            total = output_dict.get("total")
            if isinstance(total, int):
                return f"{total} OCR profiles"
        elif tool_name == "translate_active_page":
            status = str(output_dict.get("status") or "").strip().lower()
            filename = str(output_dict.get("filename") or "").strip()
            updated = output_dict.get("updated")
            total = output_dict.get("total")
            translated_count = output_dict.get("translated_count")
            text_box_count = output_dict.get("text_box_count")
            started_now = bool(output_dict.get("started_now"))
            reused = bool(output_dict.get("resource_reused"))
            if status == "already_translated":
                if (
                    filename
                    and isinstance(translated_count, int)
                    and isinstance(text_box_count, int)
                ):
                    return (
                        f"page {filename} was already translated "
                        f"({translated_count}/{text_box_count} boxes)"
                    )
                if filename:
                    return f"page {filename} was already translated"
                return "page was already translated"
            if status == "completed":
                if filename and isinstance(updated, int) and isinstance(total, int):
                    return (
                        f"page workflow completed for {filename} ({updated}/{total} boxes updated)"
                    )
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
        elif tool_name == "ocr_text_box":
            status = str(output_dict.get("status") or "").strip().lower()
            box_id = output_dict.get("box_id")
            filename = str(output_dict.get("filename") or "").strip()
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
        elif tool_name == "list_box_detection_profiles":
            total = output_dict.get("total")
            if isinstance(total, int):
                return f"{total} detection profiles"
        elif tool_name == "detect_text_boxes":
            status = str(output_dict.get("status") or "").strip().lower()
            filename = str(output_dict.get("filename") or "").strip()
            detected_count = output_dict.get("detected_count")
            text_box_count = output_dict.get("text_box_count")
            idempotency_state = str(output_dict.get("idempotency_state") or "").strip().lower()
            if status == "ok":
                if idempotency_state == "replay" and filename:
                    return f"reused detection result for {filename}"
                if isinstance(detected_count, int) and isinstance(text_box_count, int) and filename:
                    return (
                        f"detected {detected_count} new text boxes on {filename}; "
                        f"total text boxes now {text_box_count}"
                    )
                if isinstance(detected_count, int):
                    return f"detected {detected_count} text boxes"
            if status == "queued":
                job_id = str(output_dict.get("job_id") or "").strip()
                if idempotency_state == "in_progress":
                    return "equivalent detection job already in progress"
                if idempotency_state == "replay" and job_id:
                    return f"reused detection job {job_id}"
                if job_id:
                    return f"queued detection job {job_id}"
                return "queued detection job"
        elif tool_name == "view_text_box":
            box_id = output_dict.get("box_id")
            filename = str(output_dict.get("filename") or "").strip()
            if box_id is not None and filename:
                return f"loaded visual crop for box #{box_id} on {filename}"
            if box_id is not None:
                return f"loaded visual crop for box #{box_id}"
            return "loaded box visual crop"

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

    if isinstance(output, list):
        return f"{len(output)} items"
    if output is None:
        return "ok"
    return _truncate(str(output), max_chars=180)


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
            parts.append(f"body={_truncate(body_text, max_chars=400)}")
        except Exception:
            pass

    return " | ".join(parts)
