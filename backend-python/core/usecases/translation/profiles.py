# backend-python/core/usecases/translation/profiles.py
from __future__ import annotations

import os
from typing import Any, TypedDict


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
        "label": "OpenAI (fast, JA->EN)",
        "description": "Fast translation via OpenAI chat model",
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
        "label": "OpenAI (quality, JA->EN)",
        "description": "High-quality translation using GPT-4.1-mini",
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
        "label": "OpenAI (ultra quality, JA->EN)",
        "description": "Highest-quality translation using GPT-5.1",
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
        "label": "Local LLM (OpenAI-compatible)",
        "description": (
            "Translation via a local OpenAI-compatible HTTP endpoint "
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
    return [
        {
            "id": profile.get("id", pid),
            "label": profile.get("label", pid),
            "description": profile.get("description", ""),
            "kind": profile.get("kind", "remote"),
            "enabled": profile.get("enabled", True),
        }
        for pid, profile in TRANSLATION_PROFILES.items()
    ]


def get_translation_profile(profile_id: str) -> TranslationProfile:
    """Strict lookup with a nice error instead of KeyError."""
    try:
        return TRANSLATION_PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"Translation profile '{profile_id}' not found") from exc


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
