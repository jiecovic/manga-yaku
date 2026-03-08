# backend-python/core/usecases/translation/profiles/registry.py
"""Effective translation profile lookups and API views."""

from __future__ import annotations

from typing import Any, cast

from .catalog import TRANSLATION_PROFILES, TranslationProfile
from .settings import (
    list_translation_profiles_with_settings,
    resolve_translation_profile_settings,
)


def list_translation_profiles_for_api() -> list[dict[str, Any]]:
    """Lightweight view for the API / frontend."""
    profiles = list_translation_profiles_with_settings()
    return [
        {
            "id": profile.id,
            "label": profile.label,
            "description": profile.description,
            "kind": profile.kind,
            "enabled": profile.effective_enabled,
            "single_box_enabled": profile.single_box_enabled,
        }
        for profile in profiles
    ]


def get_translation_profile(profile_id: str) -> TranslationProfile:
    """Strict lookup with a nice error instead of KeyError."""
    try:
        base = TRANSLATION_PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"Translation profile '{profile_id}' not found") from exc

    profile = cast(TranslationProfile, dict(base))
    cfg = dict(profile.get("config", {}) or {})

    profile_settings = resolve_translation_profile_settings()[profile_id]
    runtime_enabled = bool(profile.get("enabled", True))
    single_box_enabled = profile_settings.single_box_enabled
    profile["enabled"] = runtime_enabled and single_box_enabled
    profile["config"] = profile_settings.model_settings().apply_to_config(
        cfg,
        token_key="max_output_tokens",
    )
    return profile
