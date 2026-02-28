"""Database box record CRUD and mapping helpers."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from .db import Box, BoxDetectionRun, Page, TextBoxContent, get_session
from .store_utils import (
    box_row_to_dict,
    coerce_uuid,
    normalize_box_source,
    normalize_box_type,
    utc_now,
)
from .store_volume_page import get_or_create_page


def create_detection_run(
    volume_id: str,
    filename: str,
    *,
    task: str,
    model_id: str | None = None,
    model_label: str | None = None,
    model_version: str | None = None,
    model_path: str | None = None,
    model_hash: str | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    with get_session() as session:
        page = get_or_create_page(session, volume_id, filename)
        run_id = uuid4()
        run = BoxDetectionRun(
            id=run_id,
            page_id=page.id,
            task=normalize_box_type(task),
            model_id=model_id,
            model_label=model_label,
            model_version=model_version,
            model_path=model_path,
            model_hash=model_hash,
            params=params,
            created_at=utc_now(),
        )
        session.add(run)
        return str(run_id)


def replace_boxes_for_type(
    volume_id: str,
    filename: str,
    *,
    box_type: str,
    boxes: list[dict[str, Any]],
    run_id: str | UUID | None = None,
    source: str = "detect",
    replace_existing: bool = True,
) -> list[dict[str, Any]]:
    with get_session() as session:
        page = get_or_create_page(session, volume_id, filename)
        normalized = normalize_box_type(box_type)

        if replace_existing:
            session.execute(
                delete(Box).where(
                    Box.page_id == page.id,
                    Box.type == normalized,
                )
            )

        max_id = session.execute(
            select(func.max(Box.box_id)).where(Box.page_id == page.id)
        ).scalar_one_or_none()
        next_id = int(max_id or 0) + 1

        if replace_existing:
            next_order_index = 1
        else:
            max_order = session.execute(
                select(func.max(Box.order_index)).where(
                    Box.page_id == page.id,
                    Box.type == normalized,
                )
            ).scalar_one_or_none()
            next_order_index = int(max_order or 0) + 1

        run: BoxDetectionRun | None = None
        run_uuid = coerce_uuid(run_id)
        if run_uuid:
            run = session.execute(
                select(BoxDetectionRun).where(BoxDetectionRun.id == run_uuid)
            ).scalar_one_or_none()
            if run is None:
                run_uuid = None

        created: list[dict[str, Any]] = []
        for det in boxes:
            row = Box(
                page_id=page.id,
                box_id=next_id,
                order_index=next_order_index,
                type=normalized,
                source=normalize_box_source(source),
                run_id=run_uuid,
                x=float(det.get("x") or 0.0),
                y=float(det.get("y") or 0.0),
                width=float(det.get("width") or 0.0),
                height=float(det.get("height") or 0.0),
            )
            if normalized == "text":
                row.text_content = TextBoxContent(
                    ocr_text=str(det.get("text") or ""),
                    translation=str(det.get("translation") or ""),
                )
            session.add(row)
            session.flush()
            created.append(box_row_to_dict(row, row.text_content, run))
            next_id += 1
            next_order_index += 1

        return created


def _find_box_by_box_id(
    session,
    volume_id: str,
    filename: str,
    box_id: int,
) -> Box | None:
    return session.execute(
        select(Box)
        .join(Page, Page.id == Box.page_id)
        .where(
            Page.volume_id == volume_id,
            Page.filename == filename,
            Box.box_id == box_id,
        )
    ).scalar_one_or_none()


def _upsert_text_content(
    session,
    *,
    box: Box,
    ocr_text: str | None = None,
    translation: str | None = None,
) -> None:
    content = session.execute(
        select(TextBoxContent).where(TextBoxContent.box_id == box.id)
    ).scalar_one_or_none()
    if content is None:
        content = TextBoxContent(
            box_id=box.id,
            ocr_text="",
            translation="",
        )
        session.add(content)

    if ocr_text is not None:
        content.ocr_text = ocr_text
    if translation is not None:
        content.translation = translation

    content.updated_at = utc_now()


def set_box_translation_by_id(
    volume_id: str,
    filename: str,
    *,
    box_id: int,
    translation: str,
) -> None:
    with get_session() as session:
        box = _find_box_by_box_id(session, volume_id, filename, box_id)
        if box is None or box.type != "text":
            return
        _upsert_text_content(session, box=box, translation=translation)


def set_box_ocr_text_by_id(
    volume_id: str,
    filename: str,
    *,
    box_id: int,
    ocr_text: str,
) -> None:
    with get_session() as session:
        box = _find_box_by_box_id(session, volume_id, filename, box_id)
        if box is None or box.type != "text":
            return
        _upsert_text_content(session, box=box, ocr_text=ocr_text)


def update_box_geometry_by_id(
    volume_id: str,
    filename: str,
    *,
    box_id: int,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    with get_session() as session:
        box = _find_box_by_box_id(session, volume_id, filename, box_id)
        if box is None:
            return
        box.x = x
        box.y = y
        box.width = width
        box.height = height


def delete_boxes_by_ids(
    volume_id: str,
    filename: str,
    box_ids: list[int],
) -> int:
    if not box_ids:
        return 0
    with get_session() as session:
        page = session.execute(
            select(Page).where(
                Page.volume_id == volume_id,
                Page.filename == filename,
            )
        ).scalar_one_or_none()
        if page is None:
            return 0
        result = session.execute(
            delete(Box).where(
                Box.page_id == page.id,
                Box.box_id.in_(box_ids),
            )
        )
        return int(result.rowcount or 0)


def set_box_order_for_type(
    volume_id: str,
    filename: str,
    *,
    box_type: str,
    ordered_ids: list[int],
) -> bool:
    normalized = normalize_box_type(box_type)
    with get_session() as session:
        page = session.execute(
            select(Page).where(
                Page.volume_id == volume_id,
                Page.filename == filename,
            )
        ).scalar_one_or_none()
        if page is None:
            return False

        boxes = session.execute(
            select(Box)
            .where(
                Box.page_id == page.id,
                Box.type == normalized,
            )
        ).scalars().all()
        by_id = {int(box.box_id): box for box in boxes}
        if not ordered_ids:
            return False
        if set(ordered_ids) != set(by_id.keys()):
            return False

        for index, box_id in enumerate(ordered_ids, start=1):
            target = by_id.get(int(box_id))
            if target is None:
                return False
            target.order_index = index

        return True


def get_box_text_by_id(
    volume_id: str,
    filename: str,
    box_id: int,
) -> str | None:
    with get_session() as session:
        box = _find_box_by_box_id(session, volume_id, filename, box_id)
        if box is None or box.type != "text":
            return None
        content = session.execute(
            select(TextBoxContent).where(TextBoxContent.box_id == box.id)
        ).scalar_one_or_none()
        return (content.ocr_text or "") if content else ""
