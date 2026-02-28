# backend-python/infra/db/agent_translate_settings_store.py
"""Persistence helpers for agent translate page settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import AgentTranslateSetting, get_session


def get_agent_translate_settings() -> dict[str, Any]:
    with get_session() as session:
        row = session.get(AgentTranslateSetting, 1)
        if row is None:
            return {}
        return {
            "model_id": row.model_id,
            "max_output_tokens": row.max_output_tokens,
            "reasoning_effort": row.reasoning_effort,
            "temperature": row.temperature,
            "updated_at": row.updated_at,
        }


def upsert_agent_translate_settings(values: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    payload = dict(values)
    payload["updated_at"] = now

    with get_session() as session:
        row = session.get(AgentTranslateSetting, 1)
        if row is None:
            row = AgentTranslateSetting(id=1, model_id=str(values.get("model_id") or ""))
            session.add(row)
        for key, value in payload.items():
            if hasattr(row, key):
                setattr(row, key, value)
