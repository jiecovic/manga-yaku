# backend-python/core/usecases/ocr/profile_settings.py
from __future__ import annotations

from typing import Any

from core.usecases.settings.service import resolve_ocr_label_overrides
from infra.db.ocr_profile_settings_store import (
    list_ocr_profile_settings,
    upsert_ocr_profile_setting,
)

from .profiles import OCR_PROFILES, OcrProfile

REASONING_CHOICES = ("low", "medium", "high")


def _default_profile_settings(profile: OcrProfile) -> dict[str, Any]:
    cfg = profile.get("config", {}) or {}
    return {
        "agent_enabled": True,
        "model_id": cfg.get("model"),
        "max_output_tokens": cfg.get("max_tokens") or cfg.get("max_completion_tokens"),
        "reasoning_effort": None,
        "temperature": cfg.get("temperature"),
    }


def resolve_ocr_profile_settings() -> dict[str, dict[str, Any]]:
    stored = list_ocr_profile_settings()
    resolved: dict[str, dict[str, Any]] = {}
    for pid, profile in OCR_PROFILES.items():
        defaults = _default_profile_settings(profile)
        current = dict(defaults)
        current.update({k: v for k, v in stored.get(pid, {}).items() if v is not None})
        if "agent_enabled" in stored.get(pid, {}):
            current["agent_enabled"] = bool(stored[pid]["agent_enabled"])
        resolved[pid] = current
    return resolved


def list_ocr_profiles_with_settings() -> list[dict[str, Any]]:
    settings = resolve_ocr_profile_settings()
    label_overrides = resolve_ocr_label_overrides().values
    results: list[dict[str, Any]] = []
    for pid, profile in OCR_PROFILES.items():
        cfg = profile.get("config", {}) or {}
        current = settings.get(pid, {})
        results.append(
            {
                "id": profile.get("id", pid),
                "label": label_overrides.get(pid) or profile.get("label", pid),
                "description": profile.get("description", ""),
                "kind": profile.get("kind", "local"),
                "enabled": bool(profile.get("enabled", True)),
                "agent_enabled": bool(current.get("agent_enabled", True)),
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


def update_ocr_profile_settings(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        if "agent_enabled" in update:
            current["agent_enabled"] = bool(update["agent_enabled"])

        profile = OCR_PROFILES[profile_id]
        is_remote = profile.get("kind") != "local"

        if is_remote:
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
        else:
            current["model_id"] = None
            current["max_output_tokens"] = None
            current["reasoning_effort"] = None
            current["temperature"] = None

    available_profiles = [
        pid
        for pid, profile in OCR_PROFILES.items()
        if profile.get("enabled", True)
    ]
    if available_profiles:
        enabled = [
            pid
            for pid in available_profiles
            if resolved.get(pid, {}).get("agent_enabled")
        ]
        if not enabled:
            raise ValueError("At least one OCR profile must be enabled for the agent.")

    for pid, settings in resolved.items():
        upsert_ocr_profile_setting(
            pid,
            {
                "agent_enabled": settings.get("agent_enabled", True),
                "model_id": settings.get("model_id"),
                "max_output_tokens": settings.get("max_output_tokens"),
                "reasoning_effort": settings.get("reasoning_effort"),
                "temperature": settings.get("temperature"),
            },
        )

    return list_ocr_profiles_with_settings()


def agent_enabled_ocr_profiles() -> list[str]:
    settings = resolve_ocr_profile_settings()
    profile_ids: list[str] = []
    for pid, profile in OCR_PROFILES.items():
        if not profile.get("enabled", True):
            continue
        if settings.get(pid, {}).get("agent_enabled", True):
            profile_ids.append(pid)
    return profile_ids
