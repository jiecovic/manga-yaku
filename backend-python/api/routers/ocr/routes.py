# backend-python/api/routers/ocr/routes.py
"""HTTP routes for ocr endpoints."""

from api.schemas.providers import OcrProvider
from core.usecases.ocr.profiles import list_ocr_profiles_for_api
from fastapi import APIRouter

router = APIRouter(tags=["ocr"])


@router.get("/ocr/providers", response_model=list[OcrProvider])
async def list_ocr_providers():
    """
    Returns the list of configured OCR profiles.
    The data comes from core/usecases/ocr/profiles.py.
    """
    providers_raw = list_ocr_profiles_for_api()
    return [OcrProvider(**p) for p in providers_raw]
