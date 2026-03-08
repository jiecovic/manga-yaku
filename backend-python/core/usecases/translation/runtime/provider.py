# backend-python/core/usecases/translation/runtime/provider.py
"""Provider-facing helpers for single-box translation."""

from __future__ import annotations

import logging
from typing import Any

from infra.llm import (
    build_chat_params,
    build_response_params,
    create_openai_client,
    extract_response_text,
    openai_chat_completions_create,
    openai_responses_create,
)
from infra.logging.correlation import append_correlation
from infra.prompts import PromptBundle, load_prompt_bundle, render_prompt_bundle

from ..profiles.registry import TranslationProfile
from .parsing import build_text_format, json_translation_validator
from .utils import normalize_translation_output

logger = logging.getLogger(__name__)


def load_profile_prompt_bundle(profile: TranslationProfile) -> PromptBundle:
    """Load the YAML prompt bundle for a profile."""
    cfg = profile.get("config", {}) or {}
    prompt_file = cfg.get("prompt_file", "translation/single_box/fast.yml")
    return load_prompt_bundle(prompt_file)


def load_structured_output_prompt_bundle() -> PromptBundle:
    """Load the structured-output addendum for single-box translation calls."""
    return load_prompt_bundle("translation/single_box/structured_output.yml")


def get_openai_client_for_profile(profile: TranslationProfile) -> Any:
    """Build a client using the profile's provider config."""
    cfg = profile.get("config", {}) or {}
    return create_openai_client(cfg)


def run_openai_translate(
    profile: TranslationProfile,
    system_prompt: str,
    user_content: str,
    *,
    expect_json: bool = False,
    log_context: dict[str, Any] | None = None,
) -> str:
    """Run a single-box translation call against an OpenAI-compatible backend."""
    cfg = profile.get("config", {}) or {}
    client = get_openai_client_for_profile(profile)
    base_url = cfg.get("base_url")

    if expect_json:
        structured_bundle = render_prompt_bundle(
            load_structured_output_prompt_bundle(),
            system_context={},
            user_context={},
        )
        system_prompt = f"{system_prompt}\n\n{structured_bundle['system']}"
        user_content = f"{user_content}\n\n{structured_bundle['user_template']}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    if not hasattr(client, "responses"):
        params = build_chat_params(cfg, messages)
        resp = openai_chat_completions_create(
            client,
            params,
            component="translation.single_box",
            context=log_context,
            result_validator=json_translation_validator if expect_json else None,
        )
        raw = resp.choices[0].message.content or ""
        return raw.strip() if expect_json else normalize_translation_output(raw)

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
    if expect_json:
        params["text"] = {"format": build_text_format()}
    try:
        resp = openai_responses_create(
            client,
            params,
            component="translation.single_box",
            context=log_context,
            result_validator=json_translation_validator if expect_json else None,
        )
        text = extract_response_text(resp)
        return text.strip() if expect_json else normalize_translation_output(text)
    except Exception as exc:
        if not base_url:
            raise
        logger.warning(
            append_correlation(
                f"Responses API failed for local translation endpoint; falling back to chat API: {exc}",
                log_context,
            )
        )
        chat_params = build_chat_params(cfg, messages)
        chat_resp = openai_chat_completions_create(
            client,
            chat_params,
            component="translation.single_box",
            context=log_context,
            result_validator=json_translation_validator if expect_json else None,
        )
        raw = chat_resp.choices[0].message.content or ""
        return raw.strip() if expect_json else normalize_translation_output(raw)
