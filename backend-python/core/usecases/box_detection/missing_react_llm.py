# backend-python/core/usecases/box_detection/missing_react_llm.py
"""Experimental LLM calls for the missing-box ReAct prototype."""

from __future__ import annotations

import json
import re
from typing import Any

from infra.llm import extract_response_text, openai_responses_create

from .missing_react_config import MissingBoxDetectionConfig


def _build_log_context(
    *,
    volume_id: str,
    filename: str,
    log_context: dict[str, Any] | None,
) -> dict[str, Any]:
    context = dict(log_context or {})
    context.setdefault("volume_id", volume_id)
    context.setdefault("filename", filename)
    return context


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Empty model response")
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        salvaged = _extract_partial_candidates(text)
        if salvaged is not None:
            return salvaged
        raise ValueError("No JSON object found in model response")
    candidate_text = text[start : end + 1]
    try:
        parsed = json.loads(candidate_text)
    except json.JSONDecodeError:
        salvaged = _extract_partial_candidates(text)
        if salvaged is not None:
            return salvaged
        raise
    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON must be an object")
    return parsed


def _extract_partial_candidates(raw: str) -> dict[str, Any] | None:
    key_index = raw.find('"candidates"')
    if key_index == -1:
        return None
    list_start = raw.find("[", key_index)
    if list_start == -1:
        return None

    items: list[dict[str, Any]] = []
    idx = list_start + 1
    raw_len = len(raw)
    while idx < raw_len:
        char = raw[idx]
        if char in " \r\n\t,":
            idx += 1
            continue
        if char == "]":
            return {"candidates": items}
        if char != "{":
            break

        object_end = _find_complete_json_object_end(raw, idx)
        if object_end is None:
            break
        try:
            parsed = json.loads(raw[idx : object_end + 1])
        except json.JSONDecodeError:
            break
        if isinstance(parsed, dict):
            items.append(parsed)
        idx = object_end + 1

    if items:
        return {"candidates": items}
    return None


def _find_complete_json_object_end(raw: str, start_index: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start_index, len(raw)):
        char = raw[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return idx
    return None


def _build_proposal_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "missing_text_box_proposals",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "hint_text": {"type": "string"},
                            "reason": {"type": "string"},
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                        },
                        "required": ["hint_text", "reason", "x", "y", "width", "height"],
                    },
                }
            },
            "required": ["candidates"],
        },
        "strict": True,
    }


def _build_verify_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "missing_text_box_verification",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "contains_text": {"type": "boolean"},
                "fully_inside_box": {"type": "boolean"},
                "text_cut_off": {"type": "boolean"},
                "confidence": {"type": "number"},
                "observed_text": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": [
                "contains_text",
                "fully_inside_box",
                "text_cut_off",
                "confidence",
                "observed_text",
                "reason",
            ],
        },
        "strict": True,
    }


def _build_adjust_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "missing_text_box_adjustment",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "width": {"type": "number"},
                "height": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["x", "y", "width", "height", "reason"],
        },
        "strict": True,
    }


def _call_responses_json(
    *,
    client: Any,
    model_id: str,
    input_payload: list[dict[str, Any]],
    text_format: dict[str, Any],
    component: str,
    context: dict[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": model_id,
        "input": input_payload,
        "text": {"format": text_format},
        "max_output_tokens": max_output_tokens,
        "reasoning": {"effort": "medium"},
    }
    response = openai_responses_create(
        client,
        params,
        component=component,
        context=context,
    )
    raw = extract_response_text(response, raise_on_refusal=True)
    return _extract_json_object(raw)


def _propose_missing_candidates(
    *,
    client: Any,
    cfg: MissingBoxDetectionConfig,
    volume_id: str,
    filename: str,
    log_context: dict[str, Any] | None,
    page_data_url: str,
    resized_w: int,
    resized_h: int,
    existing_boxes_resized: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    system_prompt = (
        "You are an expert manga layout annotator. "
        "Find text regions that are visible in the page image but missing from the existing text boxes. "
        "Do not return boxes that duplicate existing coverage. "
        "Return strict JSON."
    )
    user_payload = {
        "task": "find_missing_text_boxes",
        "image_size": {"width": resized_w, "height": resized_h},
        "max_candidates": cfg.max_candidates,
        "existing_boxes": existing_boxes_resized,
        "instructions": [
            "Coordinates must be in the provided image coordinate space.",
            "Prefer tight boxes around speech/text regions.",
            "Only include likely missing text regions.",
            "Keep hint_text very short. Use literal text only when obvious, otherwise a short location label.",
            "Keep reason short and concrete. Return fewer candidates instead of verbose descriptions.",
        ],
    }
    input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": json.dumps(user_payload, ensure_ascii=True)},
                {"type": "input_image", "image_url": page_data_url},
            ],
        },
    ]
    parsed = _call_responses_json(
        client=client,
        model_id=cfg.model_id,
        input_payload=input_payload,
        text_format=_build_proposal_format(),
        component="box_detection.missing_react.propose",
        context=_build_log_context(
            volume_id=volume_id,
            filename=filename,
            log_context=log_context,
        ),
        max_output_tokens=1400,
    )
    raw_candidates = parsed.get("candidates")
    if not isinstance(raw_candidates, list):
        return []
    return [item for item in raw_candidates if isinstance(item, dict)]


def _verify_candidate_crop(
    *,
    client: Any,
    cfg: MissingBoxDetectionConfig,
    volume_id: str,
    filename: str,
    log_context: dict[str, Any] | None,
    attempt_index: int,
    crop_data_url: str,
) -> dict[str, Any]:
    system_prompt = (
        "You verify what is visible inside one cropped manga box image only. "
        "Do not infer text outside the crop. "
        "Return strict JSON."
    )
    user_payload = {
        "attempt_index": attempt_index,
        "instructions": [
            "Set contains_text=true only if the crop clearly includes readable text.",
            "Set fully_inside_box=true only if all characters are fully visible inside the crop.",
            "Set text_cut_off=true if any character looks clipped or cut by the crop edges.",
            "confidence must be between 0 and 1.",
            "observed_text should be what you can read from this crop only.",
        ],
    }
    input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": json.dumps(user_payload, ensure_ascii=True)},
                {"type": "input_image", "image_url": crop_data_url},
            ],
        },
    ]
    return _call_responses_json(
        client=client,
        model_id=cfg.model_id,
        input_payload=input_payload,
        text_format=_build_verify_format(),
        component="box_detection.missing_react.verify",
        context=_build_log_context(
            volume_id=volume_id,
            filename=filename,
            log_context=log_context,
        ),
        max_output_tokens=450,
    )


def _adjust_candidate_box(
    *,
    client: Any,
    cfg: MissingBoxDetectionConfig,
    volume_id: str,
    filename: str,
    log_context: dict[str, Any] | None,
    hint_text: str,
    attempt_index: int,
    image_w: int,
    image_h: int,
    page_data_url: str,
    overlay_data_url: str,
    crop_data_url: str,
    current_box: dict[str, float],
    verification_summary: dict[str, Any],
    previous_box: dict[str, float] | None,
    movement_delta: dict[str, float] | None,
    recent_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    system_prompt = (
        "You adjust one manga text box on the full page. "
        "Goal: all text must be fully inside the box, with minimal extra background. "
        "You will receive the raw page, an overlay image with the current box drawn, and the current crop. "
        "Return strict JSON."
    )
    user_payload = {
        "task": "adjust_single_text_box",
        "hint_text": hint_text,
        "attempt_index": attempt_index,
        "image_size": {"width": image_w, "height": image_h},
        "current_box": current_box,
        "previous_box": previous_box,
        "movement_delta": movement_delta,
        "recent_attempts": recent_attempts,
        "verification_summary": verification_summary,
        "instructions": [
            "Move/resize the current box so the target text is fully inside.",
            "Make the box as tight/small as possible without clipping characters.",
            "Use movement_delta and recent_attempts to reason directionally (do not jump randomly).",
            "If the previous validated box kept the whole text inside, try a slightly smaller box next.",
            "If the previous move clipped or lost text, reverse that move and make the box a bit larger.",
            "Coordinates must be in full-page coordinate space.",
            "The second image is the page with only the current proposed box drawn in red.",
            "Use that overlay image to see exactly what the current box covers before proposing new coordinates.",
        ],
    }
    input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": json.dumps(user_payload, ensure_ascii=True)},
                {"type": "input_image", "image_url": page_data_url},
                {"type": "input_image", "image_url": overlay_data_url},
                {"type": "input_image", "image_url": crop_data_url},
            ],
        },
    ]
    return _call_responses_json(
        client=client,
        model_id=cfg.model_id,
        input_payload=input_payload,
        text_format=_build_adjust_format(),
        component="box_detection.missing_react.adjust",
        context=_build_log_context(
            volume_id=volume_id,
            filename=filename,
            log_context=log_context,
        ),
        max_output_tokens=400,
    )
