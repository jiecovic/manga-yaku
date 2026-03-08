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
            "prompt_file": "ocr/single_box/default.yml",
        },
    },
    "openai_fast_ocr": {
        "id": "openai_fast_ocr",
        "label": "LLM OCR (fast)",
        "description": "Fast LLM OCR",
        "llm_hint": ("Fast; ok for simple bubbles."),
        "provider": "llm_ocr",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-5-mini",
            "max_tokens": 256,
            "temperature": 0.0,
            "prompt_file": "ocr/single_box/default.yml",
        },
    },
    "openai_quality_ocr": {
        "id": "openai_quality_ocr",
        "label": "LLM OCR (quality)",
        "description": "Higher-accuracy LLM OCR",
        "llm_hint": ("More accurate; slower/costlier."),
        "provider": "llm_ocr",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-5.2",
            "max_tokens": 512,
            "temperature": 0.0,
            "prompt_file": "ocr/single_box/default.yml",
        },
    },
    "openai_ultra_ocr": {
        "id": "openai_ultra_ocr",
        "label": "LLM OCR (ultra)",
        "description": "Highest-accuracy LLM OCR",
        "llm_hint": ("Best accuracy; highest cost."),
        "provider": "llm_ocr",
        "kind": "remote",
        "enabled": True,
        "config": {
            "model": "gpt-5.2-pro",
            "max_completion_tokens": 512,
            "temperature": 0.0,
            "prompt_file": "ocr/single_box/default.yml",
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
    return [profile.to_payload() for profile in profiles if profile.enabled]


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
    if provider == "llm_ocr":
        from .profile_settings import resolve_ocr_profile_settings

        profile_settings = resolve_ocr_profile_settings()[profile_id]
        cfg = profile_settings.model_settings().apply_to_config(
            dict(profile.get("config", {}) or {}),
            token_key="max_tokens",
        )
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
