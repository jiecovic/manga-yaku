# backend-python/core/usecases/box_detection/missing_react_runtime.py
"""Experimental runtime loop helpers for missing-box ReAct."""

from __future__ import annotations

from typing import Any

from .missing_react_config import (
    MissingBoxDetectionConfig,
    RuntimeEventCallback,
    _emit_runtime_event,
)
from .missing_react_geometry import (
    _box_area,
    _box_iou,
    _encode_box_overlay_data_url,
    _encode_crop_data_url,
    _normalize_candidate_bbox,
    _retry_candidate_box,
    _to_original_box,
    _to_resized_box,
)
from .missing_react_llm import _adjust_candidate_box, _verify_candidate_crop
from .missing_react_runtime_events import (
    emit_retryable_runtime_event,
    emit_retrying_event,
    record_attempt,
)
from .missing_react_runtime_support import (
    build_adjust_error_reason,
    interpret_verification,
    run_verification_step,
    split_error_reason,
    try_encode_crop_data_url,
)


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
    ) -> dict[str, Any]:
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
                        return {"box": normalized}
                adjust_error_reason = "adjust_invalid_geometry: model returned invalid box geometry"
            except Exception as exc:
                adjust_error_reason = build_adjust_error_reason(exc)
            adjust_error_kind, adjust_error_detail = split_error_reason(adjust_error_reason)
            return {
                "box": _retry_candidate_box(
                    initial_candidate_box,
                    attempt_index=next_attempt_index,
                    image_w=source_image.width,
                    image_h=source_image.height,
                ),
                "adjust_error_reason": adjust_error_reason,
                "adjust_error_kind": adjust_error_kind,
                "adjust_error_detail": adjust_error_detail,
            }
        return {
            "box": _retry_candidate_box(
                initial_candidate_box,
                attempt_index=next_attempt_index,
                image_w=source_image.width,
                image_h=source_image.height,
            )
        }

    def _emit_adjust_error(
        *,
        choose_result: dict[str, Any],
        latest_trial: dict[str, Any],
        attempt_idx: int,
        verification_reason: str,
    ) -> tuple[str | None, str | None]:
        adjust_error_kind = str(choose_result.get("adjust_error_kind") or "").strip() or None
        adjust_error_detail = str(choose_result.get("adjust_error_detail") or "").strip() or None
        if adjust_error_kind is None:
            return None, None
        latest_trial["adjust_error_kind"] = adjust_error_kind
        if adjust_error_detail is not None:
            latest_trial["adjust_error_detail"] = adjust_error_detail
        _emit_runtime_event(
            on_runtime_event,
            {
                "phase": "adjust",
                "status": "adjust_error",
                "progress": verify_progress,
                "candidate_index": candidate_index,
                "candidates_total": candidates_total,
                "attempt_index": attempt_idx,
                "next_attempt_index": min(attempt_idx + 1, cfg.max_attempts_per_candidate),
                "attempts_per_candidate": cfg.max_attempts_per_candidate,
                "hint_text": hint_text,
                "reason": verification_reason,
                "error_kind": adjust_error_kind,
                "error_detail": adjust_error_detail,
                "fallback_strategy": "heuristic_retry_candidate_box",
                "latest_trial": dict(latest_trial),
            },
        )
        return adjust_error_kind, adjust_error_detail

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
            emit_retryable_runtime_event(
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
                overlap_crop_data_url = try_encode_crop_data_url(
                    source_image=source_image,
                    attempt_box=attempt_box,
                    crop_padding_px=cfg.crop_padding_px,
                    encode_crop_data_url_fn=_encode_crop_data_url,
                )
                choose_result = _choose_next_box(
                    current_box=attempt_box,
                    crop_data_url=overlap_crop_data_url,
                    next_attempt_index=attempt_idx + 1,
                    verification_summary={"status": "overlap_skip", "reason": failure_reason},
                    previous_box=previous_attempt_box,
                    movement_delta=movement_delta,
                )
                next_override_box = dict(choose_result["box"])
                adjust_error_kind, adjust_error_detail = _emit_adjust_error(
                    choose_result=choose_result,
                    latest_trial=latest_trial,
                    attempt_idx=attempt_idx,
                    verification_reason=failure_reason,
                )
                record_attempt(
                    attempt_history,
                    attempt_idx,
                    attempt_box,
                    status="overlap_skip",
                    reason=failure_reason,
                    adjust_error_kind=adjust_error_kind,
                    adjust_error_detail=adjust_error_detail,
                )
                emit_retrying_event(
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

        crop_data_url, verification, failure_reason = run_verification_step(
            client=client,
            cfg=cfg,
            volume_id=volume_id,
            filename=filename,
            source_image=source_image,
            attempt_box=attempt_box,
            attempt_idx=attempt_idx,
            encode_crop_data_url_fn=_encode_crop_data_url,
            verify_candidate_crop_fn=_verify_candidate_crop,
        )
        error_kind = None
        error_detail = None
        if verification is None:
            error_kind, error_detail = split_error_reason(failure_reason)
            emit_retryable_runtime_event(
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
                choose_result = _choose_next_box(
                    current_box=attempt_box,
                    crop_data_url=crop_data_url,
                    next_attempt_index=attempt_idx + 1,
                    verification_summary={"status": "verification_error", "reason": failure_reason},
                    previous_box=previous_attempt_box,
                    movement_delta=movement_delta,
                )
                next_override_box = dict(choose_result["box"])
                adjust_error_kind, adjust_error_detail = _emit_adjust_error(
                    choose_result=choose_result,
                    latest_trial=latest_trial,
                    attempt_idx=attempt_idx,
                    verification_reason=failure_reason,
                )
                record_attempt(
                    attempt_history,
                    attempt_idx,
                    attempt_box,
                    status="verification_error",
                    reason=failure_reason,
                    error_kind=error_kind,
                    error_detail=error_detail,
                    adjust_error_kind=adjust_error_kind,
                    adjust_error_detail=adjust_error_detail,
                )
                emit_retrying_event(
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

        verdict = interpret_verification(
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
                choose_result = _choose_next_box(
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
                next_override_box = dict(choose_result["box"])
                adjust_error_kind, adjust_error_detail = _emit_adjust_error(
                    choose_result=choose_result,
                    latest_trial=latest_trial,
                    attempt_idx=attempt_idx,
                    verification_reason="try_smaller_box_keep_text_inside",
                )
                emit_retrying_event(
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
                record_attempt(
                    attempt_history,
                    attempt_idx,
                    attempt_box,
                    status="candidate_valid",
                fully_inside_box=verdict["fully_inside_box"],
                text_cut_off=verdict["text_cut_off"],
                    verify_confidence=verdict["confidence"],
                    verified_text=observed_text,
                    validated_area=round(candidate_area, 3),
                    adjust_error_kind=adjust_error_kind,
                    adjust_error_detail=adjust_error_detail,
                )
                previous_attempt_box = dict(attempt_box)
                continue

        if best_box is not None:
            break

        if attempt_idx < cfg.max_attempts_per_candidate:
            choose_result = _choose_next_box(
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
            next_override_box = dict(choose_result["box"])
            adjust_error_kind, adjust_error_detail = _emit_adjust_error(
                choose_result=choose_result,
                latest_trial=latest_trial,
                attempt_idx=attempt_idx,
                verification_reason=failure_reason,
            )
            emit_retrying_event(
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
            record_attempt(
                attempt_history,
                attempt_idx,
                attempt_box,
                status="rejected_candidate",
                reason=failure_reason,
                fully_inside_box=verdict["fully_inside_box"],
                text_cut_off=verdict["text_cut_off"],
                verify_confidence=verdict["confidence"],
                verified_text=observed_text,
                adjust_error_kind=adjust_error_kind,
                adjust_error_detail=adjust_error_detail,
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
