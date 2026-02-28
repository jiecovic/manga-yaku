# backend-python/api/routers/volumes/memory.py
"""HTTP routes for volume and page memory state management."""

from __future__ import annotations

from api.schemas.volumes import (
    ClearMemoryResponse,
    ClearVolumeDerivedDataResponse,
    PageContextPayload,
    PageMemoryResponse,
    VolumeMemoryResponse,
)
from api.services.volumes_memory_service import (
    clear_page_memory as clear_page_memory_data,
)
from api.services.volumes_memory_service import (
    clear_volume_derived_state_payload,
    get_page_memory_payload,
    get_volume_memory_payload,
)
from api.services.volumes_memory_service import (
    clear_volume_memory as clear_volume_memory_data,
)
from fastapi import APIRouter, HTTPException
from infra.db.db_store import (
    get_page_context as load_page_context,
)
from infra.db.db_store import (
    set_page_context as save_page_context,
)

router = APIRouter(tags=["library"])


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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return payload


@router.get(
    "/volumes/{volume_id}/memory",
    response_model=VolumeMemoryResponse,
)
async def get_volume_memory(volume_id: str) -> VolumeMemoryResponse:
    return VolumeMemoryResponse(**get_volume_memory_payload(volume_id))


@router.get(
    "/volumes/{volume_id}/pages/{filename}/memory",
    response_model=PageMemoryResponse,
)
async def get_page_memory(
    volume_id: str,
    filename: str,
) -> PageMemoryResponse:
    return PageMemoryResponse(**get_page_memory_payload(volume_id, filename))


@router.delete(
    "/volumes/{volume_id}/memory",
    response_model=ClearMemoryResponse,
)
async def clear_volume_memory(volume_id: str) -> ClearMemoryResponse:
    clear_volume_memory_data(volume_id)
    return ClearMemoryResponse(cleared=True)


@router.delete(
    "/volumes/{volume_id}/pages/{filename}/memory",
    response_model=ClearMemoryResponse,
)
async def clear_page_memory(
    volume_id: str,
    filename: str,
) -> ClearMemoryResponse:
    clear_page_memory_data(volume_id, filename)
    return ClearMemoryResponse(cleared=True)


@router.delete(
    "/volumes/{volume_id}/derived-data",
    response_model=ClearVolumeDerivedDataResponse,
)
async def clear_volume_derived_state(
    volume_id: str,
) -> ClearVolumeDerivedDataResponse:
    return ClearVolumeDerivedDataResponse(**clear_volume_derived_state_payload(volume_id))
