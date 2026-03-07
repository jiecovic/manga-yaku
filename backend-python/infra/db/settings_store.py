# backend-python/infra/db/settings_store.py
"""Persistence helpers for global backend settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from .db import AppSetting, get_session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_settings(scope: str = "global") -> dict[str, Any]:
    with get_session() as session:
        rows = session.execute(select(AppSetting).where(AppSetting.scope == scope)).scalars().all()
        return {row.key: row.value for row in rows}


def get_setting(scope: str, key: str) -> Any | None:
    with get_session() as session:
        row = session.execute(
            select(AppSetting).where(
                AppSetting.scope == scope,
                AppSetting.key == key,
            )
        ).scalar_one_or_none()
        return row.value if row else None


def upsert_settings(scope: str, values: dict[str, Any]) -> None:
    if not values:
        return
    with get_session() as session:
        for key, value in values.items():
            row = session.execute(
                select(AppSetting).where(
                    AppSetting.scope == scope,
                    AppSetting.key == key,
                )
            ).scalar_one_or_none()
            if row is None:
                row = AppSetting(
                    scope=scope,
                    key=key,
                    value=value,
                    updated_at=_utc_now(),
                )
                session.add(row)
            else:
                row.value = value
                row.updated_at = _utc_now()
