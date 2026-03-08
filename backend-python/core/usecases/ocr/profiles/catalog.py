# backend-python/core/usecases/ocr/profiles/catalog.py
"""Static OCR profile definitions and runtime availability toggles."""

from __future__ import annotations

from typing import Any, TypedDict


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
        "llm_hint": "Fast; ok for simple bubbles.",
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
        "llm_hint": "More accurate; slower/costlier.",
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
        "llm_hint": "Best accuracy; highest cost.",
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


def mark_ocr_availability(*, has_manga_ocr: bool, has_llm_ocr: bool) -> None:
    """Update runtime availability flags for OCR profiles."""
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
