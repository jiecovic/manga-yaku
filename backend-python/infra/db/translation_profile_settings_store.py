from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import TranslationProfileSetting, get_session


def list_translation_profile_settings() -> dict[str, dict[str, Any]]:
    with get_session() as session:
        rows = session.query(TranslationProfileSetting).all()
        return {
            row.profile_id: {
                "single_box_enabled": bool(row.single_box_enabled),
                "model_id": row.model_id,
                "max_output_tokens": row.max_output_tokens,
                "reasoning_effort": row.reasoning_effort,
                "temperature": row.temperature,
                "updated_at": row.updated_at,
            }
            for row in rows
        }


def upsert_translation_profile_setting(profile_id: str, values: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    payload = dict(values)
    payload["updated_at"] = now

    with get_session() as session:
        row = session.get(TranslationProfileSetting, profile_id)
        if row is None:
            row = TranslationProfileSetting(profile_id=profile_id)
            session.add(row)
        for key, value in payload.items():
            if hasattr(row, key):
                setattr(row, key, value)
