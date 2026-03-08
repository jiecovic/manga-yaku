# backend-python/core/usecases/ocr/runtime/engine.py
"""Primary orchestration logic for ocr operations."""

from __future__ import annotations

import base64
import io
import logging
from typing import Any, cast

from core.domain.pages import set_box_ocr_text_by_id
from infra.images.image_ops import crop_volume_image, resize_for_llm
from infra.llm import (
    build_chat_params,
    build_response_params,
    create_openai_client,
    extract_response_text,
    openai_chat_completions_create,
    openai_responses_create,
)
from infra.logging.correlation import append_correlation
from infra.prompts import PromptBundle, load_prompt_bundle

from ..profiles.catalog import OcrProfile
from ..profiles.registry import get_ocr_profile
from .bootstrap import get_manga_ocr_runtime, initialize_ocr_runtime

logger = logging.getLogger(__name__)
initialize_ocr_runtime()


# -------------------------------------------------------------------
# Core engines
# -------------------------------------------------------------------


def _is_repetitive_ocr(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 60:
        return False
    counts: dict[str, int] = {}
    for ch in cleaned:
        counts[ch] = counts.get(ch, 0) + 1
    most_common = max(counts.values()) if counts else 0
    return most_common / max(len(cleaned), 1) >= 0.7


def _validate_ocr_response_text(text: str) -> tuple[bool, str | None]:
    cleaned = str(text or "").strip()
    if cleaned.upper() == "NO_TEXT":
        return True, None
    if not cleaned or cleaned in {'""', "''"}:
        return False, "empty OCR output"
    if _is_repetitive_ocr(cleaned):
        return False, "repetitive OCR output"
    return True, None


def _run_llm_ocr_box_chat_fallback(
    client: Any,
    cfg: dict[str, Any],
    *,
    profile_id: str,
    system_prompt: str,
    user_template: str,
    data_url: str,
    volume_id: str,
    filename: str,
) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_template},
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
            ],
        },
    ]

    params = build_chat_params(cfg, messages)
    resp = openai_chat_completions_create(
        client,
        params,
        component="ocr.single_box",
        context={
            "profile_id": profile_id,
            "volume_id": volume_id,
            "filename": filename,
        },
        result_validator=_validate_ocr_response_text,
    )
    text = resp.choices[0].message.content or ""
    return text.strip()


def _run_manga_ocr_box(
    volume_id: str,
    filename: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> str:
    manga_ocr, init_error = get_manga_ocr_runtime()
    if manga_ocr is None:
        raise RuntimeError(f"manga-ocr is not available: {init_error!r}")

    crop = crop_volume_image(volume_id, filename, x, y, width, height)
    crop = resize_for_llm(crop)
    return manga_ocr(crop)


# -------------------------------------------------------------------
# OpenAI / OpenAI-compatible client
# -------------------------------------------------------------------
def _get_openai_client_for_ocr_profile(profile: OcrProfile):
    """
    Thin wrapper around the shared LLM client helper.
    """
    cfg = profile.get("config", {}) or {}
    return create_openai_client(cfg)


def _load_ocr_prompt_bundle(profile: OcrProfile) -> PromptBundle:
    """
    Load the YAML prompt bundle referenced by this OCR profile.
    Falls back to 'ocr/single_box/default.yml' if prompt_file is missing.
    """
    cfg = profile.get("config", {}) or {}
    prompt_file = cfg.get("prompt_file", "ocr/single_box/default.yml")
    return load_prompt_bundle(prompt_file)


def _run_llm_ocr_box(
    profile: OcrProfile,
    volume_id: str,
    filename: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> str:
    """
    LLM OCR via Responses API with image input.

    Falls back to chat completions only for local OpenAI-compatible
    endpoints when Responses is not available.
    """
    client = _get_openai_client_for_ocr_profile(profile)
    bundle = _load_ocr_prompt_bundle(profile)
    system_prompt = bundle["system"]
    user_template = (
        bundle["user_template"] or "Transcribe the text from this crop. Plain text only."
    )

    crop = crop_volume_image(volume_id, filename, x, y, width, height)

    buf = io.BytesIO()
    crop.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    cfg = dict(profile.get("config", {}) or {})

    cfg.setdefault("text", {"format": {"type": "text"}})
    input_payload: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": user_template},
                {
                    "type": "input_image",
                    "image_url": data_url,
                    "detail": "high",
                },
            ],
        },
    ]

    if not hasattr(client, "responses"):
        return _run_llm_ocr_box_chat_fallback(
            client,
            cfg,
            profile_id=str(profile.get("id") or ""),
            system_prompt=system_prompt,
            user_template=user_template,
            data_url=data_url,
            volume_id=volume_id,
            filename=filename,
        )

    params = build_response_params(cfg, input_payload)
    try:
        resp = openai_responses_create(
            client,
            params,
            component="ocr.single_box",
            context={
                "profile_id": str(profile.get("id") or ""),
                "volume_id": volume_id,
                "filename": filename,
            },
            result_validator=_validate_ocr_response_text,
        )
    except Exception as exc:
        if cfg.get("base_url"):
            logger.warning(
                append_correlation(
                    f"LLM OCR responses API failed for local endpoint; falling back to chat API: {exc}",
                    {
                        "component": "ocr.single_box",
                        "volume_id": volume_id,
                        "filename": filename,
                    },
                    profile_id=str(profile.get("id") or ""),
                )
            )
            return _run_llm_ocr_box_chat_fallback(
                client,
                cfg,
                profile_id=str(profile.get("id") or ""),
                system_prompt=system_prompt,
                user_template=user_template,
                data_url=data_url,
                volume_id=volume_id,
                filename=filename,
            )
        raise

    text = extract_response_text(resp)
    return text.strip()


# -------------------------------------------------------------------
# Public entry
# -------------------------------------------------------------------


def run_ocr_box(
    profile_id: str,
    volume_id: str,
    filename: str,
    box_id: int | None,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    persist: bool = True,
    config_override: dict[str, Any] | None = None,
) -> str:
    profile = get_ocr_profile(profile_id)
    if config_override:
        merged = dict(profile)
        cfg = dict(profile.get("config", {}) or {})
        cfg.update(config_override)
        merged["config"] = cfg
        profile = cast(OcrProfile, merged)

    if not profile.get("enabled", True):
        raise RuntimeError(f"OCR profile '{profile_id}' is disabled")

    provider = profile.get("provider")

    if provider == "manga_ocr":
        text = _run_manga_ocr_box(volume_id, filename, x, y, width, height)
    elif provider == "llm_ocr":
        text = _run_llm_ocr_box(profile, volume_id, filename, x, y, width, height)
    else:
        raise RuntimeError(f"Unknown OCR provider '{provider}' for '{profile_id}'")

    if text and persist and box_id is not None:
        set_box_ocr_text_by_id(
            volume_id,
            filename,
            box_id=box_id,
            ocr_text=text,
        )

    return text
