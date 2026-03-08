# backend-python/core/usecases/ocr/profiles/registry.py
"""Effective OCR profile lookups and API views."""

from __future__ import annotations

from typing import Any, cast

from core.usecases.settings.service import resolve_ocr_label_overrides

from ..runtime.bootstrap import initialize_ocr_runtime
from .catalog import OCR_PROFILES, OcrProfile
from .settings import list_ocr_profiles_with_settings, resolve_ocr_profile_settings


def list_ocr_profiles_for_api() -> list[dict[str, Any]]:
    initialize_ocr_runtime()
    profiles = list_ocr_profiles_with_settings()
    return [profile.to_payload() for profile in profiles if profile.enabled]


def get_ocr_profile(profile_id: str) -> OcrProfile:
    """Lookup with a nice error instead of KeyError."""
    initialize_ocr_runtime()
    try:
        base = OCR_PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"OCR profile '{profile_id}' not found") from exc

    label_overrides = resolve_ocr_label_overrides().values
    profile = cast(OcrProfile, dict(base))
    if profile_id in label_overrides:
        profile["label"] = str(label_overrides[profile_id])
    provider = base.get("provider")
    if provider == "llm_ocr":
        profile_settings = resolve_ocr_profile_settings()[profile_id]
        cfg = profile_settings.model_settings().apply_to_config(
            dict(profile.get("config", {}) or {}),
            token_key="max_tokens",
        )
        profile["config"] = cfg
    return profile
