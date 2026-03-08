# backend-python/core/usecases/translation/profiles/settings.py
"""Settings overlay and persistence mapping for translation profiles."""

from __future__ import annotations

from typing import Any

from core.usecases.settings.models import (
    TranslationProfileRuntimeSettings,
    TranslationProfileSettingsView,
)
from core.usecases.settings.runtime_validation import (
    apply_model_runtime_patch,
    default_model_runtime_settings,
)
from infra.db.translation_profile_settings_store import (
    list_translation_profile_settings,
    upsert_translation_profile_setting,
)

from .catalog import TRANSLATION_PROFILES, TranslationProfile


def _default_profile_settings(profile: TranslationProfile) -> TranslationProfileRuntimeSettings:
    cfg = profile.get("config", {}) or {}
    defaults = default_model_runtime_settings(cfg)
    return TranslationProfileRuntimeSettings.from_model_settings(
        defaults,
        single_box_enabled=True,
    )


def _resolve_profile_settings(
    profile: TranslationProfile,
    stored_values: dict[str, Any],
) -> TranslationProfileRuntimeSettings:
    current = _default_profile_settings(profile)
    single_box_enabled = current.single_box_enabled
    if "single_box_enabled" in stored_values:
        single_box_enabled = bool(stored_values["single_box_enabled"])
    current_runtime = apply_model_runtime_patch(
        current.model_settings(),
        stored_values,
        require_model_id=False,
        min_max_output_tokens=1,
    )
    return TranslationProfileRuntimeSettings.from_model_settings(
        current_runtime,
        single_box_enabled=single_box_enabled,
    )


def resolve_translation_profile_settings() -> dict[str, TranslationProfileRuntimeSettings]:
    stored = list_translation_profile_settings()
    resolved: dict[str, TranslationProfileRuntimeSettings] = {}
    for pid, profile in TRANSLATION_PROFILES.items():
        resolved[pid] = _resolve_profile_settings(profile, stored.get(pid, {}))
    return resolved


def list_translation_profiles_with_settings() -> list[TranslationProfileSettingsView]:
    settings = resolve_translation_profile_settings()
    results: list[TranslationProfileSettingsView] = []
    for pid, profile in TRANSLATION_PROFILES.items():
        current = settings[pid]
        runtime_enabled = bool(profile.get("enabled", True))
        single_box_enabled = current.single_box_enabled
        results.append(
            TranslationProfileSettingsView(
                id=str(profile.get("id", pid)),
                label=str(profile.get("label", pid) or pid),
                description=str(profile.get("description", "")),
                kind=str(profile.get("kind", "remote")),
                enabled=runtime_enabled,
                single_box_enabled=single_box_enabled,
                effective_enabled=runtime_enabled and single_box_enabled,
                model_id=current.model_id,
                max_output_tokens=current.max_output_tokens,
                reasoning_effort=current.reasoning_effort,
                temperature=current.temperature,
            )
        )
    return results


def update_translation_profile_settings(
    updates: list[dict[str, Any]],
) -> list[TranslationProfileSettingsView]:
    if not isinstance(updates, list):
        raise ValueError("profiles must be a list")

    resolved = resolve_translation_profile_settings()
    for update in updates:
        if not isinstance(update, dict):
            raise ValueError("profile entry must be an object")
        profile_id = str(update.get("profile_id") or update.get("id") or "").strip()
        if not profile_id:
            raise ValueError("profile_id is required")
        if profile_id not in TRANSLATION_PROFILES:
            raise ValueError(f"Unknown translation profile: {profile_id}")

        current = resolved[profile_id]
        single_box_enabled = current.single_box_enabled
        if "single_box_enabled" in update:
            single_box_enabled = bool(update["single_box_enabled"])

        current_runtime = apply_model_runtime_patch(
            current.model_settings(),
            update,
            require_model_id=False,
            min_max_output_tokens=1,
        )
        resolved[profile_id] = TranslationProfileRuntimeSettings.from_model_settings(
            current_runtime,
            single_box_enabled=single_box_enabled,
        )

    available_profiles = [
        pid for pid, profile in TRANSLATION_PROFILES.items() if profile.get("enabled", True)
    ]
    if available_profiles:
        enabled = [pid for pid in available_profiles if resolved[pid].single_box_enabled]
        if not enabled:
            raise ValueError(
                "At least one available translation profile must be enabled for single-box translate."
            )

    for pid, settings in resolved.items():
        upsert_translation_profile_setting(
            pid,
            {
                "single_box_enabled": settings.single_box_enabled,
                "model_id": settings.model_id,
                "max_output_tokens": settings.max_output_tokens,
                "reasoning_effort": settings.reasoning_effort,
                "temperature": settings.temperature,
            },
        )

    return list_translation_profiles_with_settings()
