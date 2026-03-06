# backend-python/core/usecases/box_detection/missing_react_runtime.py
"""Experimental runtime loop helpers for missing-box ReAct."""

from __future__ import annotations

import json
from typing import Any

from .missing_react_config import (
    MissingBoxDetectionConfig,
    RuntimeEventCallback,
    _emit_runtime_event,
    _safe_float,
)
from .missing_react_geometry import (
    _box_area,
    _box_iou,
    _encode_box_overlay_data_url,
    _encode_crop_data_url,
    _hint_looks_like_literal_text,
    _is_useful_observed_text,
    _normalize_candidate_bbox,
    _observed_matches_hint,
    _retry_candidate_box,
    _to_original_box,
    _to_resized_box,
)
from .missing_react_llm import _adjust_candidate_box, _verify_candidate_crop


def _normalize_candidates(
    *,
    cfg: MissingBoxDetectionConfig,
    proposed_raw: list[dict[str, Any]],
    source_image_size: tuple[int, int],
    resized_image_size: tuple[int, int],
    scale_x: float,
    scale_y: float,
    dedupe_anchor_boxes: list[dict[str, float]],
) -> list[dict[str, Any]]:
    source_w, source_h = source_image_size
    resized_w, resized_h = resized_image_size
    normalized_candidates: list[dict[str, Any]] = []
    for item in proposed_raw:
        if len(normalized_candidates) >= cfg.max_candidates:
            break
        resized_box = _normalize_candidate_bbox(
            x=item.get("x"),
            y=item.get("y"),
            width=item.get("width"),
            height=item.get("height"),
            image_w=resized_w,
            image_h=resized_h,
        )
        if resized_box is None:
            continue
        original_box = _to_original_box(resized_box, scale_x=scale_x, scale_y=scale_y)
        original_box = _normalize_candidate_bbox(
            x=original_box["x"],
            y=original_box["y"],
            width=original_box["width"],
            height=original_box["height"],
            image_w=source_w,
            image_h=source_h,
        )
        if original_box is None:
            continue
        if any(_box_iou(original_box, seen) >= cfg.overlap_iou_threshold for seen in dedupe_anchor_boxes):
            continue
        dedupe_anchor_boxes.append(original_box)
        normalized_candidates.append(
            {
                "hint_text": str(item.get("hint_text") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
                "box": original_box,
            }
        )
    return normalized_candidates


# Experimental: this is the unstable per-candidate loop we expect to keep
# iterating on while the prompt and verifier behavior settle down.
def _evaluate_candidate(
    *,
    client: Any,
    cfg: MissingBoxDetectionConfig,
    volume_id: str,
    filename: str,
    source_image: Any,
    resized_image: Any,
    page_data_url: str,
    scale_x: float,
    scale_y: float,
    occupancy_boxes: list[dict[str, float]],
    candidate: dict[str, Any],
    candidate_index: int,
    candidates_total: int,
    attempt_step_index: int,
    total_attempt_steps: int,
    on_runtime_event: RuntimeEventCallback | None,
) -> dict[str, Any]:
    hint_text = str(candidate.get("hint_text") or "").strip()
    initial_candidate_box = dict(candidate["box"])
    attempt_box = dict(initial_candidate_box)
    failure_reason = "not_verified"
    observed_text = ""
    confidence = 0.0
    best_box: dict[str, float] | None = None
    best_observed_text = ""
    best_confidence = 0.0
    best_attempt_index = 0
    best_box_area: float | None = None
    next_override_box: dict[str, float] | None = None
    attempt_history: list[dict[str, Any]] = []
    previous_attempt_box: dict[str, float] | None = None
    verify_progress = 20

    def _choose_next_box(
        *,
        current_box: dict[str, float],
        crop_data_url: str | None,
        next_attempt_index: int,
        verification_summary: dict[str, Any],
        previous_box: dict[str, float] | None,
        movement_delta: dict[str, float] | None,
    ) -> dict[str, float]:
        if crop_data_url:
            try:
                current_box_resized = _to_resized_box(current_box, scale_x=scale_x, scale_y=scale_y)
                previous_box_resized = (
                    _to_resized_box(previous_box, scale_x=scale_x, scale_y=scale_y)
                    if previous_box is not None
                    else None
                )
                overlay_data_url = _encode_box_overlay_data_url(
                    image=resized_image,
                    current_box=current_box_resized,
                    max_side=max(resized_image.width, resized_image.height),
                )
                adjusted = _adjust_candidate_box(
                    client=client,
                    cfg=cfg,
                    volume_id=volume_id,
                    filename=filename,
                    hint_text=hint_text,
                    attempt_index=next_attempt_index,
                    image_w=resized_image.width,
                    image_h=resized_image.height,
                    page_data_url=page_data_url,
                    overlay_data_url=overlay_data_url,
                    crop_data_url=crop_data_url,
                    current_box=current_box_resized,
                    verification_summary=verification_summary,
                    previous_box=previous_box_resized,
                    movement_delta=movement_delta,
                    recent_attempts=attempt_history[-6:],
                )
                adjusted_resized = _normalize_candidate_bbox(
                    x=adjusted.get("x"),
                    y=adjusted.get("y"),
                    width=adjusted.get("width"),
                    height=adjusted.get("height"),
                    image_w=resized_image.width,
                    image_h=resized_image.height,
                )
                if adjusted_resized is not None:
                    adjusted_original = _to_original_box(
                        adjusted_resized,
                        scale_x=scale_x,
                        scale_y=scale_y,
                    )
                    normalized = _normalize_candidate_bbox(
                        x=adjusted_original["x"],
                        y=adjusted_original["y"],
                        width=adjusted_original["width"],
                        height=adjusted_original["height"],
                        image_w=source_image.width,
                        image_h=source_image.height,
                    )
                    if normalized is not None:
                        return normalized
            except Exception:
                pass
        return _retry_candidate_box(
            initial_candidate_box,
            attempt_index=next_attempt_index,
            image_w=source_image.width,
            image_h=source_image.height,
        )

    for attempt_idx in range(1, cfg.max_attempts_per_candidate + 1):
        if next_override_box is not None:
            attempt_box = dict(next_override_box)
            next_override_box = None
        else:
            attempt_box = _retry_candidate_box(
                initial_candidate_box,
                attempt_index=attempt_idx,
                image_w=source_image.width,
                image_h=source_image.height,
            )
        movement_delta = None
        if previous_attempt_box is not None:
            movement_delta = {
                "dx": round(float(attempt_box["x"]) - float(previous_attempt_box["x"]), 3),
                "dy": round(float(attempt_box["y"]) - float(previous_attempt_box["y"]), 3),
                "dw": round(float(attempt_box["width"]) - float(previous_attempt_box["width"]), 3),
                "dh": round(float(attempt_box["height"]) - float(previous_attempt_box["height"]), 3),
            }
        attempt_step_index += 1
        verify_progress = 20 + int((attempt_step_index / total_attempt_steps) * 70)
        latest_trial = {
            "x": float(attempt_box["x"]),
            "y": float(attempt_box["y"]),
            "width": float(attempt_box["width"]),
            "height": float(attempt_box["height"]),
            "status": "attempting",
            "candidate_index": candidate_index,
            "candidates_total": candidates_total,
            "attempt_index": attempt_idx,
            "attempts_per_candidate": cfg.max_attempts_per_candidate,
            "hint_text": hint_text,
        }
        _emit_runtime_event(
            on_runtime_event,
            {
                "phase": "verify",
                "status": "attempting",
                "progress": verify_progress,
                "candidate_index": candidate_index,
                "candidates_total": candidates_total,
                "attempt_index": attempt_idx,
                "attempts_per_candidate": cfg.max_attempts_per_candidate,
                "hint_text": hint_text,
                "latest_trial": latest_trial,
            },
        )
        if any(_box_iou(attempt_box, occupied) >= cfg.overlap_iou_threshold for occupied in occupancy_boxes):
            failure_reason = "overlaps_existing_coverage"
            _emit_retryable_runtime_event(
                on_runtime_event=on_runtime_event,
                verify_progress=verify_progress,
                candidate_index=candidate_index,
                candidates_total=candidates_total,
                attempt_idx=attempt_idx,
                attempts_per_candidate=cfg.max_attempts_per_candidate,
                hint_text=hint_text,
                status="overlap_skip",
                reason=failure_reason,
                latest_trial=latest_trial,
            )
            if attempt_idx < cfg.max_attempts_per_candidate:
                overlap_crop_data_url = _try_encode_crop_data_url(
                    source_image=source_image,
                    attempt_box=attempt_box,
                    crop_padding_px=cfg.crop_padding_px,
                )
                next_override_box = _choose_next_box(
                    current_box=attempt_box,
                    crop_data_url=overlap_crop_data_url,
                    next_attempt_index=attempt_idx + 1,
                    verification_summary={"status": "overlap_skip", "reason": failure_reason},
                    previous_box=previous_attempt_box,
                    movement_delta=movement_delta,
                )
                _record_attempt(
                    attempt_history,
                    attempt_idx,
                    attempt_box,
                    status="overlap_skip",
                    reason=failure_reason,
                )
                _emit_retrying_event(
                    on_runtime_event=on_runtime_event,
                    verify_progress=verify_progress,
                    candidate_index=candidate_index,
                    candidates_total=candidates_total,
                    attempt_idx=attempt_idx,
                    attempts_per_candidate=cfg.max_attempts_per_candidate,
                    hint_text=hint_text,
                    reason=failure_reason,
                    latest_trial=latest_trial,
                )
                previous_attempt_box = dict(attempt_box)
                continue
            break

        crop_data_url, verification, failure_reason = _run_verification_step(
            client=client,
            cfg=cfg,
            volume_id=volume_id,
            filename=filename,
            source_image=source_image,
            attempt_box=attempt_box,
            attempt_idx=attempt_idx,
        )
        error_kind = None
        error_detail = None
        if verification is None:
            error_kind, error_detail = _split_error_reason(failure_reason)
            _emit_retryable_runtime_event(
                on_runtime_event=on_runtime_event,
                verify_progress=verify_progress,
                candidate_index=candidate_index,
                candidates_total=candidates_total,
                attempt_idx=attempt_idx,
                attempts_per_candidate=cfg.max_attempts_per_candidate,
                hint_text=hint_text,
                status="verification_error",
                reason=failure_reason,
                latest_trial=latest_trial,
                error_kind=error_kind,
                error_detail=error_detail,
            )
            if attempt_idx < cfg.max_attempts_per_candidate:
                next_override_box = _choose_next_box(
                    current_box=attempt_box,
                    crop_data_url=crop_data_url,
                    next_attempt_index=attempt_idx + 1,
                    verification_summary={"status": "verification_error", "reason": failure_reason},
                    previous_box=previous_attempt_box,
                    movement_delta=movement_delta,
                )
                _record_attempt(
                    attempt_history,
                    attempt_idx,
                    attempt_box,
                    status="verification_error",
                    reason=failure_reason,
                    error_kind=error_kind,
                    error_detail=error_detail,
                )
                _emit_retrying_event(
                    on_runtime_event=on_runtime_event,
                    verify_progress=verify_progress,
                    candidate_index=candidate_index,
                    candidates_total=candidates_total,
                    attempt_idx=attempt_idx,
                    attempts_per_candidate=cfg.max_attempts_per_candidate,
                    hint_text=hint_text,
                    reason=failure_reason,
                    latest_trial=latest_trial,
                    error_kind=error_kind,
                    error_detail=error_detail,
                )
                previous_attempt_box = dict(attempt_box)
                continue
            break

        verdict = _interpret_verification(
            cfg=cfg,
            hint_text=hint_text,
            verification=verification,
            latest_trial=latest_trial,
        )
        failure_reason = verdict["failure_reason"]
        observed_text = verdict["observed_text"]
        confidence = verdict["confidence"]

        if verdict["likely_valid"] and verdict["hint_match_ok"]:
            candidate_area = _box_area(attempt_box)
            is_better = best_box_area is None or candidate_area < best_box_area
            if is_better:
                best_box = dict(attempt_box)
                best_observed_text = observed_text
                best_confidence = confidence
                best_attempt_index = attempt_idx
                best_box_area = candidate_area
            latest_trial["status"] = "candidate_valid"
            _emit_runtime_event(
                on_runtime_event,
                {
                    "phase": "verify",
                    "status": "candidate_valid",
                    "progress": verify_progress,
                    "candidate_index": candidate_index,
                    "candidates_total": candidates_total,
                    "attempt_index": attempt_idx,
                    "attempts_per_candidate": cfg.max_attempts_per_candidate,
                    "hint_text": hint_text,
                    "fully_inside_box": verdict["fully_inside_box"],
                    "text_cut_off": verdict["text_cut_off"],
                    "verify_confidence": verdict["confidence"],
                    "verified_text": observed_text,
                    "best_validated_so_far": is_better,
                    "validated_area": round(candidate_area, 3),
                    "latest_trial": latest_trial,
                },
            )
            if attempt_idx < cfg.max_attempts_per_candidate:
                next_override_box = _choose_next_box(
                    current_box=attempt_box,
                    crop_data_url=crop_data_url,
                    next_attempt_index=attempt_idx + 1,
                    verification_summary={
                        "status": "candidate_valid",
                        "reason": "try_smaller_box_keep_text_inside",
                        "fully_inside_box": verdict["fully_inside_box"],
                        "text_cut_off": verdict["text_cut_off"],
                        "confidence": verdict["confidence"],
                        "observed_text": observed_text,
                    },
                    previous_box=previous_attempt_box,
                    movement_delta=movement_delta,
                )
                _emit_retrying_event(
                    on_runtime_event=on_runtime_event,
                    verify_progress=verify_progress,
                    candidate_index=candidate_index,
                    candidates_total=candidates_total,
                    attempt_idx=attempt_idx,
                    attempts_per_candidate=cfg.max_attempts_per_candidate,
                    hint_text=hint_text,
                    reason="try_smaller_box_keep_text_inside",
                    latest_trial=latest_trial,
                    fully_inside_box=verdict["fully_inside_box"],
                    text_cut_off=verdict["text_cut_off"],
                    verify_confidence=verdict["confidence"],
                    verified_text=observed_text,
                )
            _record_attempt(
                attempt_history,
                attempt_idx,
                attempt_box,
                status="candidate_valid",
                fully_inside_box=verdict["fully_inside_box"],
                text_cut_off=verdict["text_cut_off"],
                verify_confidence=verdict["confidence"],
                verified_text=observed_text,
                validated_area=round(candidate_area, 3),
            )
            previous_attempt_box = dict(attempt_box)
            continue

        if best_box is not None:
            break

        if attempt_idx < cfg.max_attempts_per_candidate:
            next_override_box = _choose_next_box(
                current_box=attempt_box,
                crop_data_url=crop_data_url,
                next_attempt_index=attempt_idx + 1,
                verification_summary={
                    "status": "rejected_candidate",
                    "reason": failure_reason,
                    "fully_inside_box": verdict["fully_inside_box"],
                    "text_cut_off": verdict["text_cut_off"],
                    "confidence": verdict["confidence"],
                    "observed_text": observed_text,
                },
                previous_box=previous_attempt_box,
                movement_delta=movement_delta,
            )
            _emit_retrying_event(
                on_runtime_event=on_runtime_event,
                verify_progress=verify_progress,
                candidate_index=candidate_index,
                candidates_total=candidates_total,
                attempt_idx=attempt_idx,
                attempts_per_candidate=cfg.max_attempts_per_candidate,
                hint_text=hint_text,
                reason=failure_reason,
                latest_trial=latest_trial,
                fully_inside_box=verdict["fully_inside_box"],
                text_cut_off=verdict["text_cut_off"],
                verify_confidence=verdict["confidence"],
                verified_text=observed_text,
            )
            _record_attempt(
                attempt_history,
                attempt_idx,
                attempt_box,
                status="rejected_candidate",
                reason=failure_reason,
                fully_inside_box=verdict["fully_inside_box"],
                text_cut_off=verdict["text_cut_off"],
                verify_confidence=verdict["confidence"],
                verified_text=observed_text,
            )
            previous_attempt_box = dict(attempt_box)

    if best_box is not None:
        _emit_runtime_event(
            on_runtime_event,
            {
                "phase": "verify",
                "status": "accepted",
                "progress": min(99, verify_progress + 1),
                "candidate_index": candidate_index,
                "candidates_total": candidates_total,
                "attempt_index": best_attempt_index,
                "attempts_per_candidate": cfg.max_attempts_per_candidate,
                "hint_text": hint_text,
                "verify_confidence": best_confidence,
                "verified_text": best_observed_text,
                "latest_trial": {
                    "x": float(best_box["x"]),
                    "y": float(best_box["y"]),
                    "width": float(best_box["width"]),
                    "height": float(best_box["height"]),
                    "status": "accepted",
                    "candidate_index": candidate_index,
                    "candidates_total": candidates_total,
                    "attempt_index": best_attempt_index,
                    "attempts_per_candidate": cfg.max_attempts_per_candidate,
                    "hint_text": hint_text,
                    "verify_confidence": best_confidence,
                    "verified_text": best_observed_text,
                    "reason": "accepted_smallest_validated_box",
                },
            },
        )
        return {
            "accepted": True,
            "accepted_spec": {
                "x": float(best_box["x"]),
                "y": float(best_box["y"]),
                "width": float(best_box["width"]),
                "height": float(best_box["height"]),
                "hint_text": hint_text,
                "verified_text": best_observed_text,
                "verify_confidence": best_confidence,
            },
            "best_box": best_box,
            "attempt_step_index": attempt_step_index,
            "progress": verify_progress,
        }

    _emit_runtime_event(
        on_runtime_event,
        {
            "phase": "verify",
            "status": "rejected",
            "progress": verify_progress,
            "candidate_index": candidate_index,
            "candidates_total": candidates_total,
            "attempt_index": cfg.max_attempts_per_candidate,
            "attempts_per_candidate": cfg.max_attempts_per_candidate,
            "hint_text": hint_text,
            "verify_confidence": confidence,
            "verified_text": observed_text,
            "reason": failure_reason,
            "latest_trial": {
                "x": float(attempt_box["x"]),
                "y": float(attempt_box["y"]),
                "width": float(attempt_box["width"]),
                "height": float(attempt_box["height"]),
                "status": "rejected",
                "candidate_index": candidate_index,
                "candidates_total": candidates_total,
                "attempt_index": cfg.max_attempts_per_candidate,
                "attempts_per_candidate": cfg.max_attempts_per_candidate,
                "hint_text": hint_text,
                "verify_confidence": confidence,
                "verified_text": observed_text,
                "reason": failure_reason,
            },
        },
    )
    return {
        "accepted": False,
        "rejected_spec": {
            "hint_text": hint_text,
            "reason": failure_reason,
            "verified_text": observed_text,
            "verify_confidence": confidence,
        },
        "attempt_step_index": attempt_step_index,
        "progress": verify_progress,
    }


def _try_encode_crop_data_url(
    *,
    source_image: Any,
    attempt_box: dict[str, float],
    crop_padding_px: int,
) -> str | None:
    try:
        return _encode_crop_data_url(
            image=source_image,
            box=attempt_box,
            padding_px=crop_padding_px,
        )
    except Exception:
        return None


def _run_verification_step(
    *,
    client: Any,
    cfg: MissingBoxDetectionConfig,
    volume_id: str,
    filename: str,
    source_image: Any,
    attempt_box: dict[str, float],
    attempt_idx: int,
) -> tuple[str | None, dict[str, Any] | None, str]:
    crop_data_url: str | None = None
    try:
        crop_data_url = _encode_crop_data_url(
            image=source_image,
            box=attempt_box,
            padding_px=cfg.crop_padding_px,
        )
        verification = _verify_candidate_crop(
            client=client,
            cfg=cfg,
            volume_id=volume_id,
            filename=filename,
            attempt_index=attempt_idx,
            crop_data_url=crop_data_url,
        )
        return crop_data_url, verification, ""
    except Exception as exc:
        failure_reason = _build_verification_error_reason(exc)
        return crop_data_url, None, failure_reason


def _build_verification_error_reason(exc: Exception) -> str:
    error_kind = _classify_verification_error(exc)
    detail = str(exc).strip() or exc.__class__.__name__
    detail = " ".join(detail.split())
    if len(detail) > 180:
        detail = detail[:177] + "..."
    return f"{error_kind}: {detail}"


def _split_error_reason(reason: str) -> tuple[str | None, str | None]:
    text = str(reason or "").strip()
    if not text:
        return None, None
    if ": " not in text:
        return text, None
    error_kind, error_detail = text.split(": ", 1)
    return error_kind.strip() or None, error_detail.strip() or None


def _classify_verification_error(exc: Exception) -> str:
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


def _interpret_verification(
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


def _record_attempt(
    attempt_history: list[dict[str, Any]],
    attempt_idx: int,
    attempt_box: dict[str, float],
    **details: Any,
) -> None:
    attempt_history.append(
        {
            "attempt_index": attempt_idx,
            "x": float(attempt_box["x"]),
            "y": float(attempt_box["y"]),
            "width": float(attempt_box["width"]),
            "height": float(attempt_box["height"]),
            **details,
        }
    )


def _emit_retryable_runtime_event(
    *,
    on_runtime_event: RuntimeEventCallback | None,
    verify_progress: int,
    candidate_index: int,
    candidates_total: int,
    attempt_idx: int,
    attempts_per_candidate: int,
    hint_text: str,
    status: str,
    reason: str,
    latest_trial: dict[str, Any],
    error_kind: str | None = None,
    error_detail: str | None = None,
) -> None:
    latest_trial["status"] = status
    latest_trial["reason"] = reason
    if error_kind is not None:
        latest_trial["error_kind"] = error_kind
    if error_detail is not None:
        latest_trial["error_detail"] = error_detail
    _emit_runtime_event(
        on_runtime_event,
        {
            "phase": "verify",
            "status": status,
            "progress": verify_progress,
            "candidate_index": candidate_index,
            "candidates_total": candidates_total,
            "attempt_index": attempt_idx,
            "attempts_per_candidate": attempts_per_candidate,
            "hint_text": hint_text,
            "reason": reason,
            "error_kind": error_kind,
            "error_detail": error_detail,
            "latest_trial": latest_trial,
        },
    )


def _emit_retrying_event(
    *,
    on_runtime_event: RuntimeEventCallback | None,
    verify_progress: int,
    candidate_index: int,
    candidates_total: int,
    attempt_idx: int,
    attempts_per_candidate: int,
    hint_text: str,
    reason: str,
    latest_trial: dict[str, Any],
    error_kind: str | None = None,
    error_detail: str | None = None,
    fully_inside_box: bool | None = None,
    text_cut_off: bool | None = None,
    verify_confidence: float | None = None,
    verified_text: str | None = None,
) -> None:
    latest_trial["status"] = "retrying"
    if error_kind is not None:
        latest_trial["error_kind"] = error_kind
    if error_detail is not None:
        latest_trial["error_detail"] = error_detail
    payload: dict[str, Any] = {
        "phase": "verify",
        "status": "retrying",
        "progress": verify_progress,
        "candidate_index": candidate_index,
        "candidates_total": candidates_total,
        "attempt_index": attempt_idx,
        "attempts_per_candidate": attempts_per_candidate,
        "hint_text": hint_text,
        "reason": reason,
        "error_kind": error_kind,
        "error_detail": error_detail,
        "latest_trial": latest_trial,
    }
    if fully_inside_box is not None:
        payload["fully_inside_box"] = fully_inside_box
    if text_cut_off is not None:
        payload["text_cut_off"] = text_cut_off
    if verify_confidence is not None:
        payload["verify_confidence"] = verify_confidence
    if verified_text is not None:
        payload["verified_text"] = verified_text
    _emit_runtime_event(on_runtime_event, payload)
