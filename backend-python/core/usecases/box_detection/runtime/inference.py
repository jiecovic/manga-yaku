# backend-python/core/usecases/box_detection/runtime/inference.py
"""Inference helpers for YOLO-backed box detection."""

from __future__ import annotations

from collections.abc import Callable

from config import VOLUMES_ROOT, safe_join
from core.usecases.settings.service import resolve_detection_settings
from PIL import Image

from ..profiles.registry import BoxDetectionProfile
from .model_runtime import get_yolo_model
from .postprocess import (
    filter_contained_boxes,
    resolve_containment_threshold,
)

_TASK_CLASS_ALIASES = {
    "text": "text",
    "textbox": "text",
    "speech": "text",
    "frame": "panel",
    "frames": "panel",
    "panel": "panel",
    "panels": "panel",
    "face": "face",
    "faces": "face",
    "body": "body",
    "bodies": "body",
}
CancelCallback = Callable[[], bool]


def load_page_image(volume_id: str, filename: str) -> Image.Image:
    """Load a page image from the volume store."""
    try:
        img_path = safe_join(VOLUMES_ROOT, volume_id, filename)
    except ValueError as exc:
        raise FileNotFoundError("Invalid page image path") from exc
    if not img_path.exists():
        raise FileNotFoundError(f"Page image not found: {img_path}")
    return Image.open(img_path).convert("RGB")


def normalize_task(task: str | None) -> str | None:
    if not task:
        return None
    key = task.strip().lower()
    return _TASK_CLASS_ALIASES.get(key, key) or None


def should_abort(is_canceled: CancelCallback | None) -> bool:
    if is_canceled is None:
        return False
    try:
        return bool(is_canceled())
    except Exception:
        return False


def resolve_allowed_classes(
    profile: BoxDetectionProfile,
    task: str | None,
) -> list[int] | None:
    cfg = profile.get("config", {}) or {}
    if not task:
        allowed = cfg.get("allowed_classes")
        if isinstance(allowed, list):
            return [int(value) for value in allowed]
        return None

    normalized = normalize_task(task)
    if not normalized:
        return None

    class_names = cfg.get("class_names")
    if not isinstance(class_names, list) or not class_names:
        allowed = cfg.get("allowed_classes")
        if isinstance(allowed, list):
            return [int(value) for value in allowed]
        return None

    matches = [
        idx for idx, name in enumerate(class_names) if normalize_task(str(name)) == normalized
    ]
    if not matches:
        raise ValueError(
            f"Detection task '{task}' not supported by model '{profile.get('id', '')}'"
        )
    return matches


def resolve_detection_thresholds(profile: BoxDetectionProfile) -> tuple[float, float]:
    cfg = profile.get("config", {}) or {}
    conf_th = float(cfg.get("conf_threshold", 0.25))
    iou_th = float(cfg.get("iou_threshold", 0.45))
    detection_settings = resolve_detection_settings()
    if detection_settings.conf_threshold is not None:
        conf_th = detection_settings.conf_threshold
    if detection_settings.iou_threshold is not None:
        iou_th = detection_settings.iou_threshold
    return conf_th, iou_th


def run_yolo_on_image(
    image: Image.Image,
    profile: BoxDetectionProfile,
    *,
    allowed_classes: list[int] | None = None,
) -> list[dict[str, float]]:
    """Run YOLO and return normalized box detections."""
    cfg = profile.get("config", {}) or {}
    conf_th, iou_th = resolve_detection_thresholds(profile)
    if allowed_classes is None:
        allowed_classes = cfg.get("allowed_classes")

    model = get_yolo_model(profile)
    results = model(image, conf=conf_th, iou=iou_th)
    if not results:
        return []

    res = results[0]
    boxes_out: list[dict[str, float]] = []
    for box in res.boxes:
        cls_id = int(box.cls[0]) if hasattr(box, "cls") else None
        if allowed_classes is not None and cls_id is not None and cls_id not in allowed_classes:
            continue

        xyxy = box.xyxy[0].tolist()
        conf = float(box.conf[0]) if hasattr(box, "conf") else 1.0
        x1, y1, x2, y2 = map(float, xyxy)
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if width <= 0.0 or height <= 0.0:
            continue
        boxes_out.append(
            {
                "x": x1,
                "y": y1,
                "width": width,
                "height": height,
                "score": conf,
            }
        )

    image_width, image_height = image.size
    if boxes_out:
        containment_th = resolve_containment_threshold(profile)
        boxes_out = filter_contained_boxes(boxes_out, threshold=containment_th)
        if not boxes_out:
            return []

        cfg = profile.get("config", {}) or {}
        spread_ratio = float(cfg.get("spread_aspect_ratio", 1.35))
        is_spread = image_height > 0 and (image_width / image_height) >= spread_ratio
        if is_spread:
            mid_x = image_width / 2.0
            right_boxes = [bx for bx in boxes_out if (bx["x"] + bx["width"] / 2.0) >= mid_x]
            left_boxes = [bx for bx in boxes_out if (bx["x"] + bx["width"] / 2.0) < mid_x]
            if right_boxes and left_boxes:
                boxes_out = sort_boxes_reading(profile, right_boxes) + sort_boxes_reading(
                    profile, left_boxes
                )
            else:
                boxes_out = sort_boxes_reading(profile, boxes_out)
        else:
            boxes_out = sort_boxes_reading(profile, boxes_out)
    return boxes_out


def sort_boxes_reading(
    profile: BoxDetectionProfile,
    boxes: list[dict[str, float]],
) -> list[dict[str, float]]:
    if not boxes:
        return boxes
    cfg = profile.get("config", {}) or {}
    overlap_th = float(cfg.get("row_overlap_threshold", 0.35))

    boxes_sorted = sorted(boxes, key=lambda box: box["y"])
    rows_boxes: list[list[dict[str, float]]] = []
    rows_min: list[float] = []
    rows_max: list[float] = []

    for box in boxes_sorted:
        box_top = box["y"]
        box_bottom = box["y"] + box["height"]
        if not rows_boxes:
            rows_boxes.append([box])
            rows_min.append(box_top)
            rows_max.append(box_bottom)
            continue
        row_min = rows_min[-1]
        row_max = rows_max[-1]
        row_height = max(row_max - row_min, 1e-6)
        overlap = min(row_max, box_bottom) - max(row_min, box_top)
        overlap_ratio = overlap / min(box["height"], row_height) if overlap > 0 else 0.0
        if overlap_ratio >= overlap_th:
            rows_boxes[-1].append(box)
            rows_min[-1] = min(row_min, box_top)
            rows_max[-1] = max(row_max, box_bottom)
        else:
            rows_boxes.append([box])
            rows_min.append(box_top)
            rows_max.append(box_bottom)

    ordered: list[dict[str, float]] = []
    for row_boxes in rows_boxes:
        row_boxes.sort(key=lambda box: -(box["x"] + box["width"] / 2.0))
        ordered.extend(row_boxes)
    return ordered
