# backend-python/core/usecases/box_detection/runtime/engine.py
"""Primary orchestration logic for box detection operations."""

from __future__ import annotations

import logging
from typing import Any

from infra.db.store_boxes import create_detection_run, replace_boxes_for_type
from infra.db.store_volume_page import load_page

from ..profiles.registry import (
    get_box_detection_profile,
    pick_default_box_detection_profile_id,
)
from .inference import (
    CancelCallback,
    load_page_image,
    normalize_task,
    resolve_allowed_classes,
    resolve_detection_thresholds,
    run_yolo_on_image,
    should_abort,
)
from .model_runtime import get_model_hash, resolve_model_path
from .postprocess import (
    filter_boxes_overlapping_existing,
    resolve_containment_threshold,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_boxes_for_page(
    volume_id: str,
    filename: str,
    profile_id: str | None = None,
    *,
    task: str | None = None,
    replace_existing: bool = True,
    is_canceled: CancelCallback | None = None,
) -> list[dict[str, Any]]:
    """Run persisted box detection for one page and return the created boxes.

    The function is intentionally the box-detection equivalent of a usecase
    entry point:

    - resolve the effective detection profile
    - load the page image and run YOLO inference
    - create a detection-run audit row
    - either replace existing boxes or append only non-overlapping new boxes

    `replace_existing=False` is the safe/default-preserve mode used by the
    agent and page-translation flows. `replace_existing=True` remains the
    explicit rebuild mode when a full refresh is intended.
    """
    if profile_id is None:
        profile_id = pick_default_box_detection_profile_id()
    if not profile_id:
        raise RuntimeError(
            "No box detection models available. Train a model first to enable detection."
        )

    profile = get_box_detection_profile(profile_id)
    if not profile.get("enabled", True):
        raise RuntimeError(f"Box detection profile '{profile_id}' is disabled or unavailable")

    normalized_task = normalize_task(task) or "text"

    if should_abort(is_canceled):
        return []

    img = load_page_image(volume_id, filename)
    if should_abort(is_canceled):
        return []

    allowed_classes = resolve_allowed_classes(profile, normalized_task)
    detections = run_yolo_on_image(img, profile, allowed_classes=allowed_classes)
    if should_abort(is_canceled):
        return []

    model_path = resolve_model_path(profile)
    model_hash = get_model_hash(model_path)
    cfg = profile.get("config", {}) or {}
    conf_th, iou_th = resolve_detection_thresholds(profile)
    containment_th = resolve_containment_threshold(profile)
    model_version = cfg.get("model_version") or cfg.get("version")
    if should_abort(is_canceled):
        return []
    run_id = create_detection_run(
        volume_id,
        filename,
        task=normalized_task,
        model_id=profile.get("id", profile_id),
        model_label=profile.get("label"),
        model_version=str(model_version) if model_version is not None else None,
        model_path=str(model_path) if model_path else None,
        model_hash=model_hash,
        params={
            "conf_threshold": conf_th,
            "iou_threshold": iou_th,
            "containment_threshold": containment_th,
            "allowed_classes": allowed_classes,
            "class_names": cfg.get("class_names"),
        },
    )

    if not detections:
        if replace_existing:
            replace_boxes_for_type(
                volume_id,
                filename,
                box_type=normalized_task,
                boxes=[],
                run_id=run_id,
                replace_existing=True,
            )
        return []

    new_boxes = [
        {
            "x": det["x"],
            "y": det["y"],
            "width": det["width"],
            "height": det["height"],
        }
        for det in detections
    ]
    if should_abort(is_canceled):
        return []

    if not replace_existing:
        page = load_page(volume_id, filename)
        raw_boxes = page.get("boxes", []) if isinstance(page, dict) else []
        existing_boxes = [
            {
                "x": float(box.get("x") or 0.0),
                "y": float(box.get("y") or 0.0),
                "width": float(box.get("width") or 0.0),
                "height": float(box.get("height") or 0.0),
            }
            for box in raw_boxes
            if isinstance(box, dict)
            and str(box.get("type") or "").strip().lower() == normalized_task
        ]
        new_boxes = filter_boxes_overlapping_existing(
            new_boxes,
            existing_boxes=existing_boxes,
            threshold=containment_th,
        )

    if replace_existing:
        return replace_boxes_for_type(
            volume_id,
            filename,
            box_type=normalized_task,
            boxes=new_boxes,
            run_id=run_id,
            replace_existing=True,
        )

    return replace_boxes_for_type(
        volume_id,
        filename,
        box_type=normalized_task,
        boxes=new_boxes,
        run_id=run_id,
        source="detect",
        replace_existing=False,
    )


def detect_text_boxes_for_page(
    volume_id: str,
    filename: str,
    profile_id: str | None = None,
    *,
    replace_existing: bool = True,
    is_canceled: CancelCallback | None = None,
) -> list[dict[str, Any]]:
    """Convenience wrapper for the common `task="text"` detection path."""
    return detect_boxes_for_page(
        volume_id=volume_id,
        filename=filename,
        profile_id=profile_id,
        task="text",
        replace_existing=replace_existing,
        is_canceled=is_canceled,
    )
