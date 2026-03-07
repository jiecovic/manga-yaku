# backend-python/api/routers/volumes/routes.py
"""HTTP routes for volumes endpoints."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

from api.schemas.volumes import (
    CreateVolumeRequest,
    PageInfo,
    VolumeInfo,
)
from api.services.volumes_helpers import (
    IMAGE_EXTENSIONS,
    calculate_next_index,
    page_exists,
    resolve_image_extension,
    resolve_insert_index,
    sanitize_volume_id,
)
from config import VOLUMES_ROOT, safe_join
from infra.db.db import check_db
from infra.db.db_store import (
    create_volume as create_volume_record,
)
from infra.db.db_store import (
    delete_page,
    ensure_page,
    get_volume,
    list_page_filenames,
    list_pages,
    list_volumes,
    update_volume_next_index,
    volume_name_exists,
)

router = APIRouter(tags=["library"])
@router.get("/health")
async def health():
    """Handle health."""
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
    """Return volumes."""
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


@router.post("/volumes", response_model=VolumeInfo, status_code=status.HTTP_201_CREATED)
async def create_volume(payload: CreateVolumeRequest) -> VolumeInfo:
    """Create volume."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    volume_id = sanitize_volume_id(name)
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

    next_index = calculate_next_index(volume_dir)
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
    """Handle upload volume page."""
    record = get_volume(volume_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    try:
        volume_dir: Path = safe_join(VOLUMES_ROOT, volume_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid path") from e
    if not volume_dir.exists() or not volume_dir.is_dir():
        volume_dir.mkdir(parents=True, exist_ok=True)

    ext = resolve_image_extension(file)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")

    index = record.next_index or 1
    if index < 1:
        index = 1
    filename = f"{index:04d}{ext}"
    image_path = volume_dir / filename
    while page_exists(volume_dir, index):
        index += 1
        filename = f"{index:04d}{ext}"
        image_path = volume_dir / filename

    image_path.write_bytes(content)

    update_volume_next_index(volume_id, index + 1)

    page_index = resolve_insert_index(
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
    """Return pages."""
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
    """Delete volume page."""
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
