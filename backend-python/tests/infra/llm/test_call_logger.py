# backend-python/tests/infra/llm/test_call_logger.py
"""Unit tests for LLM call logger validation text handling.

What is tested:
- Semantic validators receive the full response text for validation, not a
  truncated log excerpt.

How it is tested:
- Uses a fake Responses API object with a very long JSON payload.
- Runs the internal validation helper and asserts it passes JSON parsing.
"""

from __future__ import annotations

import json
import unittest

from infra.llm import call_logger


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class CallLoggerValidationTests(unittest.TestCase):
    def test_validate_response_uses_full_text_for_long_json(self) -> None:
        payload = {"value": "x" * 9000}
        full_text = json.dumps(payload, ensure_ascii=False)
        response = _FakeResponse(full_text)

        def _validator(text: str) -> tuple[bool, str | None]:
            parsed = json.loads(text)
            return (parsed.get("value") == payload["value"], None)

        ok, detail = call_logger._validate_response(
            api="responses",
            response=response,
            validator=_validator,
        )

        self.assertTrue(ok)
        self.assertIsNone(detail)
