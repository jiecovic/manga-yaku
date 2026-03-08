# backend-python/core/workflows/page_translation/orchestration/resolution.py
"""Profile and parallelism resolution for the page-translation workflow."""

from __future__ import annotations

from typing import Any

from core.usecases.ocr.profiles.registry import get_ocr_profile
from core.usecases.ocr.profiles.settings import page_translation_enabled_ocr_profiles
from core.usecases.settings.service import (
    resolve_detection_settings,
    resolve_ocr_parallelism_settings,
)


def resolve_detection_profile_id(preferred_profile_id: str | None) -> str | None:
    """Resolve the detection profile id for a page-translation run."""
    if preferred_profile_id:
        return preferred_profile_id
    stored_profile_id = resolve_detection_settings().page_translation_detection_profile_id
    if stored_profile_id:
        return stored_profile_id
    return None


def resolve_ocr_profiles(payload: dict[str, Any]) -> list[str]:
    """Resolve enabled OCR profiles for a page-translation run."""
    raw = payload.get("ocrProfiles")
    requested = [str(item).strip() for item in raw or [] if str(item).strip()]
    profile_ids = requested or page_translation_enabled_ocr_profiles()
    if not profile_ids:
        profile_ids = ["manga_ocr_default"]

    resolved: list[str] = []
    seen: set[str] = set()
    for profile_id in profile_ids:
        if profile_id in seen:
            continue
        seen.add(profile_id)
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        if not profile.get("enabled", True):
            continue
        resolved.append(profile_id)

    if not resolved:
        try:
            fallback = get_ocr_profile("manga_ocr_default")
            if fallback.get("enabled", True):
                resolved = ["manga_ocr_default"]
        except Exception:
            pass

    if not resolved:
        raise RuntimeError("No enabled OCR profiles configured")

    return resolved


def resolve_parallel_limits() -> tuple[int, int]:
    """Resolve OCR parallelism limits for page-translation fanout."""
    settings = resolve_ocr_parallelism_settings()
    return (settings.local, settings.remote)
