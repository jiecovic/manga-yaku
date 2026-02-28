# backend-python/core/usecases/translation/profiles.py
"""Default profile definitions for translation providers."""

from __future__ import annotations

import os
from typing import Any, TypedDict, cast


class TranslationProfile(TypedDict, total=False):
    """Static configuration for a translation provider/profile."""
    id: str
    label: str
    description: str
    provider: str  # e.g. "openai_chat"
    kind: str  # "local" | "remote"
    enabled: bool
    config: dict[str, Any]


# Registry of all translation profiles.
TRANSLATION_PROFILES: dict[str, TranslationProfile] = {
    # ------------------------------------------------------------------
    # OpenAI Fast
    # ------------------------------------------------------------------
    "openai_fast_translate": {
        "id": "openai_fast_translate",
        "label": "Single-box Translate - Fast",
        "description": "Fast single-box translation via OpenAI",
        "provider": "openai_chat",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-4o-mini",
            "max_tokens": 256,
            "temperature": 0.2,
            "prompt_file": "translation_fast.yml",
        },
    },

    # ------------------------------------------------------------------
    # OpenAI Quality
    # ------------------------------------------------------------------
    "openai_quality_translate": {
        "id": "openai_quality_translate",
        "label": "Single-box Translate - Quality",
        "description": "Higher-quality single-box translation via OpenAI",
        "provider": "openai_chat",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-4.1-mini",
            "max_tokens": 512,
            "temperature": 0.2,
            "prompt_file": "translation_quality.yml",
        },
    },

    # ------------------------------------------------------------------
    # OpenAI Ultra - GPT-5.1
    # ------------------------------------------------------------------
    "openai_ultra_translate": {
        "id": "openai_ultra_translate",
        "label": "Single-box Translate - Max",
        "description": "Max-quality single-box translation via OpenAI",
        "provider": "openai_chat",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-5.1",  # or "gpt-5.1-preview"
            "max_completion_tokens": 1024,
            "temperature": 0.15,
            "prompt_file": "translation_ultra.yml",
        },
    },

    # ------------------------------------------------------------------
    # Local LLM - OpenAI-compatible endpoint
    # ------------------------------------------------------------------
    "local_llm_default": {
        "id": "local_llm_default",
        "label": "Single-box Translate - Local",
        "description": (
            "Single-box translation via a local OpenAI-compatible HTTP endpoint "
            "(e.g. TextGen WebUI / LM Studio / llama.cpp server)"
        ),
        "provider": "openai_chat",
        "kind": "local",
        "enabled": True,
        "config": {
            "base_url": os.getenv("LOCAL_OPENAI_BASE_URL", ""),
            "model": os.getenv("LOCAL_OPENAI_MODEL", "local-model"),
            "max_tokens": 512,
            "temperature": 0.3,
            "prompt_file": "translation_local.yml",
        },
    },
}


# ----------------------------------------------------------------------
# Public helpers
# ----------------------------------------------------------------------

def list_translation_profiles_for_api() -> list[dict[str, Any]]:
    """Lightweight view for the API / frontend."""
    from .profile_settings import list_translation_profiles_with_settings

    profiles = list_translation_profiles_with_settings()
    return [
        {
            "id": str(profile.get("id") or ""),
            "label": str(profile.get("label") or ""),
            "description": str(profile.get("description") or ""),
            "kind": str(profile.get("kind") or "remote"),
            "enabled": bool(
                profile.get("effective_enabled", profile.get("enabled", True))
            ),
            "single_box_enabled": bool(profile.get("single_box_enabled", True)),
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

    from .profile_settings import resolve_translation_profile_settings

    profile_settings = resolve_translation_profile_settings().get(profile_id, {})
    runtime_enabled = bool(profile.get("enabled", True))
    single_box_enabled = bool(profile_settings.get("single_box_enabled", True))
    profile["enabled"] = runtime_enabled and single_box_enabled

    model_id = profile_settings.get("model_id")
    if model_id:
        cfg["model"] = str(model_id)

    max_output_tokens = profile_settings.get("max_output_tokens")
    if max_output_tokens is not None:
        cfg["max_output_tokens"] = int(max_output_tokens)

    temperature = profile_settings.get("temperature")
    if temperature is not None:
        cfg["temperature"] = float(temperature)

    reasoning_effort = profile_settings.get("reasoning_effort")
    if reasoning_effort and str(cfg.get("model", "")).startswith("gpt-5"):
        cfg["reasoning"] = {"effort": str(reasoning_effort)}

    profile["config"] = cfg
    return profile


def mark_translation_availability(
        *,
        has_cloud_openai: bool,
        has_local_openai: bool,
) -> None:
    """
    Called by the translation engine at import/startup to toggle 'enabled'
    flags based on runtime capabilities (OpenAI SDK, API key, local endpoint).
    """
    # Cloud OpenAI-backed profiles
    for key in (
            "openai_fast_translate",
            "openai_quality_translate",
            "openai_ultra_translate",
    ):
        if key in TRANSLATION_PROFILES:
            TRANSLATION_PROFILES[key]["enabled"] = has_cloud_openai

    # Local OpenAI-compatible profile
    if "local_llm_default" in TRANSLATION_PROFILES:
        TRANSLATION_PROFILES["local_llm_default"]["enabled"] = has_local_openai
