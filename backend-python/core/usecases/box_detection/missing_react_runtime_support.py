# backend-python/core/usecases/box_detection/missing_react_runtime_support.py
"""Support helpers for the experimental missing-box runtime loop."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .missing_react_config import MissingBoxDetectionConfig, _safe_float
from .missing_react_geometry import (
    _hint_looks_like_literal_text,
    _is_useful_observed_text,
    _observed_matches_hint,
)


def try_encode_crop_data_url(
    *,
    source_image: Any,
    attempt_box: dict[str, float],
    crop_padding_px: int,
    encode_crop_data_url_fn: Callable[..., str],
) -> str | None:
    try:
        return encode_crop_data_url_fn(
            image=source_image,
            box=attempt_box,
            padding_px=crop_padding_px,
        )
    except Exception:
        return None



def run_verification_step(
    *,
    client: Any,
    cfg: MissingBoxDetectionConfig,
    volume_id: str,
    filename: str,
    log_context: dict[str, Any] | None,
    source_image: Any,
    attempt_box: dict[str, float],
    attempt_idx: int,
    encode_crop_data_url_fn: Callable[..., str],
    verify_candidate_crop_fn: Callable[..., dict[str, Any]],
) -> tuple[str | None, dict[str, Any] | None, str]:
    crop_data_url: str | None = None
    try:
        crop_data_url = encode_crop_data_url_fn(
            image=source_image,
            box=attempt_box,
            padding_px=cfg.crop_padding_px,
        )
        verification = verify_candidate_crop_fn(
            client=client,
            cfg=cfg,
            volume_id=volume_id,
            filename=filename,
            log_context=log_context,
            attempt_index=attempt_idx,
            crop_data_url=crop_data_url,
        )
        return crop_data_url, verification, ""
    except Exception as exc:
        failure_reason = build_verification_error_reason(exc)
        return crop_data_url, None, failure_reason



def build_verification_error_reason(exc: Exception) -> str:
    error_kind = classify_model_step_error(exc)
    detail = str(exc).strip() or exc.__class__.__name__
    detail = " ".join(detail.split())
    if len(detail) > 180:
        detail = detail[:177] + "..."
    return f"{error_kind}: {detail}"



def build_adjust_error_reason(exc: Exception) -> str:
    error_kind = classify_model_step_error(exc)
    detail = str(exc).strip() or exc.__class__.__name__
    detail = " ".join(detail.split())
    if len(detail) > 180:
        detail = detail[:177] + "..."
    return f"{error_kind}: {detail}"



def split_error_reason(reason: str) -> tuple[str | None, str | None]:
    text = str(reason or "").strip()
    if not text:
        return None, None
    if ": " not in text:
        return text, None
    error_kind, error_detail = text.split(": ", 1)
    return error_kind.strip() or None, error_detail.strip() or None



def classify_model_step_error(exc: Exception) -> str:
    text = str(exc).strip().lower()
    type_name = exc.__class__.__name__.lower()
    module_name = exc.__class__.__module__.lower()

    if isinstance(exc, json.JSONDecodeError):
        return "schema_parse_error"
    if text.startswith("model refusal:") or "refusal" in text:
        return "model_refusal"
    if "invalid crop bounds" in text:
        return "crop_bounds_error"
    if (
        "no json object found" in text
        or "model response json" in text
        or "empty model response" in text
        or "expecting value" in text
        or "expecting ',' delimiter" in text
    ):
        return "schema_parse_error"
    if "openai" in module_name or type_name.endswith("error"):
        if "timeout" in text or "timed out" in text:
            return "provider_timeout"
        return "provider_error"
    return "verification_runtime_error"



def interpret_verification(
    *,
    cfg: MissingBoxDetectionConfig,
    hint_text: str,
    verification: dict[str, Any],
    latest_trial: dict[str, Any],
) -> dict[str, Any]:
    contains_text = bool(verification.get("contains_text"))
    fully_inside_box = bool(verification.get("fully_inside_box"))
    text_cut_off = bool(verification.get("text_cut_off"))
    if not text_cut_off and contains_text and not fully_inside_box:
        text_cut_off = True
    confidence = _safe_float(verification.get("confidence"), 0.0, min_value=0.0, max_value=1.0)
    observed_text = str(verification.get("observed_text") or "").strip()
    failure_reason = str(verification.get("reason") or "").strip() or "rejected_by_verifier"

    latest_trial["fully_inside_box"] = fully_inside_box
    latest_trial["text_cut_off"] = text_cut_off
    latest_trial["verify_confidence"] = confidence
    latest_trial["verified_text"] = observed_text
    latest_trial["reason"] = failure_reason

    observed_text_ok = _is_useful_observed_text(observed_text)
    hint_match_required = _hint_looks_like_literal_text(hint_text)
    hint_match_ok = (not hint_match_required) or _observed_matches_hint(hint_text, observed_text)
    if not observed_text_ok:
        failure_reason = "observed_text_too_weak"
        latest_trial["reason"] = failure_reason
    if hint_match_required and not hint_match_ok:
        failure_reason = "hint_mismatch"
        latest_trial["reason"] = failure_reason

    likely_valid = (
        contains_text
        and fully_inside_box
        and not text_cut_off
        and confidence >= cfg.min_confidence
        and observed_text_ok
    )
    return {
        "contains_text": contains_text,
        "fully_inside_box": fully_inside_box,
        "text_cut_off": text_cut_off,
        "confidence": confidence,
        "observed_text": observed_text,
        "failure_reason": failure_reason,
        "likely_valid": likely_valid,
        "hint_match_ok": hint_match_ok,
    }
