# backend-python/api/routers/ocr.py
from core.usecases.ocr.profiles import list_ocr_profiles_for_api
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["ocr"])


class OcrProvider(BaseModel):
    id: str
    label: str
    description: str | None = None
    kind: str = "local"
    enabled: bool = True


@router.get("/ocr/providers", response_model=list[OcrProvider])
async def list_ocr_providers():
    """
    Returns the list of configured OCR profiles.
    The data comes from core/usecases/ocr/profiles.py.
    """
    providers_raw = list_ocr_profiles_for_api()
    return [OcrProvider(**p) for p in providers_raw]

