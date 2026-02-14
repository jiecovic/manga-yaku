# backend-python/api/routers/translation.py

from core.usecases.translation.profiles import list_translation_profiles_for_api
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["translation"])


class TranslationProvider(BaseModel):
    id: str
    label: str
    description: str | None = None
    kind: str = "remote"
    enabled: bool = True


@router.get("/translation/providers", response_model=list[TranslationProvider])
async def get_translation_providers() -> list[TranslationProvider]:
    providers_raw = list_translation_profiles_for_api()
    return [
        TranslationProvider(
            id=p.get("id", ""),
            label=p.get("label", ""),
            description=p.get("description") or "",
            kind=p.get("kind", "remote"),
            enabled=bool(p.get("enabled", True)),
        )
        for p in providers_raw
    ]

