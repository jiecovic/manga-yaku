# backend-python/core/usecases/ocr/engine.py
from __future__ import annotations

import base64
import io
import logging
from typing import Any

from config import OPENAI_API_KEY
from core.domain.pages import set_box_ocr_text_by_id
from infra.images.image_ops import crop_volume_image, resize_for_llm
from infra.llm import (
    build_chat_params,
    build_response_params,
    create_openai_client,
    extract_response_text,
    has_openai_sdk,
)
from infra.prompts import PromptBundle, load_prompt_bundle

from .profiles import (
    OcrProfile,
    get_ocr_profile,
    mark_ocr_availability,
)

logger = logging.getLogger(__name__)

# Optional manga-ocr import
try:
    from manga_ocr import MangaOcr  # type: ignore

    _manga_ocr = MangaOcr()
    _manga_ocr_error: Exception | None = None
except Exception as e:  # pragma: no cover
    _manga_ocr = None
    _manga_ocr_error = e

# -------------------------------------------------------------------
# Runtime availability → tell profiles which ones are usable
# -------------------------------------------------------------------

_has_openai_sdk = has_openai_sdk()
_has_llm_ocr = _has_openai_sdk and bool(OPENAI_API_KEY)

if _has_openai_sdk and not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not set; OpenAI OCR profiles disabled.")
elif not _has_openai_sdk:
    logger.warning("OpenAI SDK not available; OpenAI OCR profiles disabled.")

mark_ocr_availability(
    has_manga_ocr=_manga_ocr is not None,
    has_llm_ocr=_has_llm_ocr,
)


# -------------------------------------------------------------------
# Core engines
# -------------------------------------------------------------------


def _to_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return parsed


def _bump_token_limit(
    cfg: dict[str, Any],
    *,
    cap: int = 768,
) -> tuple[dict[str, Any], int, int] | None:
    for key in ("max_output_tokens", "max_completion_tokens", "max_tokens"):
        current = _to_int(cfg.get(key))
        if current is None:
            continue
        new_limit = min(max(current * 2, current + 64), cap)
        if new_limit <= current:
            return None
        retry_cfg = dict(cfg)
        retry_cfg[key] = new_limit
        return retry_cfg, current, new_limit
    return None


def _responses_truncated(response: Any) -> bool:
    status = getattr(response, "status", None)
    if status is None and isinstance(response, dict):
        status = response.get("status")
    if status != "incomplete":
        return False

    details = getattr(response, "incomplete_details", None)
    if details is None and isinstance(response, dict):
        details = response.get("incomplete_details") or {}

    reason = None
    if isinstance(details, dict):
        reason = details.get("reason")
    else:
        reason = getattr(details, "reason", None)
    return reason == "max_output_tokens"


def _chat_completions_truncated(response: Any) -> bool:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not isinstance(choices, list):
        return False

    for choice in choices:
        finish_reason = None
        if isinstance(choice, dict):
            finish_reason = choice.get("finish_reason")
        else:
            finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason == "length":
            return True
    return False

def _run_manga_ocr_box(
        volume_id: str,
        filename: str,
        x: float,
        y: float,
        width: float,
        height: float,
) -> str:
    if _manga_ocr is None:
        raise RuntimeError(f"manga-ocr is not available: {_manga_ocr_error!r}")

    crop = crop_volume_image(volume_id, filename, x, y, width, height)
    crop = resize_for_llm(crop)
    return _manga_ocr(crop)


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
    Falls back to 'ocr_default.yml' if prompt_file is missing.
    """
    cfg = profile.get("config", {}) or {}
    prompt_file = cfg.get("prompt_file", "ocr_default.yml")
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
    LLM OCR via chat/image input.

    Model-agnostic:
    - The engine does NOT care which exact model is used.
    - It just builds `messages` and forwards config keys into
      `client.chat.completions.create(...)`.
    """
    client = _get_openai_client_for_ocr_profile(profile)
    bundle = _load_ocr_prompt_bundle(profile)
    system_prompt = bundle["system"]
    user_template = bundle["user_template"] or "Transcribe the text from this crop. Plain text only."

    crop = crop_volume_image(volume_id, filename, x, y, width, height)

    buf = io.BytesIO()
    crop.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    cfg = dict(profile.get("config", {}) or {})

    model_id = str(cfg.get("model") or "")
    if model_id.startswith("gpt-5"):
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

        params = build_response_params(cfg, input_payload)
        resp = client.responses.create(**params)
        if _responses_truncated(resp):
            bumped = _bump_token_limit(cfg)
            if bumped is not None:
                retry_cfg, before, after = bumped
                logger.debug(
                    "LLM OCR truncated for %s/%s; retrying with token limit %s -> %s",
                    volume_id,
                    filename,
                    before,
                    after,
                )
                retry_params = build_response_params(retry_cfg, input_payload)
                resp = client.responses.create(**retry_params)
        text = extract_response_text(resp)
        return text.strip()

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

    resp = client.chat.completions.create(**params)
    if _chat_completions_truncated(resp):
        bumped = _bump_token_limit(cfg)
        if bumped is not None:
            retry_cfg, before, after = bumped
            logger.debug(
                "LLM OCR truncated for %s/%s (chat); retrying with token limit %s -> %s",
                volume_id,
                filename,
                before,
                after,
            )
            retry_params = build_chat_params(retry_cfg, messages)
            resp = client.chat.completions.create(**retry_params)
    text = resp.choices[0].message.content or ""
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
) -> str:
    profile = get_ocr_profile(profile_id)

    if not profile.get("enabled", True):
        raise RuntimeError(f"OCR profile '{profile_id}' is disabled")

    provider = profile.get("provider")

    if provider == "manga_ocr":
        text = _run_manga_ocr_box(volume_id, filename, x, y, width, height)
    elif provider == "llm_ocr_chat":
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

