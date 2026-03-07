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
from unittest.mock import patch

from infra.llm import call_logger


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponsesApi:
    def create(self, **_: object) -> _FakeResponse:
        return _FakeResponse('{"ok":true}')


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponsesApi()


def test_validate_response_uses_full_text_for_long_json() -> None:
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

    assert ok
    assert detail is None


def test_openai_responses_create_preserves_box_and_profile_context() -> None:
    client = _FakeClient()
    with patch.object(call_logger, "create_llm_call_log") as create_log:
        call_logger.openai_responses_create(
            client,
            {"model": "gpt-5-mini", "input": []},
            component="ocr.single_box",
            context={
                "volume_id": "Akuhamu",
                "filename": "001.jpg",
                "box_id": 12,
                "profile_id": "manga-ocr",
                "request_id": "req_123",
            },
        )

    kwargs = create_log.call_args.kwargs
    assert kwargs["params_snapshot"]["box_id"] == 12
    assert kwargs["params_snapshot"]["profile_id"] == "manga-ocr"
    assert kwargs["params_snapshot"]["request_id"] == "req_123"
    assert kwargs["payload"]["context"]["box_id"] == 12
    assert kwargs["payload"]["context"]["profile_id"] == "manga-ocr"
    assert kwargs["payload"]["context"]["request_id"] == "req_123"
