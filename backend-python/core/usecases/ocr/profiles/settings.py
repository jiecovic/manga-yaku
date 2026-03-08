# backend-python/core/usecases/ocr/profiles/settings.py
"""Settings overlay and persistence mapping for OCR profiles."""

from __future__ import annotations

from typing import Any

from core.usecases.settings.models import (
    ModelRuntimeSettings,
    OcrProfileRuntimeSettings,
    OcrProfileSettingsView,
)
from core.usecases.settings.runtime_validation import (
    apply_model_runtime_patch,
    default_model_runtime_settings,
)
from core.usecases.settings.service import resolve_ocr_label_overrides
from infra.db.ocr_profile_settings_store import (
    list_ocr_profile_settings,
    upsert_ocr_profile_setting,
)

from .catalog import OCR_PROFILES, OcrProfile


def _default_profile_settings(profile: OcrProfile) -> OcrProfileRuntimeSettings:
    cfg = profile.get("config", {}) or {}
    defaults = default_model_runtime_settings(cfg)
    return OcrProfileRuntimeSettings.from_model_settings(
        defaults,
        page_translation_enabled=True,
    )


def _resolve_profile_settings(
    profile: OcrProfile,
    stored_values: dict[str, Any],
) -> OcrProfileRuntimeSettings:
    current = _default_profile_settings(profile)
    page_translation_enabled = current.page_translation_enabled
    if "page_translation_enabled" in stored_values:
        page_translation_enabled = bool(stored_values["page_translation_enabled"])

    is_remote = str(profile.get("kind") or "local") != "local"
    if is_remote:
        current_runtime = apply_model_runtime_patch(
            current.model_settings(),
            stored_values,
            require_model_id=False,
            min_max_output_tokens=1,
        )
    else:
        current_runtime = ModelRuntimeSettings.empty()

    return OcrProfileRuntimeSettings.from_model_settings(
        current_runtime,
        page_translation_enabled=page_translation_enabled,
    )


def resolve_ocr_profile_settings() -> dict[str, OcrProfileRuntimeSettings]:
    stored = list_ocr_profile_settings()
    resolved: dict[str, OcrProfileRuntimeSettings] = {}
    for pid, profile in OCR_PROFILES.items():
        resolved[pid] = _resolve_profile_settings(profile, stored.get(pid, {}))
    return resolved


def list_ocr_profiles_with_settings() -> list[OcrProfileSettingsView]:
    settings = resolve_ocr_profile_settings()
    label_overrides = resolve_ocr_label_overrides().values
    results: list[OcrProfileSettingsView] = []
    for pid, profile in OCR_PROFILES.items():
        current = settings[pid]
        results.append(
            OcrProfileSettingsView(
                id=str(profile.get("id", pid)),
                label=str(label_overrides.get(pid) or profile.get("label", pid) or pid),
                description=str(profile.get("description", "")),
                kind=str(profile.get("kind", "local")),
                enabled=bool(profile.get("enabled", True)),
                page_translation_enabled=current.page_translation_enabled,
                model_id=current.model_id,
                max_output_tokens=current.max_output_tokens,
                reasoning_effort=current.reasoning_effort,
                temperature=current.temperature,
            )
        )
    return results


def update_ocr_profile_settings(updates: list[dict[str, Any]]) -> list[OcrProfileSettingsView]:
    if not isinstance(updates, list):
        raise ValueError("profiles must be a list")

    resolved = resolve_ocr_profile_settings()
    for update in updates:
        if not isinstance(update, dict):
            raise ValueError("profile entry must be an object")
        profile_id = str(update.get("profile_id") or update.get("id") or "").strip()
        if not profile_id:
            raise ValueError("profile_id is required")
        if profile_id not in OCR_PROFILES:
            raise ValueError(f"Unknown OCR profile: {profile_id}")

        current = resolved[profile_id]
        page_translation_enabled = current.page_translation_enabled
        if "page_translation_enabled" in update:
            page_translation_enabled = bool(update["page_translation_enabled"])

        profile = OCR_PROFILES[profile_id]
        is_remote = str(profile.get("kind") or "local") != "local"

        if is_remote:
            current_runtime = apply_model_runtime_patch(
                current.model_settings(),
                update,
                require_model_id=False,
                min_max_output_tokens=1,
            )
        else:
            current_runtime = ModelRuntimeSettings.empty()

        resolved[profile_id] = OcrProfileRuntimeSettings.from_model_settings(
            current_runtime,
            page_translation_enabled=page_translation_enabled,
        )

    available_profiles = [
        pid for pid, profile in OCR_PROFILES.items() if profile.get("enabled", True)
    ]
    if available_profiles:
        enabled = [pid for pid in available_profiles if resolved[pid].page_translation_enabled]
        if not enabled:
            raise ValueError(
                "At least one OCR profile must be enabled for the page translation workflow."
            )

    for pid, settings in resolved.items():
        upsert_ocr_profile_setting(
            pid,
            {
                "page_translation_enabled": settings.page_translation_enabled,
                "model_id": settings.model_id,
                "max_output_tokens": settings.max_output_tokens,
                "reasoning_effort": settings.reasoning_effort,
                "temperature": settings.temperature,
            },
        )

    return list_ocr_profiles_with_settings()


def page_translation_enabled_ocr_profiles() -> list[str]:
    settings = resolve_ocr_profile_settings()
    profile_ids: list[str] = []
    for pid, profile in OCR_PROFILES.items():
        if not profile.get("enabled", True):
            continue
        if settings[pid].page_translation_enabled:
            profile_ids.append(pid)
    return profile_ids
