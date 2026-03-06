# backend-python/core/usecases/box_detection/missing_react_runtime_events.py
"""Runtime event helpers for the experimental missing-box loop."""

from __future__ import annotations

from typing import Any

from .missing_react_config import RuntimeEventCallback, _emit_runtime_event


def record_attempt(
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



def emit_retryable_runtime_event(
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



def emit_retrying_event(
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
