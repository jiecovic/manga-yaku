# backend-python/core/usecases/box_detection/missing_react_config.py
"""Experimental support types and config normalization for missing-box ReAct."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from config import AGENT_MODEL

_MIN_BOX_EDGE_PX = 8.0
_MAX_BOX_AREA_RATIO = 0.60
_DEFAULT_MODEL_ID = AGENT_MODEL or "gpt-5-mini"
RuntimeEventCallback = Callable[[dict[str, Any]], None]
_HINT_DESCRIPTION_MARKERS = (
    "text",
    "title",
    "left",
    "right",
    "area",
    "region",
    "credits",
    "publisher",
    "author",
    "cover",
    "page",
    "volume",
)


@dataclass(frozen=True)
class MissingBoxDetectionConfig:
    model_id: str
    max_candidates: int
    max_attempts_per_candidate: int
    min_confidence: float
    overlap_iou_threshold: float
    max_image_side: int
    crop_padding_px: int


def _safe_int(value: Any, fallback: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(min_value, min(max_value, parsed))


def _safe_float(value: Any, fallback: float, *, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(min_value, min(max_value, parsed))


def _emit_runtime_event(
    callback: RuntimeEventCallback | None,
    event: dict[str, Any],
) -> None:
    if callback is None:
        return
    try:
        callback(dict(event))
    except Exception:
        # Progress telemetry must never fail the experimental detection job.
        return


def _normalize_cfg(
    *,
    model_id: str | None,
    max_candidates: int,
    max_attempts_per_candidate: int,
    min_confidence: float,
    overlap_iou_threshold: float,
    max_image_side: int,
    crop_padding_px: int,
) -> MissingBoxDetectionConfig:
    resolved_model = str(model_id or "").strip() or _DEFAULT_MODEL_ID
    return MissingBoxDetectionConfig(
        model_id=resolved_model,
        max_candidates=_safe_int(max_candidates, 8, min_value=1, max_value=40),
        max_attempts_per_candidate=_safe_int(
            max_attempts_per_candidate,
            3,
            min_value=1,
            max_value=5,
        ),
        min_confidence=_safe_float(min_confidence, 0.75, min_value=0.0, max_value=1.0),
        overlap_iou_threshold=_safe_float(
            overlap_iou_threshold,
            0.45,
            min_value=0.05,
            max_value=0.95,
        ),
        max_image_side=_safe_int(max_image_side, 1536, min_value=768, max_value=2048),
        crop_padding_px=_safe_int(crop_padding_px, 6, min_value=0, max_value=32),
    )
