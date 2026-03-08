# backend-python/tests/core/usecases/test_retry_policies.py
"""Unit tests for OCR/translation retry policy helper functions.

What is tested:
- Retry override escalation behavior across attempts.
- Output sanitization/normalization for empty or invalid model responses.

How it is tested:
- Pure helper functions are invoked with deterministic input values.
- No external providers or async infrastructure are involved.
"""

from __future__ import annotations

from core.usecases.ocr.tasks.runner import (
    _build_retry_override as build_ocr_retry_override,
)
from core.usecases.ocr.tasks.runner import _sanitize_ocr_text
from core.usecases.translation.task_runner import (
    _build_retry_override as build_translation_retry_override,
)
from core.usecases.translation.task_runner import _normalize_translation_result


def test_ocr_retry_override_for_gpt5() -> None:
    base_cfg = {"model": "gpt-5-mini", "max_output_tokens": 512}
    assert build_ocr_retry_override(base_cfg, attempt=1) == {}

    attempt2 = build_ocr_retry_override(base_cfg, attempt=2)
    assert attempt2["max_output_tokens"] == 1024
    assert attempt2["reasoning"] == {"effort": "medium"}

    attempt3 = build_ocr_retry_override(base_cfg, attempt=3)
    assert attempt3["max_output_tokens"] == 1536
    assert attempt3["reasoning"] == {"effort": "high"}


def test_sanitize_ocr_text_rules() -> None:
    assert _sanitize_ocr_text(" NO_TEXT ", llm=True) == ("", "no_text")
    assert _sanitize_ocr_text("", llm=True) == ("", "invalid")
    assert _sanitize_ocr_text("", llm=False) == ("", "no_text")
    assert _sanitize_ocr_text("a" * 100, llm=True) == ("", "invalid")
    assert _sanitize_ocr_text("actual text", llm=True) == ("actual text", "ok")


def test_translation_retry_override_for_gpt5() -> None:
    base_cfg = {"model": "gpt-5-nano", "max_completion_tokens": 400}
    assert build_translation_retry_override(base_cfg, attempt=1) == {}

    attempt2 = build_translation_retry_override(base_cfg, attempt=2)
    assert attempt2["max_completion_tokens"] == 800
    assert attempt2["reasoning"] == {"effort": "medium"}

    capped_cfg = {"model": "gpt-5-mini", "max_completion_tokens": 1500}
    attempt3 = build_translation_retry_override(capped_cfg, attempt=3)
    assert attempt3["max_completion_tokens"] == 2048
    assert attempt3["reasoning"] == {"effort": "high"}


def test_normalize_translation_result() -> None:
    assert _normalize_translation_result("not-a-dict") == ("invalid", "")
    assert _normalize_translation_result({"status": "ok", "translation": "line"}) == ("ok", "line")
    assert _normalize_translation_result({"status": "ok", "translation": "  "}) == ("invalid", "")
    assert _normalize_translation_result({"status": "no_text", "translation": "ignored"}) == (
        "no_text",
        "",
    )
    assert _normalize_translation_result({"status": "error", "translation": "line"}) == (
        "invalid",
        "",
    )
