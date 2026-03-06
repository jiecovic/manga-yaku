# backend-python/api/routers/volumes/memory.py
"""HTTP routes for volume and page memory state management."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.volumes import (
    ClearMemoryResponse,
    ClearVolumeDerivedDataResponse,
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

router = APIRouter(tags=["library"])


@router.get(
    "/volumes/{volume_id}/memory",
    response_model=VolumeMemoryResponse,
)
async def get_volume_memory(volume_id: str) -> VolumeMemoryResponse:
    """Return volume memory."""
    return VolumeMemoryResponse(**get_volume_memory_payload(volume_id))


@router.get(
    "/volumes/{volume_id}/pages/{filename}/memory",
    response_model=PageMemoryResponse,
)
async def get_page_memory(
    volume_id: str,
    filename: str,
) -> PageMemoryResponse:
    """Return page memory."""
    return PageMemoryResponse(**get_page_memory_payload(volume_id, filename))


@router.delete(
    "/volumes/{volume_id}/memory",
    response_model=ClearMemoryResponse,
)
async def clear_volume_memory(volume_id: str) -> ClearMemoryResponse:
    """Clear volume memory."""
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
    """Clear page memory."""
    clear_page_memory_data(volume_id, filename)
    return ClearMemoryResponse(cleared=True)


@router.delete(
    "/volumes/{volume_id}/derived-data",
    response_model=ClearVolumeDerivedDataResponse,
)
async def clear_volume_derived_state(
    volume_id: str,
) -> ClearVolumeDerivedDataResponse:
    """Clear volume derived state."""
    return ClearVolumeDerivedDataResponse(**clear_volume_derived_state_payload(volume_id))
