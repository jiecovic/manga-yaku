# backend-python/tests/api/test_agent_route_logging.py
"""Tests for agent route logging helpers."""

from __future__ import annotations

from unittest.mock import patch

from api.routers.agent.routes import (
    _log_agent_sdk_attempt,
    _sanitize_agent_log_payload,
)


def test_sanitize_agent_log_payload_redacts_data_urls() -> None:
    payload = _sanitize_agent_log_payload(
        {
            "content": [
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,abc123",
                }
            ]
        }
    )

    assert payload == {
        "content": [
            {
                "type": "input_image",
                "image_url": "<redacted:data-url:28>",
            }
        ]
    }


def test_log_agent_sdk_attempt_persists_request_id_and_actions() -> None:
    with patch("api.routers.agent.routes.create_llm_call_log") as create_log_mock:
        _log_agent_sdk_attempt(
            component="agent.chat.stream.sdk",
            status="error",
            session_id="sess-1",
            volume_id="vol-a",
            filename="001.jpg",
            model_id="gpt-5.2",
            messages=[{"role": "user", "content": "translate this page"}],
            action_events=[{"type": "tool_called", "message": "list_text_boxes()"}],
            error_detail="provider error",
            request_id="req_123",
            latency_ms=321,
            finish_reason="provider_error",
            phase="stream_primary",
        )

    kwargs = create_log_mock.call_args.kwargs
    assert kwargs["component"] == "agent.chat.stream.sdk"
    assert kwargs["status"] == "error"
    assert kwargs["params_snapshot"]["request_id"] == "req_123"
    assert kwargs["params_snapshot"]["phase"] == "stream_primary"
    assert kwargs["payload"]["action_events"] == [
        {"type": "tool_called", "message": "list_text_boxes()"}
    ]
