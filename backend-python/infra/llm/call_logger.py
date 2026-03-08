# backend-python/infra/llm/call_logger.py
"""Persistence-backed logging for LLM request/response payloads."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from typing import Any

from infra.db.llm_call_log_store import create_llm_call_log
from infra.logging.correlation import append_correlation, normalize_correlation
from infra.text_utils import truncate_text

from .openai_client import extract_response_text

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}
_LOG_MODE = os.getenv("MANGAYAKU_LLM_LOG_MODE", "full").strip().lower()
if _LOG_MODE not in {"off", "errors_only", "full"}:
    _LOG_MODE = "full"
_LOG_INCLUDE_IMAGES = os.getenv("MANGAYAKU_LLM_LOG_INCLUDE_IMAGES", "0").strip().lower() in _TRUE


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            lowered = str(key).lower()
            if lowered in {"api_key", "authorization", "openai_api_key"}:
                out[key] = "***redacted***"
                continue
            if not _LOG_INCLUDE_IMAGES and lowered == "image_url":
                if isinstance(val, str) and val.startswith("data:image/"):
                    out[key] = f"<redacted:data-url:{len(val)}>"
                    continue
                if isinstance(val, dict):
                    maybe_url = val.get("url")
                    if isinstance(maybe_url, str) and maybe_url.startswith("data:image/"):
                        out[key] = {"url": f"<redacted:data-url:{len(maybe_url)}>"}
                        continue
            out[key] = _redact_value(val)
        return out
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        if not _LOG_INCLUDE_IMAGES and value.startswith("data:image/"):
            return f"<redacted:data-url:{len(value)}>"
        return truncate_text(value, limit=12000)
    return value


def _serialize_response(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    try:
        model_dump = value.model_dump()  # type: ignore[attr-defined]
        if isinstance(model_dump, dict):
            return model_dump
        return {"value": model_dump}
    except Exception:
        return {"repr": repr(value)}


def _safe_get(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _extract_usage(api: str, response: Any) -> tuple[int | None, int | None, int | None]:
    usage = _safe_get(response, "usage")
    if not usage:
        return None, None, None

    if api == "chat_completions":
        input_tokens = _safe_get(usage, "prompt_tokens")
        output_tokens = _safe_get(usage, "completion_tokens")
        total_tokens = _safe_get(usage, "total_tokens")
    else:
        input_tokens = _safe_get(usage, "input_tokens")
        output_tokens = _safe_get(usage, "output_tokens")
        total_tokens = _safe_get(usage, "total_tokens")

    def _to_int(raw: Any) -> int | None:
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            return None
        return max(0, parsed)

    return _to_int(input_tokens), _to_int(output_tokens), _to_int(total_tokens)


def _extract_finish_reason(api: str, response: Any) -> str | None:
    if api == "chat_completions":
        choices = _safe_get(response, "choices")
        if not isinstance(choices, list) or not choices:
            return None
        finish_reason = _safe_get(choices[0], "finish_reason")
        return str(finish_reason) if finish_reason else None

    status = _safe_get(response, "status")
    if status == "incomplete":
        details = _safe_get(response, "incomplete_details") or {}
        reason = _safe_get(details, "reason")
        if reason:
            return f"incomplete:{reason}"
    if status:
        return str(status)
    return None


def _extract_response_text_excerpt(api: str, response: Any) -> str:
    try:
        if api == "chat_completions":
            choices = _safe_get(response, "choices")
            if isinstance(choices, list) and choices:
                message = _safe_get(choices[0], "message")
                content = _safe_get(message, "content")
                if isinstance(content, str):
                    return truncate_text(content, limit=8000)
                if content is not None:
                    try:
                        return truncate_text(
                            json.dumps(content, ensure_ascii=True, default=str),
                            limit=8000,
                        )
                    except Exception:
                        return truncate_text(str(content), limit=8000)
            return ""
        return truncate_text(extract_response_text(response), limit=8000)
    except Exception:
        return ""


def _extract_response_text_for_validation(api: str, response: Any) -> str:
    try:
        if api == "chat_completions":
            choices = _safe_get(response, "choices")
            if isinstance(choices, list) and choices:
                message = _safe_get(choices[0], "message")
                content = _safe_get(message, "content")
                if isinstance(content, str):
                    return content
                if content is not None:
                    try:
                        return json.dumps(content, ensure_ascii=True, default=str)
                    except Exception:
                        return str(content)
            return ""
        return extract_response_text(response)
    except Exception:
        return ""


def _extract_request_excerpt(params: dict[str, Any]) -> str:
    input_payload = params.get("input")
    if isinstance(input_payload, list):
        lines: list[str] = []
        for message in input_payload[:4]:
            content = None
            if isinstance(message, dict):
                content = message.get("content")
            if isinstance(content, list):
                for chunk in content[:4]:
                    text = chunk.get("text") if isinstance(chunk, dict) else None
                    if isinstance(text, str) and text.strip():
                        lines.append(text.strip())
            elif isinstance(content, str) and content.strip():
                lines.append(content.strip())
        return truncate_text("\n\n".join(lines), limit=8000)

    messages = params.get("messages")
    if isinstance(messages, list):
        lines = []
        for message in messages[:6]:
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and content.strip():
                lines.append(content.strip())
            elif isinstance(content, list):
                for item in content[:4]:
                    if isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            lines.append(text.strip())
        return truncate_text("\n\n".join(lines), limit=8000)

    return ""


def _build_params_snapshot(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "model": params.get("model"),
        "max_output_tokens": params.get("max_output_tokens"),
        "temperature": params.get("temperature"),
        "reasoning": params.get("reasoning"),
    }
    text_cfg = params.get("text")
    if text_cfg is not None:
        snapshot["text"] = text_cfg

    if "input" in params:
        input_payload = params["input"]
        if isinstance(input_payload, list):
            snapshot["input_messages"] = len(input_payload)
    if "messages" in params:
        messages = params["messages"]
        if isinstance(messages, list):
            snapshot["chat_messages"] = len(messages)

    for key in (
        "job_id",
        "workflow_run_id",
        "task_run_id",
        "session_id",
        "volume_id",
        "filename",
        "request_id",
        "box_id",
        "profile_id",
    ):
        if key in context:
            snapshot[key] = context[key]
    return _redact_value(snapshot)


def _should_log(status: str) -> bool:
    if _LOG_MODE == "off":
        return False
    if _LOG_MODE == "errors_only" and status == "success":
        return False
    return True


def _safe_write_log(
    *,
    api: str,
    component: str,
    params: dict[str, Any],
    status: str,
    context: dict[str, Any],
    latency_ms: int,
    response: Any = None,
    error_detail: str | None = None,
    finish_reason_override: str | None = None,
) -> None:
    if not _should_log(status):
        return
    normalized_context = normalize_correlation(context)
    for passthrough_key in ("box_id", "profile_id"):
        if passthrough_key in context and passthrough_key not in normalized_context:
            value = context.get(passthrough_key)
            if value not in (None, ""):
                normalized_context[passthrough_key] = value
    try:
        redacted_params = _redact_value(params)
        serialized_response = _redact_value(_serialize_response(response))
        response_excerpt = (
            _extract_response_text_excerpt(api, response) if response is not None else ""
        )
        input_tokens, output_tokens, total_tokens = _extract_usage(api, response)
        finish_reason = finish_reason_override or _extract_finish_reason(api, response)

        payload = {
            "provider": "openai",
            "api": api,
            "component": component,
            "status": status,
            "context": normalized_context,
            "request": redacted_params,
            "response": serialized_response,
            "response_text": response_excerpt,
            "error": error_detail,
            "latency_ms": latency_ms,
        }
        create_llm_call_log(
            provider="openai",
            api=api,
            component=component,
            status=status,
            model_id=str(params.get("model") or "") or None,
            job_id=str(normalized_context.get("job_id") or "") or None,
            workflow_run_id=str(normalized_context.get("workflow_run_id") or "") or None,
            task_run_id=str(normalized_context.get("task_run_id") or "") or None,
            attempt=(
                int(normalized_context.get("attempt"))
                if normalized_context.get("attempt") not in (None, "")
                else None
            ),
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            error_detail=error_detail,
            params_snapshot=_build_params_snapshot(redacted_params, normalized_context),
            request_excerpt=_extract_request_excerpt(redacted_params),
            response_excerpt=response_excerpt,
            payload=payload,
        )
    except Exception as exc:
        logger.warning(
            append_correlation(
                f"Failed to persist LLM call log: {exc}",
                normalized_context,
                api=api,
            )
        )


def _validate_response(
    *,
    api: str,
    response: Any,
    validator: Callable[[str], tuple[bool, str | None]] | None,
) -> tuple[bool, str | None]:
    if validator is None:
        return True, None
    # Validate against the complete model text, not the truncated log excerpt.
    text = _extract_response_text_for_validation(api, response)
    try:
        ok, detail = validator(text)
    except Exception as exc:
        return False, str(exc).strip() or repr(exc)
    if ok:
        return True, None
    return False, (str(detail).strip() if detail else "semantic validation failed")


def openai_responses_create(
    client: Any,
    params: dict[str, Any],
    *,
    component: str,
    context: dict[str, Any] | None = None,
    result_validator: Callable[[str], tuple[bool, str | None]] | None = None,
) -> Any:
    ctx = dict(context or {})
    started = time.monotonic()
    try:
        response = client.responses.create(**params)
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        _safe_write_log(
            api="responses",
            component=component,
            params=params,
            status="error",
            context=ctx,
            latency_ms=latency_ms,
            error_detail=str(exc).strip() or repr(exc),
        )
        raise

    latency_ms = int((time.monotonic() - started) * 1000)
    valid, semantic_error = _validate_response(
        api="responses",
        response=response,
        validator=result_validator,
    )
    _safe_write_log(
        api="responses",
        component=component,
        params=params,
        status="success" if valid else "error",
        context=ctx,
        latency_ms=latency_ms,
        response=response,
        error_detail=semantic_error,
    )
    return response


def openai_chat_completions_create(
    client: Any,
    params: dict[str, Any],
    *,
    component: str,
    context: dict[str, Any] | None = None,
    result_validator: Callable[[str], tuple[bool, str | None]] | None = None,
) -> Any:
    ctx = dict(context or {})
    started = time.monotonic()
    try:
        response = client.chat.completions.create(**params)
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        _safe_write_log(
            api="chat_completions",
            component=component,
            params=params,
            status="error",
            context=ctx,
            latency_ms=latency_ms,
            error_detail=str(exc).strip() or repr(exc),
        )
        raise

    latency_ms = int((time.monotonic() - started) * 1000)
    valid, semantic_error = _validate_response(
        api="chat_completions",
        response=response,
        validator=result_validator,
    )
    _safe_write_log(
        api="chat_completions",
        component=component,
        params=params,
        status="success" if valid else "error",
        context=ctx,
        latency_ms=latency_ms,
        response=response,
        error_detail=semantic_error,
    )
    return response


def openai_responses_stream_events(
    client: Any,
    params: dict[str, Any],
    *,
    component: str,
    context: dict[str, Any] | None = None,
) -> Iterator[Any]:
    ctx = dict(context or {})
    started = time.monotonic()
    final_response: Any = None
    completed = False
    try:
        with client.responses.stream(**params) as stream:
            yield from stream
            completed = True
            try:
                final_response = stream.get_final_response()
            except Exception:
                final_response = None
    except GeneratorExit:
        latency_ms = int((time.monotonic() - started) * 1000)
        _safe_write_log(
            api="responses_stream",
            component=component,
            params=params,
            status="success",
            context=ctx,
            latency_ms=latency_ms,
            finish_reason_override="stream_closed",
        )
        raise
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        _safe_write_log(
            api="responses_stream",
            component=component,
            params=params,
            status="error",
            context=ctx,
            latency_ms=latency_ms,
            error_detail=str(exc).strip() or repr(exc),
        )
        raise

    latency_ms = int((time.monotonic() - started) * 1000)
    _safe_write_log(
        api="responses_stream",
        component=component,
        params=params,
        status="success",
        context=ctx,
        latency_ms=latency_ms,
        response=final_response,
        finish_reason_override=None if completed else "stream_closed",
    )
