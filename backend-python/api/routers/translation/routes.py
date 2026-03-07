# backend-python/api/routers/translation/routes.py
"""HTTP routes for translation endpoints."""

from api.schemas.providers import TranslationProvider
from core.usecases.translation.profiles import list_translation_profiles_for_api
from fastapi import APIRouter

router = APIRouter(tags=["translation"])


@router.get("/translation/providers", response_model=list[TranslationProvider])
async def get_translation_providers() -> list[TranslationProvider]:
    """Return translation providers."""
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
