# backend-python/core/usecases/translation/engine.py
from __future__ import annotations

import logging
from typing import Any

from config import DEBUG_PROMPTS, OPENAI_API_KEY
from core.domain.pages import set_box_translation_by_id
from infra.db.db_store import (
    get_box_text_by_id,
    get_page_context,
)
from infra.llm import (
    build_chat_params,
    build_response_params,
    create_openai_client,
    has_openai_sdk,
    is_openai_base_url_reachable,
)
from infra.prompts import (
    PromptBundle,
    load_prompt_bundle,
    render_prompt_bundle,
)

from .profiles import (
    TRANSLATION_PROFILES,
    TranslationProfile,
    get_translation_profile,
    mark_translation_availability,
)
from .utils import normalize_translation_output

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
    _has_openai_sdk
    and bool(_local_base_url)
    and is_openai_base_url_reachable(_local_base_url)
)

mark_translation_availability(
    has_cloud_openai=_has_cloud_openai,
    has_local_openai=_has_local_openai,
)

logger = logging.getLogger(__name__)

# =====================================================================
# PROMPTS
# =====================================================================

def _load_profile_prompt_bundle(profile: TranslationProfile) -> PromptBundle:
    """
    Load the YAML prompt bundle for a profile (system + user_template).
    Reads profile.config["prompt_file"].
    """
    cfg = profile.get("config", {}) or {}
    prompt_file = cfg.get("prompt_file", "translation_fast.yml")
    return load_prompt_bundle(prompt_file)


# =====================================================================
# CORE PROVIDER FUNCTIONS
# =====================================================================

def _get_openai_client_for_profile(profile: TranslationProfile):
    """
    Thin wrapper around the shared LLM client helper.
    """
    cfg = profile.get("config", {}) or {}
    return create_openai_client(cfg)


def _run_openai_translate(
    profile: TranslationProfile,
    system_prompt: str,
    user_content: str,
) -> str:
    """
    Generic translation runner for all OpenAI-chat-compatible profiles:
    - Cloud OpenAI (gpt-4o-mini, gpt-4.1-mini, gpt-5.1, ...)
    - Local OpenAI-compatible servers (via base_url in profile.config)
    """
    cfg = profile.get("config", {}) or {}
    client = _get_openai_client_for_profile(profile)
    base_url = cfg.get("base_url")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    if base_url:
        params = build_chat_params(cfg, messages)
        resp = client.chat.completions.create(**params)
        raw = (resp.choices[0].message.content or "")
        return normalize_translation_output(raw)

    if not hasattr(client, "responses"):
        params = build_chat_params(cfg, messages)
        resp = client.chat.completions.create(**params)
        raw = (resp.choices[0].message.content or "")
        return normalize_translation_output(raw)

    input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": user_content}],
        },
    ]

    params = build_response_params(cfg, input_payload)
    resp = client.responses.create(**params)

    raw = getattr(resp, "output_text", None)
    if raw:
        return normalize_translation_output(raw)

    output = getattr(resp, "output", None)
    if output:
        parts: list[str] = []
        for item in output:
            content = getattr(item, "content", None)
            if content is None and isinstance(item, dict):
                content = item.get("content")
            if not content:
                continue
            for chunk in content:
                chunk_type = None
                text_value = None
                if isinstance(chunk, dict):
                    chunk_type = chunk.get("type")
                    text_value = chunk.get("text")
                else:
                    chunk_type = getattr(chunk, "type", None)
                    text_value = getattr(chunk, "text", None)
                if text_value and (chunk_type in (None, "output_text", "text")):
                    parts.append(str(text_value))
        if parts:
            return normalize_translation_output("\n".join(parts))

    return ""


# =====================================================================
# HIGH-LEVEL TRANSLATION ENTRY
# =====================================================================

def run_translate_box_with_context(
    profile_id: str,
    volume_id: str,
    filename: str,
    box_id: int,
    use_page_context: bool,
) -> str:
    """
    High-level translation runner.

    Responsibilities:
    - Load the target box content.
    - Gather page context.
    - Render prompts via YAML + Jinja2 templates.
    - Call the selected translation provider.
    - Persist the translation back into the JSON structure.
    """
    # 1) Load box text content
    box_text = get_box_text_by_id(volume_id, filename, box_id)
    if box_text is None:
        raise RuntimeError(f"Box {box_id} not found in {filename}")

    source_text = box_text.strip()
    if not source_text:
        raise RuntimeError("No OCR text in box")

    # 2) Page context
    page_ctx = get_page_context(volume_id, filename) if use_page_context else ""

    # 5) Resolve profile
    profile = get_translation_profile(profile_id)
    if not profile.get("enabled", True):
        raise RuntimeError(f"Translation profile '{profile_id}' is disabled or unavailable")

    # 6) Load and render YAML prompt bundle with Jinja2
    bundle = _load_profile_prompt_bundle(profile)

    system_context: dict[str, Any] = {
        "SERIES_CONTEXT": "",
        "PAGE_CONTEXT": page_ctx or "",
    }

    user_context: dict[str, Any] = {
        "TEXT": source_text,
    }

    rendered = render_prompt_bundle(
        bundle,
        system_context=system_context,
        user_context=user_context,
    )

    system_prompt = rendered["system"]
    user_content = rendered["user_template"]

    provider = profile.get("provider", "")

    if DEBUG_PROMPTS:
        logger.debug("================ TRANSLATION PROMPT DEBUG ================")
        logger.debug("Volume: %s | Page: %s | Box: %s", volume_id, filename, box_id)
        logger.debug("Use page context: %s", use_page_context)
        logger.debug("----- SOURCE TEXT -----")
        logger.debug("%s", source_text)
        logger.debug("----- SYSTEM PROMPT -----")
        logger.debug(
            "%s",
            system_prompt.encode("utf-8", errors="replace").decode("utf-8", errors="replace"),
        )
        logger.debug("----- USER CONTENT -----")
        logger.debug(
            "%s",
            user_content.encode("utf-8", errors="replace").decode("utf-8", errors="replace"),
        )
        logger.debug("===========================================================")

    # 7) Call provider
    if provider == "openai_chat":
        translation = _run_openai_translate(profile, system_prompt, user_content)
    else:
        raise RuntimeError(f"Unknown translation provider '{provider}'")

    # 8) Persist translation back into the page JSON via domain helper
    set_box_translation_by_id(
        volume_id=volume_id,
        filename=filename,
        box_id=box_id,
        translation=translation,
    )

    return translation

