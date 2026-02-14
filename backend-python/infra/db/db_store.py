# backend-python/infra/db/db_store.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from .db import (
    Box,
    BoxDetectionRun,
    Page,
    PageContext,
    TextBoxContent,
    Volume,
    VolumeContext,
    get_session,
)


def _default_page() -> dict[str, Any]:
    return {
        "boxes": [],
        "pageContext": "",
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_uuid(raw: str | UUID | None) -> UUID | None:
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _normalize_box_type(raw: str | None) -> str:
    if not raw:
        return "text"
    key = str(raw).strip().lower()
    if key in {"textbox", "speech"}:
        return "text"
    if key in {"frame"}:
        return "panel"
    if key in {"text", "panel", "face", "body"}:
        return key
    return "text"


def _normalize_box_source(raw: str | None) -> str:
    if not raw:
        return "manual"
    key = str(raw).strip().lower()
    if key in {"detect", "detected", "auto"}:
        return "detect"
    return "manual"


def _box_row_to_dict(
    box: Box,
    text_content: TextBoxContent | None,
    run: BoxDetectionRun | None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": box.box_id,
        "orderIndex": int(box.order_index or 0),
        "x": float(box.x),
        "y": float(box.y),
        "width": float(box.width),
        "height": float(box.height),
        "type": _normalize_box_type(box.type),
        "source": _normalize_box_source(box.source),
        "runId": str(box.run_id) if box.run_id else None,
    }

    if run:
        data.update(
            {
                "modelId": run.model_id,
                "modelLabel": run.model_label,
                "modelVersion": run.model_version,
                "modelPath": run.model_path,
                "modelHash": run.model_hash,
                "modelTask": run.task,
            }
        )

    if text_content:
        data["text"] = text_content.ocr_text or ""
        data["translation"] = text_content.translation or ""
    elif data["type"] == "text":
        data["text"] = ""
        data["translation"] = ""

    return data


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
            created_at=_utc_now(),
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


def _page_to_dict(page: Page, boxes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "boxes": boxes,
        "pageContext": page.context or "",
    }


def _get_or_create_page(
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
            return _default_page()

        rows = session.execute(
            select(Box, TextBoxContent, BoxDetectionRun)
            .outerjoin(TextBoxContent, TextBoxContent.box_id == Box.id)
            .outerjoin(BoxDetectionRun, BoxDetectionRun.id == Box.run_id)
            .where(Box.page_id == page.id)
            .order_by(Box.type.asc(), Box.order_index.asc(), Box.box_id.asc())
        ).all()

        boxes = [
            _box_row_to_dict(box, text_content, run)
            for box, text_content, run in rows
        ]

        return _page_to_dict(page, boxes)


def save_page(volume_id: str, filename: str, data: dict[str, Any]) -> None:
    with get_session() as session:
        page = _get_or_create_page(session, volume_id, filename)

        if "pageContext" in data and data["pageContext"] is not None:
            page.context = str(data["pageContext"] or "")

        if "boxes" in data and isinstance(data["boxes"], list):
            session.execute(delete(Box).where(Box.page_id == page.id))

            order_counters: dict[str, int] = {}

            for box in data["boxes"]:
                box_type = _normalize_box_type(box.get("type"))
                run_id = _coerce_uuid(box.get("runId"))
                source = _normalize_box_source(box.get("source"))
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
                    )

                session.add(row)


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
        page = _get_or_create_page(session, volume_id, filename)
        run_id = uuid4()
        run = BoxDetectionRun(
            id=run_id,
            page_id=page.id,
            task=_normalize_box_type(task),
            model_id=model_id,
            model_label=model_label,
            model_version=model_version,
            model_path=model_path,
            model_hash=model_hash,
            params=params,
            created_at=_utc_now(),
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
        page = _get_or_create_page(session, volume_id, filename)
        normalized = _normalize_box_type(box_type)

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
        run_uuid = _coerce_uuid(run_id)
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
                source=_normalize_box_source(source),
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
            created.append(_box_row_to_dict(row, row.text_content, run))
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

    content.updated_at = _utc_now()


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
    normalized = _normalize_box_type(box_type)
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


def ensure_page(
    volume_id: str,
    filename: str,
    *,
    page_index: float | None = None,
) -> None:
    with get_session() as session:
        _get_or_create_page(
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
        page = _get_or_create_page(session, volume_id, filename)
        page.context = context or ""


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


def _normalize_json_blob(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, ensure_ascii=True, default=str))
    except (TypeError, ValueError):
        return None


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
        now = _utc_now()
        if context is None:
            context = VolumeContext(
                volume_id=volume_id,
                rolling_summary=rolling_summary or "",
                updated_at=now,
            )
            session.add(context)
        context.rolling_summary = rolling_summary or ""
        context.active_characters = _normalize_json_blob(active_characters)
        context.open_threads = _normalize_json_blob(open_threads)
        context.glossary = _normalize_json_blob(glossary)
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
        page = _get_or_create_page(session, volume_id, filename)
        context = session.execute(
            select(PageContext).where(PageContext.page_id == page.id)
        ).scalar_one_or_none()
        now = _utc_now()
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
        context.characters_snapshot = _normalize_json_blob(characters_snapshot)
        context.open_threads_snapshot = _normalize_json_blob(open_threads_snapshot)
        context.glossary_snapshot = _normalize_json_blob(glossary_snapshot)
        context.updated_at = now
