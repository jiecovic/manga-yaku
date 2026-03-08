# backend-python/core/usecases/translation/profiles/catalog.py
"""Static translation profile definitions and runtime availability toggles."""

from __future__ import annotations

import os
from typing import Any, TypedDict


class TranslationProfile(TypedDict, total=False):
    """Static configuration for a translation provider/profile."""

    id: str
    label: str
    description: str
    provider: str
    kind: str
    enabled: bool
    config: dict[str, Any]


TRANSLATION_PROFILES: dict[str, TranslationProfile] = {
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
            "prompt_file": "translation/single_box/fast.yml",
        },
    },
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
            "prompt_file": "translation/single_box/quality.yml",
        },
    },
    "openai_ultra_translate": {
        "id": "openai_ultra_translate",
        "label": "Single-box Translate - Max",
        "description": "Max-quality single-box translation via OpenAI",
        "provider": "openai_chat",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-5.1",
            "max_completion_tokens": 1024,
            "temperature": 0.15,
            "prompt_file": "translation/single_box/ultra.yml",
        },
    },
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
            "prompt_file": "translation/single_box/local.yml",
        },
    },
}


def mark_translation_availability(
    *,
    has_cloud_openai: bool,
    has_local_openai: bool,
) -> None:
    """Update runtime availability flags for translation profiles."""
    for key in (
        "openai_fast_translate",
        "openai_quality_translate",
        "openai_ultra_translate",
    ):
        if key in TRANSLATION_PROFILES:
            TRANSLATION_PROFILES[key]["enabled"] = has_cloud_openai

    if "local_llm_default" in TRANSLATION_PROFILES:
        TRANSLATION_PROFILES["local_llm_default"]["enabled"] = has_local_openai
