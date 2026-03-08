# backend-python/tests/core/usecases/ocr/test_ocr_providers.py
"""Regression tests for OCR provider availability exposure.

What is tested:
- Runtime capability initialization marks unavailable providers as disabled.
- API-facing provider list excludes disabled/unavailable providers.

How it is tested:
- Registry snapshots are exercised with patched runtime checks.
- Router handler is called directly to verify final API-visible payloads.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from api.routers.ocr.routes import list_ocr_providers
from core.usecases.ocr.profiles.registry import OCR_PROFILES
from core.usecases.settings.models import OcrProfileSettingsView


def _profiles_snapshot_from_registry() -> list[OcrProfileSettingsView]:
    snapshot: list[OcrProfileSettingsView] = []
    for profile_id, profile in OCR_PROFILES.items():
        snapshot.append(
            OcrProfileSettingsView(
                id=str(profile.get("id", profile_id)),
                label=str(profile.get("label", profile_id) or profile_id),
                description=str(profile.get("description", "")),
                kind=str(profile.get("kind", "local")),
                enabled=bool(profile.get("enabled", True)),
                page_translation_enabled=True,
                model_id=None,
                max_output_tokens=None,
                reasoning_effort=None,
                temperature=None,
            )
        )
    return snapshot


def test_unavailable_manga_ocr_is_hidden_from_provider_list() -> None:
    original_manga_enabled = bool(OCR_PROFILES.get("manga_ocr_default", {}).get("enabled", True))
    original_fast_enabled = bool(OCR_PROFILES.get("openai_fast_ocr", {}).get("enabled", True))
    original_quality_enabled = bool(OCR_PROFILES.get("openai_quality_ocr", {}).get("enabled", True))
    original_ultra_enabled = bool(OCR_PROFILES.get("openai_ultra_ocr", {}).get("enabled", True))

    try:
        OCR_PROFILES["manga_ocr_default"]["enabled"] = True
        OCR_PROFILES["openai_fast_ocr"]["enabled"] = True
        OCR_PROFILES["openai_quality_ocr"]["enabled"] = True
        OCR_PROFILES["openai_ultra_ocr"]["enabled"] = True

        def _simulate_runtime_probe() -> None:
            OCR_PROFILES["manga_ocr_default"]["enabled"] = False
            OCR_PROFILES["openai_fast_ocr"]["enabled"] = True
            OCR_PROFILES["openai_quality_ocr"]["enabled"] = True
            OCR_PROFILES["openai_ultra_ocr"]["enabled"] = True

        with (
            patch(
                "core.usecases.ocr.profiles.registry.initialize_ocr_runtime",
                side_effect=_simulate_runtime_probe,
            ),
            patch(
                "core.usecases.ocr.profiles.registry.list_ocr_profiles_with_settings",
                side_effect=_profiles_snapshot_from_registry,
            ),
        ):
            providers = asyncio.run(list_ocr_providers())
    finally:
        OCR_PROFILES["manga_ocr_default"]["enabled"] = original_manga_enabled
        OCR_PROFILES["openai_fast_ocr"]["enabled"] = original_fast_enabled
        OCR_PROFILES["openai_quality_ocr"]["enabled"] = original_quality_enabled
        OCR_PROFILES["openai_ultra_ocr"]["enabled"] = original_ultra_enabled

    ids = [provider.id for provider in providers]
    assert "manga_ocr_default" not in ids
    assert "openai_fast_ocr" in ids
