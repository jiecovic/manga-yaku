# backend-python/api/routers/volumes.py
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import VOLUMES_ROOT, safe_join
from infra.db.db import check_db
from infra.db.db_store import (
    clear_page_context_snapshot,
    clear_volume_context,
    clear_volume_derived_data,
    delete_page,
    delete_volume,
    ensure_page,
    get_max_page_index,
    get_page_context_snapshot,
    get_volume,
    get_volume_context,
    list_page_filenames,
    list_pages,
    list_volumes,
    update_volume_next_index,
    volume_name_exists,
)
from infra.db.db_store import (
    create_volume as create_volume_record,
)
from infra.db.db_store import (
    get_page_context as load_page_context,
)
from infra.db.db_store import (
    set_page_context as save_page_context,
)

router = APIRouter(tags=["library"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class VolumeInfo(BaseModel):
    id: str
    name: str
    pageCount: int
    coverImageUrl: str | None


class PageInfo(BaseModel):
    id: str
    volumeId: str
    filename: str
    relPath: str
    imageUrl: str | None = None
    missing: bool | None = None


# ---------- context payloads ----------

class PageContextPayload(BaseModel):
    context: str


class CharacterInfo(BaseModel):
    name: str
    gender: str
    info: str


class GlossaryEntry(BaseModel):
    term: str
    translation: str
    note: str


class VolumeMemoryResponse(BaseModel):
    rollingSummary: str
    activeCharacters: list[CharacterInfo]
    openThreads: list[str]
    glossary: list[GlossaryEntry]
    lastPageIndex: float | None = None
    updatedAt: str | None = None


class PageMemoryResponse(BaseModel):
    pageSummary: str
    imageSummary: str
    characters: list[CharacterInfo]
    openThreads: list[str]
    glossary: list[GlossaryEntry]
    createdAt: str | None = None
    updatedAt: str | None = None


class ClearMemoryResponse(BaseModel):
    cleared: bool


class ClearVolumeDerivedDataDetails(BaseModel):
    pagesTouched: int
    boxesDeleted: int
    detectionRunsDeleted: int
    pageContextSnapshotsDeleted: int
    pageNotesCleared: int
    volumeContextDeleted: int
    agentSessionsDeleted: int
    workflowRunsDeleted: int
    taskRunsDeleted: int
    taskAttemptEventsDeleted: int
    llmCallLogsDeleted: int
    llmPayloadFilesDeleted: int
    agentDebugFilesDeleted: int


class ClearVolumeDerivedDataResponse(BaseModel):
    cleared: bool
    details: ClearVolumeDerivedDataDetails


class CreateVolumeRequest(BaseModel):
    name: str


class MissingVolume(BaseModel):
    id: str
    name: str


class PruneMissingRequest(BaseModel):
    ids: list[str]


class MissingPage(BaseModel):
    volumeId: str
    filename: str


class PruneMissingPagesRequest(BaseModel):
    pages: list[MissingPage]


def _sanitize_volume_id(name: str) -> str:
    cleaned = name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", cleaned)
    cleaned = cleaned.strip("-_")
    return cleaned


def _calculate_next_index(volume_dir: Path) -> int:
    max_index = 0
    for entry in volume_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
            stem = entry.stem
            if stem.isdigit():
                max_index = max(max_index, int(stem))
    return max_index + 1


def _unique_volume_name(base: str) -> str:
    candidate = base
    suffix = 2
    while volume_name_exists(candidate):
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def _page_exists(volume_dir: Path, index: int) -> bool:
    stem = f"{index:04d}"
    return any((volume_dir / f"{stem}{ext}").exists() for ext in IMAGE_EXTENSIONS)


def _resolve_image_extension(file: UploadFile) -> str:
    if file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            return suffix

    content_type = (file.content_type or "").lower()
    if content_type == "image/jpeg":
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"

    raise HTTPException(status_code=400, detail="Unsupported image type")


def _resolve_insert_index(
    volume_id: str,
    *,
    insert_before: str | None,
    insert_after: str | None,
) -> float:
    pages = list_pages(volume_id)
    if not pages:
        return 1.0

    if insert_before:
        target_idx = next(
            (idx for idx, page in enumerate(pages) if page.filename == insert_before),
            None,
        )
        if target_idx is None:
            raise HTTPException(status_code=400, detail="insert_before not found")
        target_index = pages[target_idx].page_index or float(target_idx + 1)
        prev_index = pages[target_idx - 1].page_index if target_idx > 0 else None
        if prev_index is None:
            return target_index - 1.0
        return (prev_index + target_index) / 2.0

    if insert_after:
        target_idx = next(
            (idx for idx, page in enumerate(pages) if page.filename == insert_after),
            None,
        )
        if target_idx is None:
            raise HTTPException(status_code=400, detail="insert_after not found")
        target_index = pages[target_idx].page_index or float(target_idx + 1)
        next_index = (
            pages[target_idx + 1].page_index
            if target_idx + 1 < len(pages)
            else None
        )
        if next_index is None:
            return target_index + 1.0
        return (target_index + next_index) / 2.0

    max_index = get_max_page_index(volume_id)
    return (max_index or float(len(pages))) + 1.0


def _to_iso(value: datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


@router.get("/health")
async def health():
    ok, _error = check_db()
    if ok:
        return {"status": "ok", "database": "ok"}
    return JSONResponse(
        status_code=503,
        content={
            "status": "degraded",
            "database": "unavailable",
            "detail": "Database unavailable. Check DATABASE_URL and that Postgres is running.",
        },
    )


@router.get("/volumes", response_model=list[VolumeInfo])
async def get_volumes():
    volumes: list[VolumeInfo] = []

    for record in list_volumes():
        volume_id = record.id
        volume_dir = VOLUMES_ROOT / volume_id
        page_filenames = list_page_filenames(volume_id)

        cover_url = None
        if page_filenames and volume_dir.is_dir():
            for filename in page_filenames:
                candidate = volume_dir / filename
                if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
                    rel = f"{volume_id}/{filename}".replace("\\", "/")
                    cover_url = f"/images/{rel}"
                    break

        volumes.append(
            VolumeInfo(
                id=volume_id,
                name=record.name,
                pageCount=len(page_filenames),
                coverImageUrl=cover_url,
            )
        )

    return volumes


@router.get("/volumes/sync/missing", response_model=list[MissingVolume])
async def list_missing_volumes() -> list[MissingVolume]:
    missing: list[MissingVolume] = []
    for record in list_volumes():
        volume_dir = VOLUMES_ROOT / record.id
        if not volume_dir.exists():
            missing.append(MissingVolume(id=record.id, name=record.name))
    return missing


@router.post("/volumes/sync/import")
async def import_missing_volumes() -> dict:
    imported: list[str] = []
    if not VOLUMES_ROOT.exists():
        return {"imported": 0, "ids": []}

    for entry in sorted(VOLUMES_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        volume_id = entry.name
        if get_volume(volume_id) is not None:
            continue
        display_name = _unique_volume_name(volume_id)
        next_index = _calculate_next_index(entry)
        create_volume_record(volume_id, display_name, next_index=next_index)
        imported.append(volume_id)

    return {"imported": len(imported), "ids": imported}


@router.post("/volumes/sync/prune")
async def prune_missing_volumes(payload: PruneMissingRequest) -> dict:
    deleted = 0
    for volume_id in payload.ids:
        if get_volume(volume_id) is None:
            continue
        volume_dir = VOLUMES_ROOT / volume_id
        if volume_dir.exists():
            continue
        delete_volume(volume_id)
        deleted += 1
    return {"deleted": deleted}


@router.get("/volumes/sync/pages/missing", response_model=list[MissingPage])
async def list_missing_pages() -> list[MissingPage]:
    missing: list[MissingPage] = []
    for record in list_volumes():
        volume_dir = VOLUMES_ROOT / record.id
        filenames = list_page_filenames(record.id)
        if not volume_dir.exists():
            missing.extend(
                MissingPage(volumeId=record.id, filename=filename)
                for filename in filenames
            )
            continue
        for filename in filenames:
            if not (volume_dir / filename).exists():
                missing.append(MissingPage(volumeId=record.id, filename=filename))
    return missing


@router.post("/volumes/sync/pages/import")
async def import_missing_pages() -> dict:
    imported: list[MissingPage] = []
    for record in list_volumes():
        volume_dir = VOLUMES_ROOT / record.id
        if not volume_dir.is_dir():
            continue
        pages = list_pages(record.id)
        existing = {page.filename for page in pages}
        new_entries = [
            entry
            for entry in volume_dir.iterdir()
            if entry.is_file()
            and entry.suffix.lower() in IMAGE_EXTENSIONS
            and entry.name not in existing
        ]
        if not new_entries:
            continue

        new_entries.sort(key=lambda entry: entry.name)

        if not pages:
            next_index = 1.0
        else:
            max_index = max(
                page.page_index or float(idx + 1)
                for idx, page in enumerate(pages)
            )
            next_index = max_index + 1.0

        for entry in new_entries:
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            ensure_page(record.id, entry.name, page_index=next_index)
            next_index += 1.0
            imported.append(MissingPage(volumeId=record.id, filename=entry.name))
        update_volume_next_index(record.id, _calculate_next_index(volume_dir))
    return {"imported": len(imported), "items": [item.model_dump() for item in imported]}


@router.post("/volumes/sync/pages/prune")
async def prune_missing_pages(payload: PruneMissingPagesRequest) -> dict:
    deleted = 0
    for page in payload.pages:
        volume_dir = VOLUMES_ROOT / page.volumeId
        if (volume_dir / page.filename).exists():
            continue
        delete_page(page.volumeId, page.filename)
        deleted += 1
    return {"deleted": deleted}


@router.post("/volumes", response_model=VolumeInfo, status_code=status.HTTP_201_CREATED)
async def create_volume(payload: CreateVolumeRequest) -> VolumeInfo:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    volume_id = _sanitize_volume_id(name)
    if not volume_id:
        raise HTTPException(
            status_code=400,
            detail="Name must include letters or numbers",
        )

    VOLUMES_ROOT.mkdir(parents=True, exist_ok=True)

    volume_dir = safe_join(VOLUMES_ROOT, volume_id)
    if get_volume(volume_id) is not None:
        raise HTTPException(status_code=409, detail="Volume name already exists")

    if volume_name_exists(name):
        raise HTTPException(status_code=409, detail="Volume name already exists")

    if volume_dir.exists():
        if not volume_dir.is_dir():
            raise HTTPException(
                status_code=409,
                detail="Volume path already exists and is not a folder",
            )
    else:
        volume_dir.mkdir(parents=True, exist_ok=False)

    next_index = _calculate_next_index(volume_dir)
    record = create_volume_record(volume_id, name, next_index=next_index)

    return VolumeInfo(
        id=record.id,
        name=record.name,
        pageCount=0,
        coverImageUrl=None,
    )


@router.post(
    "/volumes/{volume_id}/pages/upload",
    response_model=PageInfo,
    status_code=status.HTTP_201_CREATED,
)
async def upload_volume_page(
    volume_id: str,
    file: Annotated[UploadFile, File(...)],
    insert_before: str | None = Query(None),
    insert_after: str | None = Query(None),
) -> PageInfo:
    record = get_volume(volume_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    try:
        volume_dir: Path = safe_join(VOLUMES_ROOT, volume_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid path") from e
    if not volume_dir.exists() or not volume_dir.is_dir():
        volume_dir.mkdir(parents=True, exist_ok=True)

    ext = _resolve_image_extension(file)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")

    index = record.next_index or 1
    if index < 1:
        index = 1
    filename = f"{index:04d}{ext}"
    image_path = volume_dir / filename
    while _page_exists(volume_dir, index):
        index += 1
        filename = f"{index:04d}{ext}"
        image_path = volume_dir / filename

    image_path.write_bytes(content)

    update_volume_next_index(volume_id, index + 1)

    page_index = _resolve_insert_index(
        volume_id,
        insert_before=insert_before,
        insert_after=insert_after,
    )

    ensure_page(volume_id, filename, page_index=page_index)

    rel_path = f"{volume_id}/{filename}".replace("\\", "/")
    return PageInfo(
        id=rel_path,
        volumeId=volume_id,
        filename=filename,
        relPath=rel_path,
        imageUrl=f"/images/{rel_path}",
        missing=False,
    )


@router.get("/volumes/{volume_id}/pages", response_model=list[PageInfo])
async def get_pages(volume_id: str):
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    try:
        vol_dir: Path = safe_join(VOLUMES_ROOT, volume_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid path") from e
    if not vol_dir.exists() or not vol_dir.is_dir():
        vol_dir = VOLUMES_ROOT / volume_id

    pages = list_pages(volume_id)

    out: list[PageInfo] = []
    for page in pages:
        filename = page.filename
        rel_path = f"{volume_id}/{filename}".replace("\\", "/")
        img_path = vol_dir / filename
        exists = img_path.is_file()
        out.append(
            PageInfo(
                id=rel_path,
                volumeId=volume_id,
                filename=filename,
                relPath=rel_path,
                imageUrl=f"/images/{rel_path}" if exists else None,
                missing=not exists,
            )
        )

    return out


@router.delete("/volumes/{volume_id}/pages/{filename}")
async def delete_volume_page(volume_id: str, filename: str) -> dict:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    filenames = set(list_page_filenames(volume_id))
    if filename not in filenames:
        raise HTTPException(status_code=404, detail="Page not found")
    try:
        file_path = safe_join(VOLUMES_ROOT, volume_id, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid path") from e

    missing_file = True
    if file_path.exists():
        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Page path is not a file")
        file_path.unlink()
        missing_file = False

    delete_page(volume_id, filename)
    return {"deleted": True, "missingFile": missing_file}


# =========================
# PAGE CONTEXT (database)
# =========================


@router.get(
    "/volumes/{volume_id}/pages/{filename}/context",
    response_model=PageContextPayload,
)
async def get_page_context(
        volume_id: str,
        filename: str,
) -> PageContextPayload:
    try:
        ctx = load_page_context(volume_id, filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return PageContextPayload(context=ctx or "")


@router.put(
    "/volumes/{volume_id}/pages/{filename}/context",
    response_model=PageContextPayload,
)
async def set_page_context(
        volume_id: str,
        filename: str,
        payload: PageContextPayload,
) -> PageContextPayload:
    try:
        save_page_context(volume_id, filename, payload.context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return payload


@router.get(
    "/volumes/{volume_id}/memory",
    response_model=VolumeMemoryResponse,
)
async def get_volume_memory(volume_id: str) -> VolumeMemoryResponse:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    context = get_volume_context(volume_id)
    if context is None:
        return VolumeMemoryResponse(
            rollingSummary="",
            activeCharacters=[],
            openThreads=[],
            glossary=[],
            lastPageIndex=None,
            updatedAt=None,
        )
    return VolumeMemoryResponse(
        rollingSummary=str(context.get("rolling_summary") or ""),
        activeCharacters=context.get("active_characters") or [],
        openThreads=context.get("open_threads") or [],
        glossary=context.get("glossary") or [],
        lastPageIndex=context.get("last_page_index"),
        updatedAt=_to_iso(context.get("updated_at")),
    )


@router.get(
    "/volumes/{volume_id}/pages/{filename}/memory",
    response_model=PageMemoryResponse,
)
async def get_page_memory(
    volume_id: str,
    filename: str,
) -> PageMemoryResponse:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    if filename not in set(list_page_filenames(volume_id)):
        raise HTTPException(status_code=404, detail="Page not found")
    context = get_page_context_snapshot(volume_id, filename)
    if context is None:
        return PageMemoryResponse(
            pageSummary="",
            imageSummary="",
            characters=[],
            openThreads=[],
            glossary=[],
            createdAt=None,
            updatedAt=None,
        )
    return PageMemoryResponse(
        pageSummary=str(context.get("page_summary") or ""),
        imageSummary=str(context.get("image_summary") or ""),
        characters=context.get("characters_snapshot") or [],
        openThreads=context.get("open_threads_snapshot") or [],
        glossary=context.get("glossary_snapshot") or [],
        createdAt=_to_iso(context.get("created_at")),
        updatedAt=_to_iso(context.get("updated_at")),
    )


@router.delete(
    "/volumes/{volume_id}/memory",
    response_model=ClearMemoryResponse,
)
async def clear_volume_memory(volume_id: str) -> ClearMemoryResponse:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    clear_volume_context(volume_id)
    return ClearMemoryResponse(cleared=True)


@router.delete(
    "/volumes/{volume_id}/pages/{filename}/memory",
    response_model=ClearMemoryResponse,
)
async def clear_page_memory(
    volume_id: str,
    filename: str,
) -> ClearMemoryResponse:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    if filename not in set(list_page_filenames(volume_id)):
        raise HTTPException(status_code=404, detail="Page not found")

    # Clear both structured page memory snapshot and manual page context text.
    clear_page_context_snapshot(volume_id, filename)
    save_page_context(volume_id, filename, "")
    return ClearMemoryResponse(cleared=True)


@router.delete(
    "/volumes/{volume_id}/derived-data",
    response_model=ClearVolumeDerivedDataResponse,
)
async def clear_volume_derived_state(
    volume_id: str,
) -> ClearVolumeDerivedDataResponse:
    if get_volume(volume_id) is None:
        raise HTTPException(status_code=404, detail="Volume not found")

    try:
        raw = clear_volume_derived_data(volume_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ClearVolumeDerivedDataResponse(
        cleared=True,
        details=ClearVolumeDerivedDataDetails(
            pagesTouched=int(raw.get("pages_touched") or 0),
            boxesDeleted=int(raw.get("boxes_deleted") or 0),
            detectionRunsDeleted=int(raw.get("detection_runs_deleted") or 0),
            pageContextSnapshotsDeleted=int(
                raw.get("page_context_snapshots_deleted") or 0
            ),
            pageNotesCleared=int(raw.get("page_notes_cleared") or 0),
            volumeContextDeleted=int(raw.get("volume_context_deleted") or 0),
            agentSessionsDeleted=int(raw.get("agent_sessions_deleted") or 0),
            workflowRunsDeleted=int(raw.get("workflow_runs_deleted") or 0),
            taskRunsDeleted=int(raw.get("task_runs_deleted") or 0),
            taskAttemptEventsDeleted=int(raw.get("task_attempt_events_deleted") or 0),
            llmCallLogsDeleted=int(raw.get("llm_call_logs_deleted") or 0),
            llmPayloadFilesDeleted=int(raw.get("llm_payload_files_deleted") or 0),
            agentDebugFilesDeleted=int(raw.get("agent_debug_files_deleted") or 0),
        ),
    )
