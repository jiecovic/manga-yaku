# backend-python/core/usecases/translation/runtime/engine.py
"""Primary orchestration logic for translation operations."""

from __future__ import annotations

import logging
from typing import Any, cast

from config import DEBUG_PROMPTS, OPENAI_API_KEY
from core.domain.pages import set_box_translation_by_id
from infra.db.store_boxes import get_box_text_by_id
from infra.llm import (
    has_openai_sdk,
    is_openai_base_url_reachable,
)
from infra.logging.correlation import append_correlation
from infra.prompts import render_prompt_bundle

from ..profiles.catalog import (
    TRANSLATION_PROFILES,
    TranslationProfile,
    mark_translation_availability,
)
from ..profiles.registry import get_translation_profile
from .context import build_page_context, build_series_context
from .parsing import parse_structured_translation
from .provider import load_profile_prompt_bundle, run_openai_translate

# ----------------------------------------------------------------------
# Runtime capability detection → inform profiles
# ----------------------------------------------------------------------

_has_openai_sdk = has_openai_sdk()

# Cloud OpenAI available?
_has_cloud_openai = bool(OPENAI_API_KEY) and _has_openai_sdk

# Local OpenAI-compatible endpoint available?
_local_cfg = TRANSLATION_PROFILES["local_llm_default"].get("config", {})
_local_base_url = _local_cfg.get("base_url", "") if isinstance(_local_cfg, dict) else ""
_has_local_openai = (
    _has_openai_sdk and bool(_local_base_url) and is_openai_base_url_reachable(_local_base_url)
)

mark_translation_availability(
    has_cloud_openai=_has_cloud_openai,
    has_local_openai=_has_local_openai,
)

logger = logging.getLogger(__name__)


def run_translate_box_with_context(
    profile_id: str,
    volume_id: str,
    filename: str,
    box_id: int,
    use_page_context: bool,
    *,
    persist: bool = True,
    config_override: dict[str, Any] | None = None,
) -> str:
    _, profile, system_prompt, user_content = _prepare_translate_box_request(
        profile_id=profile_id,
        volume_id=volume_id,
        filename=filename,
        box_id=box_id,
        use_page_context=use_page_context,
        config_override=config_override,
    )

    provider = profile.get("provider", "")
    if provider == "openai_chat":
        translation = run_openai_translate(
            profile,
            system_prompt,
            user_content,
            expect_json=False,
            log_context={
                "profile_id": profile_id,
                "volume_id": volume_id,
                "filename": filename,
                "box_id": box_id,
            },
        )
    else:
        raise RuntimeError(f"Unknown translation provider '{provider}'")

    if persist and translation:
        set_box_translation_by_id(
            volume_id=volume_id,
            filename=filename,
            box_id=box_id,
            translation=translation,
        )

    return translation


def run_translate_box_with_context_structured(
    profile_id: str,
    volume_id: str,
    filename: str,
    box_id: int,
    use_page_context: bool,
    *,
    persist: bool = True,
    config_override: dict[str, Any] | None = None,
) -> dict[str, str]:
    _, profile, system_prompt, user_content = _prepare_translate_box_request(
        profile_id=profile_id,
        volume_id=volume_id,
        filename=filename,
        box_id=box_id,
        use_page_context=use_page_context,
        config_override=config_override,
    )

    provider = profile.get("provider", "")
    if provider != "openai_chat":
        raise RuntimeError(f"Unknown translation provider '{provider}'")

    raw_output = run_openai_translate(
        profile,
        system_prompt,
        user_content,
        expect_json=True,
        log_context={
            "profile_id": profile_id,
            "volume_id": volume_id,
            "filename": filename,
            "box_id": box_id,
        },
    )
    parsed = parse_structured_translation(raw_output)
    if persist and parsed["status"] == "ok":
        set_box_translation_by_id(
            volume_id=volume_id,
            filename=filename,
            box_id=box_id,
            translation=parsed["translation"],
        )
    return parsed


def _prepare_translate_box_request(
    *,
    profile_id: str,
    volume_id: str,
    filename: str,
    box_id: int,
    use_page_context: bool,
    config_override: dict[str, Any] | None,
) -> tuple[str, TranslationProfile, str, str]:
    box_text = get_box_text_by_id(volume_id, filename, box_id)
    if box_text is None:
        raise RuntimeError(f"Box {box_id} not found in {filename}")

    source_text = box_text.strip()
    if not source_text:
        raise RuntimeError("No OCR text in box")

    page_ctx = ""
    series_ctx = ""
    if use_page_context:
        page_ctx = build_page_context(
            volume_id,
            filename,
            target_box_id=box_id,
        )
        series_ctx = build_series_context(volume_id)

    profile = get_translation_profile(profile_id)
    if config_override:
        merged = dict(profile)
        cfg = dict(profile.get("config", {}) or {})
        cfg.update(config_override)
        merged["config"] = cfg
        profile = cast(TranslationProfile, merged)
    if not profile.get("enabled", True):
        raise RuntimeError(f"Translation profile '{profile_id}' is disabled or unavailable")

    bundle = load_profile_prompt_bundle(profile)
    rendered = render_prompt_bundle(
        bundle,
        system_context={
            "SERIES_CONTEXT": series_ctx,
            "PAGE_CONTEXT": page_ctx or "",
        },
        user_context={"TEXT": source_text},
    )
    system_prompt = rendered["system"]
    user_content = rendered["user_template"]

    if DEBUG_PROMPTS:
        logger.debug(
            append_correlation(
                "Translation prompt debug prepared",
                {
                    "component": "translation.prompt_debug",
                    "volume_id": volume_id,
                    "filename": filename,
                },
                box_id=box_id,
                use_page_context=use_page_context,
                source_chars=len(source_text),
                system_prompt_chars=len(system_prompt),
                user_content_chars=len(user_content),
            )
        )
    return source_text, profile, system_prompt, user_content
