# backend-python/core/usecases/translation/engine.py
"""Primary orchestration logic for translation operations."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, cast

from config import DEBUG_PROMPTS, OPENAI_API_KEY
from core.domain.pages import set_box_translation_by_id
from infra.db.db_store import (
    get_box_text_by_id,
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
    openai_chat_completions_create,
    openai_responses_create,
)
from infra.logging.correlation import append_correlation
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
    _has_openai_sdk and bool(_local_base_url) and is_openai_base_url_reachable(_local_base_url)
)

mark_translation_availability(
    has_cloud_openai=_has_cloud_openai,
    has_local_openai=_has_local_openai,
)

logger = logging.getLogger(__name__)


def _json_translation_validator(text: str) -> tuple[bool, str | None]:
    try:
        _parse_structured_translation(text)
    except Exception as exc:
        return False, str(exc).strip() or repr(exc)
    return True, None


def _build_text_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "single_box_translation",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["ok", "no_text"],
                },
                "translation": {"type": "string"},
            },
            "required": ["status", "translation"],
        },
        "strict": True,
    }


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise ValueError("Empty response")
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("JSON response must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    snippet = text[start : end + 1]
    parsed = json.loads(snippet)
    if not isinstance(parsed, dict):
        raise ValueError("JSON response must be an object")
    return parsed


def _parse_structured_translation(raw: str) -> dict[str, str]:
    payload = _extract_json(raw)
    status = str(payload.get("status") or "").strip().lower()
    translation = normalize_translation_output(str(payload.get("translation") or ""))
    if status not in {"ok", "no_text"}:
        raise ValueError("status must be 'ok' or 'no_text'")
    if status == "ok" and not translation:
        raise ValueError("translation is empty for status=ok")
    if status == "no_text":
        translation = ""
    return {
        "status": status,
        "translation": translation,
    }


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
            parts.append(
                "open threads:\n- " + "\n- ".join(_clip_context(line) for line in lines[:8])
            )

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
    page_snapshot = get_page_context_snapshot(volume_id, filename)
    if page_snapshot:
        manual_notes = str(page_snapshot.get("manual_notes") or "").strip()
        page_summary = str(page_snapshot.get("page_summary") or "").strip()
        image_summary = str(page_snapshot.get("image_summary") or "").strip()
        if manual_notes:
            parts.append(f"page notes: {_clip_context(manual_notes, max_chars=900)}")
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
    *,
    expect_json: bool = False,
    log_context: dict[str, Any] | None = None,
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

    if expect_json:
        system_prompt = (
            f"{system_prompt}\n\n"
            "Return only valid JSON with keys: "
            '{"status":"ok"|"no_text","translation":"..."}.\n'
            "Do not include markdown or extra text."
        )
        user_content = (
            f"{user_content}\n\n"
            "If the source has no translatable text, return status='no_text' and translation=''."
        )

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
            result_validator=_json_translation_validator if expect_json else None,
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
        params["text"] = {"format": _build_text_format()}
    try:
        resp = openai_responses_create(
            client,
            params,
            component="translation.single_box",
            context=log_context,
            result_validator=_json_translation_validator if expect_json else None,
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
            result_validator=_json_translation_validator if expect_json else None,
        )
        raw = chat_resp.choices[0].message.content or ""
        return raw.strip() if expect_json else normalize_translation_output(raw)


# =====================================================================
# HIGH-LEVEL TRANSLATION ENTRY
# =====================================================================


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
        translation = _run_openai_translate(
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

    raw_output = _run_openai_translate(
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
    parsed = _parse_structured_translation(raw_output)
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
        page_ctx = _build_page_context(
            volume_id,
            filename,
            target_box_id=box_id,
        )
        series_ctx = _build_series_context(volume_id)

    profile = get_translation_profile(profile_id)
    if config_override:
        merged = dict(profile)
        cfg = dict(profile.get("config", {}) or {})
        cfg.update(config_override)
        merged["config"] = cfg
        profile = cast(TranslationProfile, merged)
    if not profile.get("enabled", True):
        raise RuntimeError(f"Translation profile '{profile_id}' is disabled or unavailable")

    bundle = _load_profile_prompt_bundle(profile)
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
