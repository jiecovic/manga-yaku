# backend-python/infra/db/agent_store.py
"""Persistence helpers for agent sessions, turns, and metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select

from .db import AgentMessage, AgentSession, Volume, get_session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_session_uuid(session_id: str | UUID) -> UUID | None:
    if isinstance(session_id, UUID):
        return session_id
    text = str(session_id or "").strip()
    if not text:
        return None
    try:
        return UUID(text)
    except (TypeError, ValueError):
        return None


def _session_public(session: AgentSession) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "volumeId": session.volume_id,
        "title": session.title,
        "modelId": session.model_id,
        "createdAt": session.created_at.isoformat(),
        "updatedAt": session.updated_at.isoformat(),
    }


def _message_public(message: AgentMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "sessionId": str(message.session_id),
        "role": message.role,
        "content": message.content,
        "createdAt": message.created_at.isoformat(),
        "meta": message.meta,
    }


def list_agent_sessions(volume_id: str) -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.execute(
            select(AgentSession)
            .where(AgentSession.volume_id == volume_id)
            .order_by(AgentSession.updated_at.desc())
        ).scalars()
        return [_session_public(item) for item in rows]


def get_agent_session(session_id: str | UUID) -> AgentSession | None:
    resolved_session_id = _coerce_session_uuid(session_id)
    if resolved_session_id is None:
        return None
    with get_session() as session:
        return session.execute(
            select(AgentSession).where(AgentSession.id == resolved_session_id)
        ).scalar_one_or_none()


def create_agent_session(
    volume_id: str,
    title: str | None,
    *,
    model_id: str | None = None,
) -> dict[str, Any]:
    now = _utc_now()
    session_title = title.strip() if title and title.strip() else "Session"
    with get_session() as session:
        volume = session.execute(select(Volume).where(Volume.id == volume_id)).scalar_one_or_none()
        if volume is None:
            raise ValueError("Volume not found")

        row = AgentSession(
            volume_id=volume_id,
            title=session_title,
            model_id=model_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        return _session_public(row)


def touch_agent_session(session_id: str | UUID) -> None:
    resolved_session_id = _coerce_session_uuid(session_id)
    if resolved_session_id is None:
        return
    with get_session() as session:
        row = session.execute(
            select(AgentSession).where(AgentSession.id == resolved_session_id)
        ).scalar_one_or_none()
        if row is None:
            return
        row.updated_at = _utc_now()


def update_agent_session(
    session_id: str | UUID,
    *,
    title: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    resolved_session_id = _coerce_session_uuid(session_id)
    if resolved_session_id is None:
        raise ValueError("Session not found")
    with get_session() as session:
        row = session.execute(
            select(AgentSession).where(AgentSession.id == resolved_session_id)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Session not found")
        if title is not None:
            row.title = title.strip() or row.title
        if model_id is not None:
            row.model_id = model_id
        row.updated_at = _utc_now()
        session.flush()
        return _session_public(row)


def delete_agent_session(session_id: str | UUID) -> None:
    resolved_session_id = _coerce_session_uuid(session_id)
    if resolved_session_id is None:
        raise ValueError("Session not found")
    with get_session() as session:
        row = session.execute(
            select(AgentSession).where(AgentSession.id == resolved_session_id)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Session not found")
        session.delete(row)


def list_agent_messages(
    session_id: str | UUID,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    resolved_session_id = _coerce_session_uuid(session_id)
    if resolved_session_id is None:
        return []
    with get_session() as session:
        if limit is not None and limit > 0:
            stmt = (
                select(AgentMessage)
                .where(AgentMessage.session_id == resolved_session_id)
                .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
                .limit(int(limit))
            )
            rows = list(session.execute(stmt).scalars())
            rows.reverse()
            return [_message_public(item) for item in rows]

        stmt = (
            select(AgentMessage)
            .where(AgentMessage.session_id == resolved_session_id)
            .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
        )
        rows = session.execute(stmt).scalars()
        return [_message_public(item) for item in rows]


def add_agent_message(
    session_id: str | UUID,
    *,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_session_id = _coerce_session_uuid(session_id)
    if resolved_session_id is None:
        raise ValueError("Session not found")
    now = _utc_now()
    role_value = role.strip().lower()
    if role_value not in {"user", "assistant", "system", "tool"}:
        raise ValueError(f"Unsupported role '{role}'")
    with get_session() as session:
        session_row = session.execute(
            select(AgentSession).where(AgentSession.id == resolved_session_id)
        ).scalar_one_or_none()
        if session_row is None:
            raise ValueError("Session not found")
        row = AgentMessage(
            session_id=resolved_session_id,
            role=role_value,
            content=str(content),
            meta=meta,
            created_at=now,
        )
        session.add(row)
        session_row.updated_at = now
        session.flush()
        return _message_public(row)
