# backend-python/core/usecases/agent/chat_runtime_settings.py
"""Helpers for DB-backed chat-agent runtime settings."""

from __future__ import annotations

from config import AGENT_MAX_OUTPUT_TOKENS, AGENT_MAX_TURNS
from core.usecases.settings.service import get_setting_value

_AGENT_CHAT_MAX_TURNS_MIN = 1
_AGENT_CHAT_MAX_TURNS_MAX = 200
_AGENT_CHAT_MAX_OUTPUT_TOKENS_MIN = 128
_AGENT_CHAT_MAX_OUTPUT_TOKENS_MAX = 4096


def resolve_agent_chat_max_turns() -> int:
    default_value = max(
        _AGENT_CHAT_MAX_TURNS_MIN,
        min(_AGENT_CHAT_MAX_TURNS_MAX, int(AGENT_MAX_TURNS)),
    )
    try:
        raw_value = get_setting_value("agent.chat.max_turns")
    except Exception:
        raw_value = None
    if raw_value in (None, ""):
        return default_value
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default_value
    if parsed < _AGENT_CHAT_MAX_TURNS_MIN:
        return _AGENT_CHAT_MAX_TURNS_MIN
    if parsed > _AGENT_CHAT_MAX_TURNS_MAX:
        return _AGENT_CHAT_MAX_TURNS_MAX
    return parsed


def resolve_agent_chat_max_output_tokens() -> int:
    default_value = max(
        _AGENT_CHAT_MAX_OUTPUT_TOKENS_MIN,
        min(_AGENT_CHAT_MAX_OUTPUT_TOKENS_MAX, int(AGENT_MAX_OUTPUT_TOKENS)),
    )
    try:
        raw_value = get_setting_value("agent.chat.max_output_tokens")
    except Exception:
        raw_value = None
    if raw_value in (None, ""):
        return default_value
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default_value
    if parsed < _AGENT_CHAT_MAX_OUTPUT_TOKENS_MIN:
        return _AGENT_CHAT_MAX_OUTPUT_TOKENS_MIN
    if parsed > _AGENT_CHAT_MAX_OUTPUT_TOKENS_MAX:
        return _AGENT_CHAT_MAX_OUTPUT_TOKENS_MAX
    return parsed
