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
import unittest
from unittest.mock import patch

from api.routers.ocr.routes import list_ocr_providers
from core.usecases.ocr.profiles import OCR_PROFILES


def _profiles_snapshot_from_registry() -> list[dict]:
    snapshot: list[dict] = []
    for profile_id, profile in OCR_PROFILES.items():
        snapshot.append(
            {
                "id": profile.get("id", profile_id),
                "label": profile.get("label", profile_id),
                "description": profile.get("description", ""),
                "kind": profile.get("kind", "local"),
                "enabled": bool(profile.get("enabled", True)),
                "agent_enabled": True,
                "model_id": None,
                "max_output_tokens": None,
                "reasoning_effort": None,
                "temperature": None,
            }
        )
    return snapshot


class OcrProvidersTests(unittest.TestCase):
    def test_unavailable_manga_ocr_is_hidden_from_provider_list(self) -> None:
        original_manga_enabled = bool(
            OCR_PROFILES.get("manga_ocr_default", {}).get("enabled", True)
        )
        original_fast_enabled = bool(
            OCR_PROFILES.get("openai_fast_ocr", {}).get("enabled", True)
        )
        original_quality_enabled = bool(
            OCR_PROFILES.get("openai_quality_ocr", {}).get("enabled", True)
        )
        original_ultra_enabled = bool(
            OCR_PROFILES.get("openai_ultra_ocr", {}).get("enabled", True)
        )

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
                    "core.usecases.ocr.initialize_ocr_runtime",
                    side_effect=_simulate_runtime_probe,
                ),
                patch(
                    "core.usecases.ocr.profile_settings.list_ocr_profiles_with_settings",
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
        self.assertNotIn("manga_ocr_default", ids)
        self.assertIn("openai_fast_ocr", ids)
