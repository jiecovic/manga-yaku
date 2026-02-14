# backend-python/core/usecases/agent/page_translate.py
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import yaml
from config import (
    AGENT_DEBUG_DIR,
    AGENT_MAX_OUTPUT_TOKENS,
    AGENT_MODEL,
    AGENT_REASONING_EFFORT,
    AGENT_TEMPERATURE,
    AGENT_TRANSLATE_MAX_OUTPUT_TOKENS,
    AGENT_TRANSLATE_REASONING_EFFORT,
    DEBUG_PROMPTS,
)
from infra.images.image_ops import encode_image_data_url, load_volume_image, resize_for_llm
from infra.llm import (
    build_response_params,
    create_openai_client,
    extract_response_text,
    has_openai_sdk,
)
from infra.prompts import load_prompt_bundle, render_prompt_bundle

logger = logging.getLogger(__name__)


def _build_text_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "translate_page",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "boxes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "box_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                            "ocr_profile_id": {"type": "string"},
                            "ocr_text": {"type": "string"},
                            "translation": {"type": "string"},
                        },
                        "required": [
                            "box_ids",
                            "ocr_profile_id",
                            "ocr_text",
                            "translation",
                        ],
                    },
                },
                "characters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "gender": {"type": "string"},
                            "info": {"type": "string"},
                        },
                        "required": ["name", "gender", "info"],
                    },
                },
                "image_summary": {"type": "string"},
                "story_summary": {"type": "string"},
                "no_text_boxes": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "open_threads": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "glossary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "term": {"type": "string"},
                            "translation": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["term", "translation", "note"],
                    },
                },
            },
            "required": [
                "boxes",
                "characters",
                "image_summary",
                "story_summary",
                "no_text_boxes",
                "open_threads",
                "glossary",
            ],
        },
        "strict": True,
    }


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise ValueError("Empty response")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    snippet = raw[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        pass

    repaired = _repair_json(snippet)
    return json.loads(repaired)


def _repair_json(raw: str) -> str:
    """
    Best-effort cleanup for minor JSON format issues from LLM output.
    Avoids heavy parsing; only handles common missing commas/trailing commas.
    """
    text = raw.strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r"}\s*{", "},{", text)
    text = re.sub(r"]\s*{", "],{", text)
    text = re.sub(r'([0-9eE"\}\]])\s*("[^"]+"\s*:)', r"\1,\2", text)
    return text


def _repair_with_llm(
    *,
    client: Any,
    model_cfg: dict[str, Any],
    raw_text: str,
) -> str:
    if not raw_text.strip():
        return raw_text
    repair_prompt = (
        "Fix the following JSON to match the required schema. "
        "Return only valid JSON. Do not add commentary."
    )
    input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": repair_prompt}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": raw_text}],
        },
    ]
    repair_cfg = dict(model_cfg)
    repair_cfg.setdefault("text", {"format": _build_text_format()})
    if "temperature" in repair_cfg:
        repair_cfg["temperature"] = 0.0
    if "max_output_tokens" in repair_cfg:
        repair_cfg["max_output_tokens"] = min(
            int(repair_cfg["max_output_tokens"]), 4096
        )
    params = build_response_params(repair_cfg, input_payload)
    resp = client.responses.create(**params)
    return extract_response_text(resp, raise_on_refusal=True)


def _should_retry(response: Any) -> bool:
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


def _format_yaml(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict) and not value:
        return ""
    if isinstance(value, list) and not value:
        return ""
    try:
        return yaml.safe_dump(
            value,
            allow_unicode=True,
            sort_keys=False,
        ).strip()
    except Exception:
        return str(value).strip()


def _build_prompt_payload(
    *,
    source_language: str,
    target_language: str,
    boxes: list[dict[str, Any]],
    ocr_profiles: list[dict[str, Any]] | None,
    prior_context_summary: str | None,
    prior_characters: list[dict[str, Any]] | None,
    prior_open_threads: list[str] | None,
    prior_glossary: list[dict[str, Any]] | None,
) -> tuple[str, str]:
    bundle = load_prompt_bundle("agent_translate_page.yml")
    input_yaml = yaml.safe_dump(
        {"boxes": boxes},
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    profiles_yaml = yaml.safe_dump(
        {"profiles": ocr_profiles or []},
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    rendered = render_prompt_bundle(
        bundle,
        system_context={
            "SOURCE_LANG": source_language,
            "TARGET_LANG": target_language,
            "PRIOR_CONTEXT_SUMMARY": _format_yaml(prior_context_summary),
            "PRIOR_CHARACTERS": _format_yaml(prior_characters),
            "PRIOR_OPEN_THREADS": _format_yaml(prior_open_threads),
            "PRIOR_GLOSSARY": _format_yaml(prior_glossary),
        },
        user_context={
            "INPUT_YAML": input_yaml,
            "OCR_PROFILES_YAML": profiles_yaml,
        },
    )
    return rendered["system"], rendered["user_template"]


def _write_debug_snapshot(
    *,
    debug_id: str | None,
    payload: dict[str, Any],
) -> None:
    if not DEBUG_PROMPTS:
        return
    try:
        target_dir = AGENT_DEBUG_DIR / "translate_page"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"{debug_id or 'agent'}_{stamp}.json"
        path = target_dir / name
        path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Failed to write agent debug snapshot: %s", exc)


def run_agent_translate_page(
    *,
    volume_id: str,
    filename: str,
    boxes: list[dict[str, Any]],
    ocr_profiles: list[dict[str, Any]] | None = None,
    prior_context_summary: str | None = None,
    prior_characters: list[dict[str, Any]] | None = None,
    prior_open_threads: list[str] | None = None,
    prior_glossary: list[dict[str, Any]] | None = None,
    source_language: str = "Japanese",
    target_language: str = "English",
    model_id: str | None = None,
    debug_id: str | None = None,
    max_output_tokens: int | None = None,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    if not has_openai_sdk():
        raise RuntimeError("OpenAI SDK is not available")

    system_prompt, user_content = _build_prompt_payload(
        source_language=source_language,
        target_language=target_language,
        boxes=boxes,
        ocr_profiles=ocr_profiles,
        prior_context_summary=prior_context_summary,
        prior_characters=prior_characters,
        prior_open_threads=prior_open_threads,
        prior_glossary=prior_glossary,
    )

    original_image = load_volume_image(volume_id, filename)
    image = resize_for_llm(original_image)
    data_url = encode_image_data_url(image)

    input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": user_content},
                {"type": "input_image", "image_url": data_url},
            ],
        },
    ]

    resolved_model = model_id or AGENT_MODEL
    max_output = max_output_tokens or max(
        AGENT_MAX_OUTPUT_TOKENS,
        AGENT_TRANSLATE_MAX_OUTPUT_TOKENS,
    )
    cfg: dict[str, Any] = {
        "model": resolved_model,
        "max_output_tokens": max_output,
    }
    if str(resolved_model).startswith("gpt-5"):
        effort = reasoning_effort or AGENT_TRANSLATE_REASONING_EFFORT or AGENT_REASONING_EFFORT
        if effort not in {"low", "medium", "high"}:
            effort = "medium"
        cfg["reasoning"] = {"effort": effort}
    else:
        cfg["temperature"] = temperature if temperature is not None else AGENT_TEMPERATURE
    cfg.setdefault("text", {"format": _build_text_format()})

    client = create_openai_client({})
    params = build_response_params(cfg, input_payload)
    resp = client.responses.create(**params)
    raw_text = extract_response_text(resp, raise_on_refusal=True)
    if not raw_text and _should_retry(resp):
        retry_cfg = dict(cfg)
        retry_cfg["max_output_tokens"] = max(max_output * 2, max_output + 512)
        retry_params = build_response_params(retry_cfg, input_payload)
        retry_params.setdefault("text", {"format": _build_text_format()})
        resp = client.responses.create(**retry_params)
        raw_text = extract_response_text(resp, raise_on_refusal=True)
        cfg = retry_cfg
        params = retry_params

    debug_payload = {
        "job_id": debug_id,
        "volume_id": volume_id,
        "filename": filename,
        "model": cfg.get("model"),
        "params": {
            "max_output_tokens": cfg.get("max_output_tokens"),
            "reasoning": cfg.get("reasoning"),
            "temperature": cfg.get("temperature"),
            "text": cfg.get("text"),
        },
        "image": {
            "original_size": list(original_image.size),
            "resized_size": list(image.size),
            "data_url_len": len(data_url),
        },
        "system_prompt": system_prompt,
        "user_prompt": user_content,
        "ocr_profiles": ocr_profiles,
        "boxes": boxes,
        "raw_output_text": raw_text,
    }
    try:
        debug_payload["response"] = resp.model_dump()
    except Exception:
        debug_payload["response"] = repr(resp)
    if not raw_text:
        raw_dump: str
        try:
            raw_dump = json.dumps(resp.model_dump(), ensure_ascii=True)
        except Exception:
            raw_dump = repr(resp)
        logger.warning("Empty agent translate response: %s", raw_dump)

    repaired_text: str | None = None
    try:
        result = _extract_json(raw_text)
    except Exception as exc:
        logger.warning("Failed to parse agent JSON, retrying repair: %s", exc)
        try:
            repaired_text = _repair_with_llm(
                client=client,
                model_cfg=cfg,
                raw_text=raw_text,
            )
            result = _extract_json(repaired_text)
        except Exception:
            _write_debug_snapshot(
                debug_id=debug_id,
                payload={**debug_payload, "repair_output_text": repaired_text},
            )
            raise

    debug_payload["repair_output_text"] = repaired_text
    _write_debug_snapshot(debug_id=debug_id, payload=debug_payload)
    return result
