# backend-python/api/routers/volumes/sync.py
"""HTTP routes for volume/database filesystem synchronization operations."""

from __future__ import annotations

from api.schemas.volumes import (
    MissingPage,
    MissingVolume,
    PruneMissingPagesRequest,
    PruneMissingRequest,
)
from api.services.volumes_helpers import (
    IMAGE_EXTENSIONS,
    calculate_next_index,
    unique_volume_name,
)
from config import VOLUMES_ROOT
from fastapi import APIRouter
from infra.db.db_store import (
    create_volume as create_volume_record,
)
from infra.db.db_store import (
    delete_page,
    delete_volume,
    ensure_page,
    get_volume,
    list_page_filenames,
    list_pages,
    list_volumes,
    update_volume_next_index,
)

router = APIRouter(tags=["library"])


@router.get("/volumes/sync/missing", response_model=list[MissingVolume])
async def list_missing_volumes() -> list[MissingVolume]:
    """List missing volumes."""
    missing: list[MissingVolume] = []
    for record in list_volumes():
        volume_dir = VOLUMES_ROOT / record.id
        if not volume_dir.exists():
            missing.append(MissingVolume(id=record.id, name=record.name))
    return missing


@router.post("/volumes/sync/import")
async def import_missing_volumes() -> dict:
    """Handle import missing volumes."""
    imported: list[str] = []
    if not VOLUMES_ROOT.exists():
        return {"imported": 0, "ids": []}

    for entry in sorted(VOLUMES_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        volume_id = entry.name
        if get_volume(volume_id) is not None:
            continue
        display_name = unique_volume_name(volume_id)
        next_index = calculate_next_index(entry)
        create_volume_record(volume_id, display_name, next_index=next_index)
        imported.append(volume_id)

    return {"imported": len(imported), "ids": imported}


@router.post("/volumes/sync/prune")
async def prune_missing_volumes(payload: PruneMissingRequest) -> dict:
    """Handle prune missing volumes."""
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
    """List missing pages."""
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
    """Handle import missing pages."""
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
        update_volume_next_index(record.id, calculate_next_index(volume_dir))
    return {"imported": len(imported), "items": [item.model_dump() for item in imported]}


@router.post("/volumes/sync/pages/prune")
async def prune_missing_pages(payload: PruneMissingPagesRequest) -> dict:
    """Handle prune missing pages."""
    deleted = 0
    for page in payload.pages:
        volume_dir = VOLUMES_ROOT / page.volumeId
        if (volume_dir / page.filename).exists():
            continue
        delete_page(page.volumeId, page.filename)
        deleted += 1
    return {"deleted": deleted}
