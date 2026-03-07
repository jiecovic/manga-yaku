# backend-python/tests/core/usecases/test_agent_chat_settings.py
"""Tests for chat-agent runtime settings resolution."""

from __future__ import annotations

from unittest.mock import patch

from core.usecases.agent.engine import (
    _resolve_agent_chat_max_output_tokens,
    _resolve_agent_chat_max_turns,
)


def test_resolve_agent_chat_max_turns_prefers_db_setting() -> None:
    with patch(
        "core.usecases.agent.chat_runtime_settings.get_setting_value",
        return_value=42,
    ):
        assert _resolve_agent_chat_max_turns() == 42


def test_resolve_agent_chat_max_turns_falls_back_to_env_default() -> None:
    with (
        patch(
            "core.usecases.agent.chat_runtime_settings.get_setting_value",
            return_value=None,
        ),
        patch("core.usecases.agent.chat_runtime_settings.AGENT_MAX_TURNS", 18),
    ):
        assert _resolve_agent_chat_max_turns() == 18


def test_resolve_agent_chat_max_turns_clamps_invalid_values() -> None:
    with patch(
        "core.usecases.agent.chat_runtime_settings.get_setting_value",
        return_value=999,
    ):
        assert _resolve_agent_chat_max_turns() == 200


def test_resolve_agent_chat_max_output_tokens_prefers_db_setting() -> None:
    with patch(
        "core.usecases.agent.chat_runtime_settings.get_setting_value",
        return_value=1536,
    ):
        assert _resolve_agent_chat_max_output_tokens() == 1536


def test_resolve_agent_chat_max_output_tokens_falls_back_to_env_default() -> None:
    with (
        patch(
            "core.usecases.agent.chat_runtime_settings.get_setting_value",
            return_value=None,
        ),
        patch("core.usecases.agent.chat_runtime_settings.AGENT_MAX_OUTPUT_TOKENS", 2048),
    ):
        assert _resolve_agent_chat_max_output_tokens() == 2048


def test_resolve_agent_chat_max_output_tokens_clamps_invalid_values() -> None:
    with patch(
        "core.usecases.agent.chat_runtime_settings.get_setting_value",
        return_value=99999,
    ):
        assert _resolve_agent_chat_max_output_tokens() == 4096
