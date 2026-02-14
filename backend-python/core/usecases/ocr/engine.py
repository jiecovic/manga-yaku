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
_has_openai_vision = _has_openai_sdk and bool(OPENAI_API_KEY)

if _has_openai_sdk and not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not set; OpenAI OCR profiles disabled.")
elif not _has_openai_sdk:
    logger.warning("OpenAI SDK not available; OpenAI OCR profiles disabled.")

mark_ocr_availability(
    has_manga_ocr=_manga_ocr is not None,
    has_openai_vision=_has_openai_vision,
)


# -------------------------------------------------------------------
# Core engines
# -------------------------------------------------------------------

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


def _run_openai_vision_ocr_box(
        profile: OcrProfile,
        volume_id: str,
        filename: str,
        x: float,
        y: float,
        width: float,
        height: float,
) -> str:
    """
    OpenAI OCR via chat+vision.

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
    elif provider == "openai_vision_chat":
        text = _run_openai_vision_ocr_box(profile, volume_id, filename, x, y, width, height)
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

