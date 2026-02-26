# backend-python/core/usecases/translation/engine.py
from __future__ import annotations

import logging
from typing import Any

from config import DEBUG_PROMPTS, OPENAI_API_KEY
from core.domain.pages import set_box_translation_by_id
from infra.db.db_store import (
    get_box_text_by_id,
    get_page_context,
    get_page_context_snapshot,
    get_volume_context,
    load_page,
)
from infra.llm import (
    build_chat_params,
    build_response_params,
    create_openai_client,
    extract_response_text,
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


def _clip_context(value: str, *, max_chars: int = 420) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3].rstrip()}..."


def _build_series_context(volume_id: str) -> str:
    snapshot = get_volume_context(volume_id)
    if not snapshot:
        return ""

    parts: list[str] = []
    rolling_summary = str(snapshot.get("rolling_summary") or "").strip()
    if rolling_summary:
        parts.append(f"story summary: {_clip_context(rolling_summary, max_chars=900)}")

    active_characters = snapshot.get("active_characters")
    if isinstance(active_characters, list):
        lines: list[str] = []
        for item in active_characters[:8]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            info = str(item.get("info") or "").strip()
            if not name and not info:
                continue
            if name and info:
                lines.append(f"{name}: {_clip_context(info, max_chars=140)}")
            elif name:
                lines.append(name)
            else:
                lines.append(_clip_context(info, max_chars=140))
        if lines:
            parts.append("active characters:\n- " + "\n- ".join(lines))

    open_threads = snapshot.get("open_threads")
    if isinstance(open_threads, list):
        lines = [str(item).strip() for item in open_threads if str(item).strip()]
        if lines:
            parts.append("open threads:\n- " + "\n- ".join(_clip_context(line) for line in lines[:8]))

    glossary = snapshot.get("glossary")
    if isinstance(glossary, list):
        lines: list[str] = []
        for item in glossary[:8]:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term") or "").strip()
            translation = str(item.get("translation") or "").strip()
            note = str(item.get("note") or "").strip()
            if term and translation:
                line = f"{term} => {translation}"
                if note:
                    line += f" ({_clip_context(note, max_chars=120)})"
                lines.append(line)
        if lines:
            parts.append("glossary:\n- " + "\n- ".join(lines))

    return "\n\n".join(parts)


def _build_page_context(
    volume_id: str,
    filename: str,
    *,
    target_box_id: int,
) -> str:
    parts: list[str] = []
    page_context = get_page_context(volume_id, filename)
    if page_context.strip():
        parts.append(f"page notes: {_clip_context(page_context, max_chars=900)}")

    page_snapshot = get_page_context_snapshot(volume_id, filename)
    if page_snapshot:
        page_summary = str(page_snapshot.get("page_summary") or "").strip()
        image_summary = str(page_snapshot.get("image_summary") or "").strip()
        if page_summary:
            parts.append(f"page summary: {_clip_context(page_summary, max_chars=900)}")
        if image_summary:
            parts.append(f"image summary: {_clip_context(image_summary, max_chars=900)}")

    page = load_page(volume_id, filename)
    raw_boxes = page.get("boxes") if isinstance(page, dict) else []
    lines: list[str] = []
    if isinstance(raw_boxes, list):
        sorted_boxes = sorted(
            raw_boxes,
            key=lambda box: (
                int(box.get("orderIndex") or box.get("id") or 0),
                int(box.get("id") or 0),
            ),
        )
        for box in sorted_boxes:
            if not isinstance(box, dict):
                continue
            box_id = int(box.get("id") or 0)
            if box_id <= 0 or box_id == target_box_id:
                continue
            if str(box.get("type") or "").strip().lower() != "text":
                continue
            order = int(box.get("orderIndex") or box_id)
            ocr_text = str(box.get("text") or "").strip()
            translation = str(box.get("translation") or "").strip()
            if ocr_text:
                lines.append(f"box #{order} ocr: {_clip_context(ocr_text)}")
            if translation:
                lines.append(f"box #{order} translation: {_clip_context(translation)}")
            if len(lines) >= 12:
                break
    if lines:
        parts.append("neighbor boxes:\n- " + "\n- ".join(lines))

    return "\n\n".join(parts)

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
    Generic translation runner for OpenAI-backed profiles.
    - Cloud OpenAI (gpt-4o-mini, gpt-4.1-mini, gpt-5.1, ...)
    - Local OpenAI-compatible servers (via base_url in profile.config)

    Uses Responses API by default; falls back to Chat Completions for
    local endpoints if needed.
    """
    cfg = profile.get("config", {}) or {}
    client = _get_openai_client_for_profile(profile)
    base_url = cfg.get("base_url")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

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
    try:
        resp = client.responses.create(**params)
        return normalize_translation_output(extract_response_text(resp))
    except Exception as exc:
        if not base_url:
            raise
        logger.warning(
            "Responses API failed for local translation endpoint; falling back to chat API: %s",
            exc,
        )
        chat_params = build_chat_params(cfg, messages)
        chat_resp = client.chat.completions.create(**chat_params)
        raw = (chat_resp.choices[0].message.content or "")
        return normalize_translation_output(raw)


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

    # 2) Optional context (page + volume memory snapshots + neighboring box data)
    page_ctx = ""
    series_ctx = ""
    if use_page_context:
        page_ctx = _build_page_context(
            volume_id,
            filename,
            target_box_id=box_id,
        )
        series_ctx = _build_series_context(volume_id)

    # 5) Resolve profile
    profile = get_translation_profile(profile_id)
    if not profile.get("enabled", True):
        raise RuntimeError(f"Translation profile '{profile_id}' is disabled or unavailable")

    # 6) Load and render YAML prompt bundle with Jinja2
    bundle = _load_profile_prompt_bundle(profile)

    system_context: dict[str, Any] = {
        "SERIES_CONTEXT": series_ctx,
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
