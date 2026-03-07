# backend-python/tests/api/test_agent_route_logging.py
"""Tests for agent route logging helpers."""

from __future__ import annotations

from unittest.mock import patch

from api.routers.agent.helpers import (
    build_prompt_payload,
    log_agent_sdk_attempt,
    persist_action_event_messages,
    sanitize_agent_log_payload,
)


def test_sanitize_agent_log_payload_redacts_data_urls() -> None:
    payload = sanitize_agent_log_payload(
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
    with patch("api.routers.agent.helpers.create_llm_call_log") as create_log_mock:
        log_agent_sdk_attempt(
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


def test_build_prompt_payload_excludes_tool_timeline_messages() -> None:
    payload = build_prompt_payload(
        [
            {"role": "user", "content": "translate this line"},
            {"role": "tool", "content": "ocr_text_box -> completed"},
            {"role": "assistant", "content": "Here is the translation."},
        ]
    )

    assert payload == [
        {"role": "user", "content": "translate this line"},
        {"role": "assistant", "content": "Here is the translation."},
    ]


def test_persist_action_event_messages_persists_full_observable_sequence() -> None:
    persisted_rows: list[dict[str, object]] = []

    def fake_add_message(session_id, *, role, content, meta):
        row = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "meta": meta,
        }
        persisted_rows.append(row)
        return row

    with patch("api.routers.agent.helpers.add_agent_message", side_effect=fake_add_message):
        result = persist_action_event_messages(
            "sess-1",
            [
                {"type": "activity", "message": "Agents SDK runtime active (MCP tools)"},
                {
                    "type": "tool_called",
                    "message": 'ocr_text_box({"box_id": 3})',
                    "tool": "ocr_text_box",
                },
                {
                    "type": "tool_output",
                    "message": "ocr_text_box -> completed",
                    "tool": "ocr_text_box",
                },
                {"type": "page_switch", "message": "Switched to 006.jpg", "filename": "006.jpg"},
            ],
        )

    assert len(result) == 4
    assert [row["role"] for row in persisted_rows] == ["tool", "tool", "tool", "tool"]
    assert persisted_rows[0]["meta"]["eventType"] == "activity"
    assert persisted_rows[1]["meta"]["eventType"] == "tool_called"
    assert persisted_rows[2]["meta"]["tool"] == "ocr_text_box"
    assert persisted_rows[3]["meta"]["filename"] == "006.jpg"
