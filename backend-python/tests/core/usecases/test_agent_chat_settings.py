# backend-python/tests/core/usecases/test_agent_chat_settings.py
"""Tests for chat-agent runtime settings resolution."""

from __future__ import annotations

from unittest.mock import patch

from core.usecases.agent.engine import _resolve_agent_chat_max_turns


def test_resolve_agent_chat_max_turns_prefers_db_setting() -> None:
    with patch("core.usecases.agent.engine.get_setting_value", return_value=42):
        assert _resolve_agent_chat_max_turns() == 42


def test_resolve_agent_chat_max_turns_falls_back_to_env_default() -> None:
    with (
        patch("core.usecases.agent.engine.get_setting_value", return_value=None),
        patch("core.usecases.agent.engine.AGENT_MAX_TURNS", 18),
    ):
        assert _resolve_agent_chat_max_turns() == 18


def test_resolve_agent_chat_max_turns_clamps_invalid_values() -> None:
    with patch("core.usecases.agent.engine.get_setting_value", return_value=999):
        assert _resolve_agent_chat_max_turns() == 200
