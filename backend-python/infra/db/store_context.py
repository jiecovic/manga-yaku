from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .db import Page, PageContext, VolumeContext, get_session
from .store_utils import normalize_json_blob, utc_now
from .store_volume_page import get_or_create_page


def get_page_context_snapshot(volume_id: str, filename: str) -> dict[str, Any] | None:
    with get_session() as session:
        page = session.execute(
            select(Page).where(
                Page.volume_id == volume_id,
                Page.filename == filename,
            )
        ).scalar_one_or_none()
        if page is None:
            return None
        context = session.execute(
            select(PageContext).where(PageContext.page_id == page.id)
        ).scalar_one_or_none()
        if context is None:
            return None
        return {
            "page_summary": context.page_summary or "",
            "image_summary": context.image_summary or "",
            "characters_snapshot": context.characters_snapshot or [],
            "open_threads_snapshot": context.open_threads_snapshot or [],
            "glossary_snapshot": context.glossary_snapshot or [],
            "created_at": context.created_at,
            "updated_at": context.updated_at,
        }


def get_volume_context(volume_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        context = session.execute(
            select(VolumeContext).where(VolumeContext.volume_id == volume_id)
        ).scalar_one_or_none()
        if context is None:
            return None
        return {
            "rolling_summary": context.rolling_summary or "",
            "active_characters": context.active_characters or [],
            "open_threads": context.open_threads or [],
            "glossary": context.glossary or [],
            "last_page_index": context.last_page_index,
            "updated_at": context.updated_at,
        }


def upsert_volume_context(
    volume_id: str,
    *,
    rolling_summary: str,
    active_characters: list[dict[str, Any]] | None,
    open_threads: list[str] | None,
    glossary: list[dict[str, Any]] | None,
    last_page_index: float | None,
) -> None:
    with get_session() as session:
        context = session.execute(
            select(VolumeContext).where(VolumeContext.volume_id == volume_id)
        ).scalar_one_or_none()
        now = utc_now()
        if context is None:
            context = VolumeContext(
                volume_id=volume_id,
                rolling_summary=rolling_summary or "",
                updated_at=now,
            )
            session.add(context)
        context.rolling_summary = rolling_summary or ""
        context.active_characters = normalize_json_blob(active_characters)
        context.open_threads = normalize_json_blob(open_threads)
        context.glossary = normalize_json_blob(glossary)
        context.last_page_index = (
            float(last_page_index) if last_page_index is not None else None
        )
        context.updated_at = now


def upsert_page_context(
    volume_id: str,
    filename: str,
    *,
    page_summary: str,
    image_summary: str,
    characters_snapshot: list[dict[str, Any]] | None,
    open_threads_snapshot: list[str] | None,
    glossary_snapshot: list[dict[str, Any]] | None,
) -> None:
    with get_session() as session:
        page = get_or_create_page(session, volume_id, filename)
        context = session.execute(
            select(PageContext).where(PageContext.page_id == page.id)
        ).scalar_one_or_none()
        now = utc_now()
        if context is None:
            context = PageContext(
                page_id=page.id,
                volume_id=volume_id,
                page_summary=page_summary or "",
                image_summary=image_summary or "",
                created_at=now,
                updated_at=now,
            )
            session.add(context)
        context.page_summary = page_summary or ""
        context.image_summary = image_summary or ""
        context.characters_snapshot = normalize_json_blob(characters_snapshot)
        context.open_threads_snapshot = normalize_json_blob(open_threads_snapshot)
        context.glossary_snapshot = normalize_json_blob(glossary_snapshot)
        context.updated_at = now
