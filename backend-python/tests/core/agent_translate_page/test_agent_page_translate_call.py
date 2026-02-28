# backend-python/tests/core/agent_translate_page/test_agent_page_translate_call.py
"""Unit tests for page-translate structured call retry behavior.

What is tested:
- `run_structured_call` retries on incomplete:max_output_tokens responses.
- Retry growth of max output tokens is capped.

How it is tested:
- Mocked OpenAI response objects and mocked transport helpers.
- Pure in-memory parser, no network or filesystem access.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.usecases.agent.page_translate_call import run_structured_call


class _DummyResponse:
    def __init__(self, *, status: str, incomplete_reason: str | None = None) -> None:
        self.status = status
        self.incomplete_details = (
            {"reason": incomplete_reason} if incomplete_reason is not None else None
        )

    def model_dump(self) -> dict[str, object]:
        return {
            "status": self.status,
            "incomplete_details": self.incomplete_details,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        }


class RunStructuredCallTests(unittest.TestCase):
    def test_retry_max_output_tokens_is_capped(self) -> None:
        first = _DummyResponse(status="incomplete", incomplete_reason="max_output_tokens")
        second = _DummyResponse(status="completed")

        with (
            patch(
                "core.usecases.agent.page_translate_call.build_response_params",
                side_effect=lambda cfg, _payload: dict(cfg),
            ),
            patch(
                "core.usecases.agent.page_translate_call.openai_responses_create",
                side_effect=[first, second],
            ) as create_call,
            patch(
                "core.usecases.agent.page_translate_call.extract_response_text",
                side_effect=['{"ok": true}', '{"ok": true}'],
            ),
        ):
            result, diagnostics = run_structured_call(
                client=object(),
                model_cfg={"model": "gpt-5-mini", "max_output_tokens": 5000},
                input_payload=[{"role": "user", "content": [{"type": "input_text", "text": "x"}]}],
                text_format={"type": "json_schema", "name": "n", "schema": {"type": "object"}},
                parser=lambda data: data,
                component="agent.translate_page.translate",
                repair_component="agent.translate_page.translate.repair",
                log_context={"job_id": "test"},
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(diagnostics["attempt_count"], 2)
        self.assertEqual(diagnostics["params"]["max_output_tokens"], 4096)
        self.assertEqual(create_call.call_count, 2)
