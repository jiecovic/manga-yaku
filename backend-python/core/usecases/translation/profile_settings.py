from __future__ import annotations

from typing import Any

from infra.db.translation_profile_settings_store import (
    list_translation_profile_settings,
    upsert_translation_profile_setting,
)

from .profiles import TRANSLATION_PROFILES, TranslationProfile

REASONING_CHOICES = ("low", "medium", "high")


def _default_profile_settings(profile: TranslationProfile) -> dict[str, Any]:
    cfg = profile.get("config", {}) or {}
    return {
        "single_box_enabled": True,
        "model_id": cfg.get("model"),
        "max_output_tokens": cfg.get("max_tokens") or cfg.get("max_completion_tokens"),
        "reasoning_effort": None,
        "temperature": cfg.get("temperature"),
    }


def resolve_translation_profile_settings() -> dict[str, dict[str, Any]]:
    stored = list_translation_profile_settings()
    resolved: dict[str, dict[str, Any]] = {}
    for pid, profile in TRANSLATION_PROFILES.items():
        defaults = _default_profile_settings(profile)
        current = dict(defaults)
        current.update({k: v for k, v in stored.get(pid, {}).items() if v is not None})
        if "single_box_enabled" in stored.get(pid, {}):
            current["single_box_enabled"] = bool(stored[pid]["single_box_enabled"])
        resolved[pid] = current
    return resolved


def list_translation_profiles_with_settings() -> list[dict[str, Any]]:
    settings = resolve_translation_profile_settings()
    results: list[dict[str, Any]] = []
    for pid, profile in TRANSLATION_PROFILES.items():
        cfg = profile.get("config", {}) or {}
        current = settings.get(pid, {})
        runtime_enabled = bool(profile.get("enabled", True))
        single_box_enabled = bool(current.get("single_box_enabled", True))
        results.append(
            {
                "id": profile.get("id", pid),
                "label": profile.get("label", pid),
                "description": profile.get("description", ""),
                "kind": profile.get("kind", "remote"),
                "enabled": runtime_enabled,
                "single_box_enabled": single_box_enabled,
                "effective_enabled": runtime_enabled and single_box_enabled,
                "model_id": current.get("model_id") or cfg.get("model"),
                "max_output_tokens": current.get("max_output_tokens")
                if current.get("max_output_tokens") is not None
                else cfg.get("max_tokens") or cfg.get("max_completion_tokens"),
                "reasoning_effort": current.get("reasoning_effort"),
                "temperature": current.get("temperature")
                if current.get("temperature") is not None
                else cfg.get("temperature"),
            }
        )
    return results


def update_translation_profile_settings(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        if "single_box_enabled" in update:
            current["single_box_enabled"] = bool(update["single_box_enabled"])

        if "model_id" in update:
            model_id = update.get("model_id")
            current["model_id"] = str(model_id).strip() if model_id else None

        if "max_output_tokens" in update:
            max_output_tokens = update.get("max_output_tokens")
            if max_output_tokens is None or max_output_tokens == "":
                current["max_output_tokens"] = None
            else:
                try:
                    max_output_tokens = int(max_output_tokens)
                except (TypeError, ValueError):
                    raise ValueError("max_output_tokens must be an integer") from None
                if max_output_tokens < 1:
                    raise ValueError("max_output_tokens must be >= 1")
                current["max_output_tokens"] = max_output_tokens

        if "reasoning_effort" in update:
            effort = update.get("reasoning_effort")
            if effort is None or effort == "":
                current["reasoning_effort"] = None
            else:
                effort = str(effort).strip().lower()
                if effort not in REASONING_CHOICES:
                    raise ValueError(
                        f"reasoning_effort must be one of {REASONING_CHOICES}"
                    )
                current["reasoning_effort"] = effort

        if "temperature" in update:
            temperature = update.get("temperature")
            if temperature is None or temperature == "":
                current["temperature"] = None
            else:
                try:
                    temperature = float(temperature)
                except (TypeError, ValueError):
                    raise ValueError("temperature must be a number") from None
                if temperature < 0 or temperature > 2:
                    raise ValueError("temperature must be between 0 and 2")
                current["temperature"] = temperature

    available_profiles = [
        pid
        for pid, profile in TRANSLATION_PROFILES.items()
        if profile.get("enabled", True)
    ]
    if available_profiles:
        enabled = [
            pid
            for pid in available_profiles
            if resolved.get(pid, {}).get("single_box_enabled")
        ]
        if not enabled:
            raise ValueError(
                "At least one available translation profile must be enabled for single-box translate."
            )

    for pid, settings in resolved.items():
        upsert_translation_profile_setting(
            pid,
            {
                "single_box_enabled": settings.get("single_box_enabled", True),
                "model_id": settings.get("model_id"),
                "max_output_tokens": settings.get("max_output_tokens"),
                "reasoning_effort": settings.get("reasoning_effort"),
                "temperature": settings.get("temperature"),
            },
        )

    return list_translation_profiles_with_settings()
