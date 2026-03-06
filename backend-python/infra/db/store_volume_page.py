# backend-python/infra/db/store_volume_page.py
"""Database persistence for volume and page metadata."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select

from .db import Box, BoxDetectionRun, Page, TextBoxContent, Volume, get_session
from .store_utils import (
    box_row_to_dict,
    coerce_uuid,
    default_page,
    normalize_box_source,
    normalize_box_type,
    utc_now,
)


def list_volumes() -> list[Volume]:
    with get_session() as session:
        return session.execute(select(Volume).order_by(Volume.created_at.asc())).scalars().all()


def get_volume(volume_id: str) -> Volume | None:
    with get_session() as session:
        return session.execute(
            select(Volume).where(Volume.id == volume_id)
        ).scalar_one_or_none()


def volume_name_exists(name: str) -> bool:
    with get_session() as session:
        existing = session.execute(
            select(Volume.id).where(func.lower(Volume.name) == name.casefold())
        ).first()
        return existing is not None


def create_volume(volume_id: str, name: str, *, next_index: int = 1) -> Volume:
    with get_session() as session:
        volume = Volume(
            id=volume_id,
            name=name,
            created_at=utc_now(),
            next_index=max(1, int(next_index)),
        )
        session.add(volume)
        session.flush()
        return volume


def update_volume_next_index(volume_id: str, next_index: int) -> None:
    with get_session() as session:
        volume = session.execute(
            select(Volume).where(Volume.id == volume_id)
        ).scalar_one_or_none()
        if volume is None:
            return
        volume.next_index = max(1, int(next_index))


def delete_volume(volume_id: str) -> None:
    with get_session() as session:
        page_ids = session.execute(
            select(Page.id).where(Page.volume_id == volume_id)
        ).scalars().all()
        if page_ids:
            session.execute(delete(Box).where(Box.page_id.in_(page_ids)))
            session.execute(delete(Page).where(Page.id.in_(page_ids)))
        session.execute(delete(Volume).where(Volume.id == volume_id))


def list_page_filenames(volume_id: str) -> list[str]:
    with get_session() as session:
        return session.execute(
            select(Page.filename)
            .where(Page.volume_id == volume_id)
            .order_by(Page.page_index.asc().nulls_last(), Page.filename.asc())
        ).scalars().all()


def list_pages(volume_id: str) -> list[Page]:
    with get_session() as session:
        return session.execute(
            select(Page)
            .where(Page.volume_id == volume_id)
            .order_by(Page.page_index.asc().nulls_last(), Page.filename.asc())
        ).scalars().all()


def get_page_index(volume_id: str, filename: str) -> float | None:
    with get_session() as session:
        return session.execute(
            select(Page.page_index)
            .where(
                Page.volume_id == volume_id,
                Page.filename == filename,
            )
        ).scalar_one_or_none()


def delete_page(volume_id: str, filename: str) -> None:
    with get_session() as session:
        page = session.execute(
            select(Page).where(
                Page.volume_id == volume_id,
                Page.filename == filename,
            )
        ).scalar_one_or_none()
        if page is None:
            return
        session.execute(delete(Box).where(Box.page_id == page.id))
        session.execute(delete(Page).where(Page.id == page.id))


def page_to_dict(page: Page, boxes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "boxes": boxes,
        "pageContext": page.context or "",
    }


def get_or_create_page(
    session,
    volume_id: str,
    filename: str,
    *,
    page_index: float | None = None,
) -> Page:
    page = session.execute(
        select(Page).where(
            Page.volume_id == volume_id,
            Page.filename == filename,
        )
    ).scalar_one_or_none()

    if page is None:
        if page_index is None:
            max_index = session.execute(
                select(func.max(Page.page_index))
                .where(Page.volume_id == volume_id)
            ).scalar_one_or_none()
            page_index = (max_index or 0) + 1.0
        page = Page(
            volume_id=volume_id,
            filename=filename,
            context="",
            page_index=page_index,
        )
        session.add(page)
        session.flush()
    elif page_index is not None and page.page_index is None:
        page.page_index = page_index

    return page


def load_page(volume_id: str, filename: str) -> dict[str, Any]:
    with get_session() as session:
        page = session.execute(
            select(Page).where(
                Page.volume_id == volume_id,
                Page.filename == filename,
            )
        ).scalar_one_or_none()

        if page is None:
            return default_page()

        rows = session.execute(
            select(Box, TextBoxContent, BoxDetectionRun)
            .outerjoin(TextBoxContent, TextBoxContent.box_id == Box.id)
            .outerjoin(BoxDetectionRun, BoxDetectionRun.id == Box.run_id)
            .where(Box.page_id == page.id)
            .order_by(Box.type.asc(), Box.order_index.asc(), Box.box_id.asc())
        ).all()

        boxes = [
            box_row_to_dict(box, text_content, run)
            for box, text_content, run in rows
        ]

        return page_to_dict(page, boxes)


def save_page(volume_id: str, filename: str, data: dict[str, Any]) -> None:
    with get_session() as session:
        page = get_or_create_page(session, volume_id, filename)

        if "pageContext" in data and data["pageContext"] is not None:
            page.context = str(data["pageContext"] or "")

        if "boxes" in data and isinstance(data["boxes"], list):
            session.execute(delete(Box).where(Box.page_id == page.id))

            order_counters: dict[str, int] = {}

            for box in data["boxes"]:
                box_type = normalize_box_type(box.get("type"))
                run_id = coerce_uuid(box.get("runId"))
                source = normalize_box_source(box.get("source"))
                order_counters[box_type] = order_counters.get(box_type, 0) + 1
                order_index = order_counters[box_type]

                if run_id:
                    existing_run = session.execute(
                        select(BoxDetectionRun.id).where(BoxDetectionRun.id == run_id)
                    ).scalar_one_or_none()
                    if existing_run is None:
                        run_id = None

                row = Box(
                    page_id=page.id,
                    box_id=int(box.get("id") or 0),
                    order_index=order_index,
                    type=box_type,
                    source=source,
                    run_id=run_id,
                    x=float(box.get("x") or 0.0),
                    y=float(box.get("y") or 0.0),
                    width=float(box.get("width") or 0.0),
                    height=float(box.get("height") or 0.0),
                )
                if box_type == "text":
                    row.text_content = TextBoxContent(
                        ocr_text=str(box.get("text") or ""),
                        translation=str(box.get("translation") or ""),
                        note=str(box.get("note") or ""),
                    )

                session.add(row)


def ensure_page(
    volume_id: str,
    filename: str,
    *,
    page_index: float | None = None,
) -> None:
    with get_session() as session:
        get_or_create_page(
            session,
            volume_id,
            filename,
            page_index=page_index,
        )


def get_max_page_index(volume_id: str) -> float | None:
    with get_session() as session:
        return session.execute(
            select(func.max(Page.page_index))
            .where(Page.volume_id == volume_id)
        ).scalar_one_or_none()


def get_page_context(volume_id: str, filename: str) -> str:
    with get_session() as session:
        page = session.execute(
            select(Page).where(
                Page.volume_id == volume_id,
                Page.filename == filename,
            )
        ).scalar_one_or_none()
        return (page.context or "") if page else ""


def set_page_context(volume_id: str, filename: str, context: str) -> None:
    with get_session() as session:
        page = get_or_create_page(session, volume_id, filename)
        page.context = context or ""
