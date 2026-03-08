# backend-python/tests/core/usecases/test_runtime_settings_models.py
"""Regression tests for typed runtime settings usage in core usecases."""

from __future__ import annotations

from unittest.mock import patch

from config import (
    AGENT_MODEL,
    PAGE_TRANSLATION_REASONING_EFFORT,
)
from core.usecases.ocr.profiles.registry import OCR_PROFILES, get_ocr_profile
from core.usecases.ocr.profiles.settings import list_ocr_profiles_with_settings
from core.usecases.page_translation.settings import (
    resolve_page_translation_settings,
    update_page_translation_settings,
)
from core.usecases.settings.models import (
    OcrLabelOverrides,
    OcrProfileRuntimeSettings,
    OcrProfileSettingsView,
    PageTranslationRuntimeSettings,
    TranslationProfileRuntimeSettings,
)
from core.usecases.translation.profile_settings import resolve_translation_profile_settings
from core.usecases.translation.profiles import get_translation_profile


def test_resolve_page_translation_settings_returns_typed_settings() -> None:
    with patch(
        "core.usecases.page_translation.settings.get_page_translation_settings",
        return_value={"max_output_tokens": 1536, "temperature": 0.4},
    ):
        settings = resolve_page_translation_settings()

    assert isinstance(settings, PageTranslationRuntimeSettings)
    assert settings.model_id == AGENT_MODEL
    assert settings.max_output_tokens == 1536
    assert settings.reasoning_effort == PAGE_TRANSLATION_REASONING_EFFORT
    assert settings.temperature == 0.4


def test_update_page_translation_settings_validates_once_and_persists_payload() -> None:
    with (
        patch(
            "core.usecases.page_translation.settings.get_page_translation_settings",
            side_effect=[
                {},
                {
                    "max_output_tokens": 2048,
                    "temperature": 0.6,
                },
            ],
        ),
        patch("core.usecases.page_translation.settings.upsert_page_translation_settings") as upsert,
    ):
        settings = update_page_translation_settings(
            {
                "max_output_tokens": 2048,
                "temperature": 0.6,
            }
        )

    upsert.assert_called_once_with(
        {
            "model_id": AGENT_MODEL,
            "max_output_tokens": 2048,
            "reasoning_effort": PAGE_TRANSLATION_REASONING_EFFORT,
            "temperature": 0.6,
        }
    )
    assert settings.max_output_tokens == 2048
    assert settings.temperature == 0.6


def test_get_ocr_profile_applies_typed_runtime_settings_to_config() -> None:
    runtime_settings = {
        "openai_quality_ocr": OcrProfileRuntimeSettings(
            model_id="gpt-5.2",
            max_output_tokens=999,
            reasoning_effort="high",
            temperature=0.1,
            page_translation_enabled=True,
        )
    }
    with (
        patch(
            "core.usecases.ocr.profiles.settings.resolve_ocr_profile_settings",
            return_value=runtime_settings,
        ),
        patch(
            "core.usecases.ocr.profiles.registry.resolve_ocr_label_overrides",
            return_value=OcrLabelOverrides(values={}),
        ),
        patch(
            "core.usecases.ocr.runtime.engine.initialize_ocr_runtime",
        ),
    ):
        profile = get_ocr_profile("openai_quality_ocr")

    cfg = dict(profile.get("config", {}) or {})
    assert cfg["model"] == "gpt-5.2"
    assert cfg["max_tokens"] == 999
    assert "temperature" not in cfg
    assert cfg["reasoning"] == {"effort": "high"}


def test_resolve_translation_profile_settings_returns_typed_mapping() -> None:
    with patch(
        "core.usecases.translation.profile_settings.list_translation_profile_settings",
        return_value={"openai_quality_translate": {"temperature": 0.4}},
    ):
        settings = resolve_translation_profile_settings()

    quality = settings["openai_quality_translate"]
    assert isinstance(quality, TranslationProfileRuntimeSettings)
    assert quality.temperature == 0.4
    assert quality.single_box_enabled is True


def test_get_translation_profile_applies_typed_runtime_settings_to_config() -> None:
    runtime_settings = {
        "openai_ultra_translate": TranslationProfileRuntimeSettings(
            model_id="gpt-5.1",
            max_output_tokens=1400,
            reasoning_effort="medium",
            temperature=0.25,
            single_box_enabled=False,
        )
    }
    with patch(
        "core.usecases.translation.profile_settings.resolve_translation_profile_settings",
        return_value=runtime_settings,
    ):
        profile = get_translation_profile("openai_ultra_translate")

    cfg = dict(profile.get("config", {}) or {})
    assert profile["enabled"] is False
    assert cfg["model"] == "gpt-5.1"
    assert cfg["max_output_tokens"] == 1400
    assert "temperature" not in cfg
    assert cfg["reasoning"] == {"effort": "medium"}


def test_list_ocr_profiles_with_settings_returns_typed_views() -> None:
    resolved_profiles = {
        profile_id: OcrProfileRuntimeSettings(
            model_id=None,
            max_output_tokens=None,
            reasoning_effort=None,
            temperature=None,
            page_translation_enabled=True,
        )
        for profile_id in OCR_PROFILES
    }
    with (
        patch(
            "core.usecases.ocr.profiles.settings.resolve_ocr_profile_settings",
            return_value=resolved_profiles,
        ),
        patch(
            "core.usecases.ocr.profiles.settings.resolve_ocr_label_overrides",
            return_value=OcrLabelOverrides(values={}),
        ),
    ):
        views = [
            view for view in list_ocr_profiles_with_settings() if view.id == "manga_ocr_default"
        ]

    assert len(views) == 1
    assert isinstance(views[0], OcrProfileSettingsView)
    assert views[0].page_translation_enabled is True
