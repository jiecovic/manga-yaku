# backend-python/tests/core/usecases/test_agent_engine_settings.py
"""Tests for agent SDK model settings."""

from __future__ import annotations

from unittest.mock import patch

from core.usecases.agent import engine


def test_build_sdk_agent_disables_parallel_tool_calls() -> None:
    captured_settings: dict[str, object] = {}

    class DummyModelSettings:
        def __init__(self, **kwargs: object) -> None:
            captured_settings.update(kwargs)

    with (
        patch.object(engine, "Agent", side_effect=lambda **kwargs: kwargs),
        patch.object(engine, "ModelSettings", DummyModelSettings),
    ):
        agent = engine._build_sdk_agent("gpt-5.2", mcp_servers=[])

    assert agent["model"] == "gpt-5.2"
    assert captured_settings["parallel_tool_calls"] is False


def test_run_agent_chat_repair_uses_text_only_observations() -> None:
    captured: dict[str, object] = {}

    class DummyResponse:
        pass

    def fake_responses_create(client, params, *, component, context, result_validator=None):
        del client, context, result_validator
        captured["params"] = params
        captured["component"] = component
        return DummyResponse()

    with (
        patch.object(engine, "create_openai_client", return_value=object()),
        patch.object(engine, "openai_responses_create", side_effect=fake_responses_create),
        patch.object(engine, "extract_response_text", return_value="repaired answer"),
        patch.object(engine, "_resolve_agent_chat_max_output_tokens", return_value=1536),
    ):
        result = engine.run_agent_chat_repair(
            [
                {"role": "user", "content": "what sounds better here?"},
                {"role": "assistant", "content": "option a or b"},
                {"role": "user", "content": "in the context of this page"},
            ],
            action_events=[
                {
                    "type": "tool_output",
                    "message": "get_text_box_detail -> box #2: kore kao ...! aitsu ni sokkuri da ...",
                },
                {
                    "type": "tool_output",
                    "message": "get_text_box_detail -> box #3: osananajimi no aitsu ....",
                },
            ],
            model_id="gpt-5.2",
            volume_id="Arisa",
            current_filename="005.jpg",
            session_id="sess-1",
        )

    assert result == "repaired answer"
    assert captured["component"] == "agent.chat.repair"
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["max_output_tokens"] == 1536
    input_payload = params["input"]
    assert isinstance(input_payload, list)
    assert len(input_payload) == 2
    prompt_text = input_payload[1]["content"][0]["text"]
    assert "Tool observations:" in prompt_text
    assert "get_text_box_detail -> box #3" in prompt_text


def test_run_agent_chat_always_uses_sdk_runtime() -> None:
    with patch.object(engine, "_run_agent_chat_sdk", return_value="sdk answer") as sdk_mock:
        result = engine.run_agent_chat(
            [{"role": "user", "content": "hello"}],
            model_id="gpt-5.2",
            volume_id="vol-a",
            current_filename="001.jpg",
            session_id="sess-1",
        )

    assert result == "sdk answer"
    sdk_mock.assert_called_once_with(
        [{"role": "user", "content": "hello"}],
        model_id="gpt-5.2",
        volume_id="vol-a",
        current_filename="001.jpg",
        session_id="sess-1",
    )


def test_run_agent_chat_stream_always_uses_sdk_runtime() -> None:
    with patch.object(
        engine,
        "_run_agent_chat_stream_sdk",
        return_value=iter(
            [
                {"type": "activity", "message": "sdk"},
                {"type": "delta", "delta": "hello"},
            ]
        ),
    ) as sdk_mock:
        result = list(
            engine.run_agent_chat_stream(
                [{"role": "user", "content": "hello"}],
                model_id="gpt-5.2",
                volume_id="vol-a",
                current_filename="001.jpg",
                session_id="sess-1",
            )
        )

    assert result == [
        {"type": "activity", "message": "sdk"},
        {"type": "delta", "delta": "hello"},
    ]
    sdk_mock.assert_called_once_with(
        [{"role": "user", "content": "hello"}],
        model_id="gpt-5.2",
        volume_id="vol-a",
        current_filename="001.jpg",
        session_id="sess-1",
        stop_event=None,
    )
