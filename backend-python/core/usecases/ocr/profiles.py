# backend-python/core/usecases/ocr/profiles.py
"""Default profile definitions for ocr providers."""

from __future__ import annotations

from typing import Any, TypedDict, cast

from core.usecases.settings.service import resolve_ocr_label_overrides


class OcrProfile(TypedDict, total=False):
    id: str
    label: str
    description: str
    provider: str
    kind: str
    enabled: bool
    llm_hint: str
    config: dict[str, Any]


OCR_PROFILES: dict[str, OcrProfile] = {
    "manga_ocr_default": {
        "id": "manga_ocr_default",
        "label": "manga-ocr (default)",
        "description": "Local manga-ocr on cropped region",
        "llm_hint": (
            "Fast local; best on clean print. Weaker at empty-crop detection and can "
            "emit short false positives on noisy crops."
        ),
        "provider": "manga_ocr",
        "kind": "local",
        "enabled": True,
        "config": {
            "prompt_file": "ocr_default.yml",
        },
    },

    "openai_fast_ocr": {
        "id": "openai_fast_ocr",
        "label": "LLM OCR (fast)",
        "description": "Fast LLM OCR",
        "llm_hint": (
            "Fast; ok for simple bubbles."
        ),
        "provider": "llm_ocr",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-5-mini",
            "max_tokens": 256,
            "temperature": 0.0,
            "prompt_file": "ocr_default.yml",
        },
    },

    "openai_quality_ocr": {
        "id": "openai_quality_ocr",
        "label": "LLM OCR (quality)",
        "description": "Higher-accuracy LLM OCR",
        "llm_hint": (
            "More accurate; slower/costlier."
        ),
        "provider": "llm_ocr",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-5.2",
            "max_tokens": 512,
            "temperature": 0.0,
            "prompt_file": "ocr_default.yml",
        },
    },

    "openai_ultra_ocr": {
        "id": "openai_ultra_ocr",
        "label": "LLM OCR (ultra)",
        "description": "Highest-accuracy LLM OCR",
        "llm_hint": (
            "Best accuracy; highest cost."
        ),
        "provider": "llm_ocr",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-5.2-pro",
            "max_completion_tokens": 512,
            "temperature": 0.0,
            "prompt_file": "ocr_default.yml",
        },
    },
}


def list_ocr_profiles_for_api() -> list[dict[str, Any]]:
    # Refresh runtime capability flags (manga-ocr import/init, OpenAI key state)
    # before exposing profile availability to API consumers.
    from . import initialize_ocr_runtime
    from .profile_settings import list_ocr_profiles_with_settings

    initialize_ocr_runtime()
    profiles = list_ocr_profiles_with_settings()
    return [profile for profile in profiles if bool(profile.get("enabled", True))]


def get_ocr_profile(profile_id: str) -> OcrProfile:
    """Lookup with a nice error instead of KeyError."""
    from . import initialize_ocr_runtime

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
    # Keep legacy provider id support for older in-memory/profile variants.
    if provider in {"llm_ocr", "llm_ocr_chat"}:
        from .profile_settings import resolve_ocr_profile_settings

        profile_settings = resolve_ocr_profile_settings().get(profile_id, {})
        cfg = dict(profile.get("config", {}) or {})
        model_id = profile_settings.get("model_id")
        if model_id:
            cfg["model"] = model_id
        max_output_tokens = profile_settings.get("max_output_tokens")
        if max_output_tokens is not None:
            cfg["max_tokens"] = max_output_tokens
        temperature = profile_settings.get("temperature")
        if temperature is not None:
            cfg["temperature"] = temperature
        reasoning_effort = profile_settings.get("reasoning_effort")
        if reasoning_effort and str(cfg.get("model", "")).startswith("gpt-5"):
            cfg["reasoning"] = {"effort": reasoning_effort}
        profile["config"] = cfg
    return profile


def mark_ocr_availability(*, has_manga_ocr: bool, has_llm_ocr: bool) -> None:
    """
    Called by the engine at import/startup to toggle 'enabled' flags
    based on runtime capabilities.
    """
    if "manga_ocr_default" in OCR_PROFILES:
        OCR_PROFILES["manga_ocr_default"]["enabled"] = has_manga_ocr

    if has_llm_ocr:
        for key in ("openai_fast_ocr", "openai_quality_ocr", "openai_ultra_ocr"):
            if key in OCR_PROFILES:
                OCR_PROFILES[key]["enabled"] = True
    else:
        for key in ("openai_fast_ocr", "openai_quality_ocr", "openai_ultra_ocr"):
            if key in OCR_PROFILES:
                OCR_PROFILES[key]["enabled"] = False
