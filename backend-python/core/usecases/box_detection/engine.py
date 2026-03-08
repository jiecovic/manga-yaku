# backend-python/core/usecases/box_detection/engine.py
"""Primary orchestration logic for box detection operations."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT, VOLUMES_ROOT, safe_join
from core.usecases.settings.service import resolve_detection_settings
from infra.db.store_boxes import create_detection_run, replace_boxes_for_type
from infra.db.store_volume_page import load_page
from infra.logging.correlation import append_correlation
from PIL import Image

from .postprocess import (
    filter_boxes_overlapping_existing,
    filter_contained_boxes,
    resolve_containment_threshold,
)
from .profiles import (
    BoxDetectionProfile,
    get_box_detection_profile,
    is_git_lfs_pointer_model,
    pick_default_box_detection_profile_id,
)

# Optional YOLO import (ultralytics)
try:
    from ultralytics import YOLO  # type: ignore

    _yolo_import_error: Exception | None = None
except Exception as e:  # pragma: no cover
    YOLO = None  # type: ignore
    _yolo_import_error = e

# Simple cache so we don't reload the model for every page
_YOLO_MODEL_CACHE: dict[Path, Any] = {}
_MODEL_HASH_CACHE: dict[Path, tuple[float, int, str]] = {}
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
logger = logging.getLogger(__name__)
CancelCallback = Callable[[], bool]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_page_image(volume_id: str, filename: str) -> Image.Image:
    """
    Load a page image from VOLUMES_ROOT / <volume_id> / <filename>.
    """
    try:
        img_path = safe_join(VOLUMES_ROOT, volume_id, filename)
    except ValueError as exc:
        raise FileNotFoundError("Invalid page image path") from exc
    if not img_path.exists():
        raise FileNotFoundError(f"Page image not found: {img_path}")

    return Image.open(img_path).convert("RGB")


def _get_yolo_model(profile: BoxDetectionProfile):
    """
    Lazily load and cache the YOLO model defined in the profile config.
    Resolves relative paths against the *project root* (one level above backend-python/).
    """
    if YOLO is None:
        raise RuntimeError(f"ultralytics.YOLO is not available: {_yolo_import_error!r}")

    cfg = profile.get("config", {}) or {}
    raw_path = cfg.get("model_path")
    if not raw_path:
        raise RuntimeError("Box detection profile config is missing 'model_path'")

    model_path = Path(raw_path)

    # If it's a relative path, treat it as relative to the project root
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path

    logger.debug(
        append_correlation(
            f"Model path resolved: {model_path}",
            {"component": "box_detection.model_load"},
            profile_id=str(profile.get("id") or ""),
        )
    )

    if not model_path.is_file():
        raise FileNotFoundError(
            f"YOLO model file not found at '{model_path}'. "
            "Place your weights under training-data/ultralytics/weights and "
            "update model_path in box_detection/profiles.py if needed."
        )
    if is_git_lfs_pointer_model(model_path):
        raise RuntimeError(
            f"YOLO model file at '{model_path}' is a Git LFS pointer, not real weights. "
            "Fetch the actual model file (for example: `git lfs pull`) or train a model first."
        )

    if model_path in _YOLO_MODEL_CACHE:
        return _YOLO_MODEL_CACHE[model_path]

    model = YOLO(str(model_path))
    _YOLO_MODEL_CACHE[model_path] = model
    return model


def _resolve_model_path(profile: BoxDetectionProfile) -> Path | None:
    cfg = profile.get("config", {}) or {}
    raw_path = cfg.get("model_path")
    if not raw_path:
        return None
    model_path = Path(raw_path)
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path
    return model_path


def _get_model_hash(model_path: Path | None) -> str | None:
    if not model_path or not model_path.is_file():
        return None
    try:
        stat = model_path.stat()
    except OSError:
        return None

    cached = _MODEL_HASH_CACHE.get(model_path)
    if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2]

    sha = hashlib.sha256()
    with model_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    digest = sha.hexdigest()
    _MODEL_HASH_CACHE[model_path] = (stat.st_mtime, stat.st_size, digest)
    return digest


def _normalize_task(task: str | None) -> str | None:
    if not task:
        return None
    key = task.strip().lower()
    return _TASK_CLASS_ALIASES.get(key, key) or None


def _should_abort(is_canceled: CancelCallback | None) -> bool:
    if is_canceled is None:
        return False
    try:
        return bool(is_canceled())
    except Exception:
        return False


def _resolve_allowed_classes(
    profile: BoxDetectionProfile,
    task: str | None,
) -> list[int] | None:
    cfg = profile.get("config", {}) or {}
    if not task:
        allowed = cfg.get("allowed_classes")
        if isinstance(allowed, list):
            return [int(value) for value in allowed]
        return None

    normalized = _normalize_task(task)
    if not normalized:
        return None

    class_names = cfg.get("class_names")
    if not isinstance(class_names, list) or not class_names:
        allowed = cfg.get("allowed_classes")
        if isinstance(allowed, list):
            return [int(value) for value in allowed]
        return None

    matches = [
        idx for idx, name in enumerate(class_names) if _normalize_task(str(name)) == normalized
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


def _run_yolo_on_image(
    image: Image.Image,
    profile: BoxDetectionProfile,
    *,
    allowed_classes: list[int] | None = None,
) -> list[dict[str, float]]:
    """
    Run YOLO on the given image and return a list of detections:
    [{"x": ..., "y": ..., "width": ..., "height": ..., "score": ...}, ...]
    """
    cfg = profile.get("config", {}) or {}
    conf_th, iou_th = resolve_detection_thresholds(profile)
    if allowed_classes is None:
        allowed_classes = cfg.get("allowed_classes")  # e.g. [1] for "text" only

    model = _get_yolo_model(profile)

    # Run inference
    results = model(image, conf=conf_th, iou=iou_th)
    if not results:
        return []

    res = results[0]
    boxes_out: list[dict[str, float]] = []

    for b in res.boxes:
        # class id (if available)
        cls_id = int(b.cls[0]) if hasattr(b, "cls") else None

        # 👇 Filter by allowed_classes if configured
        if allowed_classes is not None and cls_id is not None:
            if cls_id not in allowed_classes:
                continue

        xyxy = b.xyxy[0].tolist()  # [x1, y1, x2, y2]
        conf = float(b.conf[0]) if hasattr(b, "conf") else 1.0

        x1, y1, x2, y2 = map(float, xyxy)
        w = max(0.0, x2 - x1)
        h = max(0.0, y2 - y1)

        if w <= 0.0 or h <= 0.0:
            continue

        boxes_out.append(
            {
                "x": x1,
                "y": y1,
                "width": w,
                "height": h,
                "score": conf,
            }
        )

    # --------- Containment dedupe + reading order ----------
    img_w, img_h = image.size

    def sort_boxes_reading(boxes: list[dict[str, float]]) -> list[dict[str, float]]:
        if not boxes:
            return boxes
        cfg = profile.get("config", {}) or {}
        overlap_th = float(cfg.get("row_overlap_threshold", 0.35))

        def top_sort_key(bx: dict[str, float]):
            return bx["y"]

        boxes_sorted = sorted(boxes, key=top_sort_key)
        rows_boxes: list[list[dict[str, float]]] = []
        rows_min: list[float] = []
        rows_max: list[float] = []

        for bx in boxes_sorted:
            bx_top = bx["y"]
            bx_bottom = bx["y"] + bx["height"]
            if not rows_boxes:
                rows_boxes.append([bx])
                rows_min.append(bx_top)
                rows_max.append(bx_bottom)
                continue
            row_min = rows_min[-1]
            row_max = rows_max[-1]
            row_height = max(row_max - row_min, 1e-6)
            overlap = min(row_max, bx_bottom) - max(row_min, bx_top)
            overlap_ratio = overlap / min(bx["height"], row_height) if overlap > 0 else 0.0
            if overlap_ratio >= overlap_th:
                rows_boxes[-1].append(bx)
                rows_min[-1] = min(row_min, bx_top)
                rows_max[-1] = max(row_max, bx_bottom)
            else:
                rows_boxes.append([bx])
                rows_min.append(bx_top)
                rows_max.append(bx_bottom)

        ordered: list[dict[str, float]] = []
        for row_boxes in rows_boxes:
            row_boxes.sort(key=lambda bx: -(bx["x"] + bx["width"] / 2.0))
            ordered.extend(row_boxes)

        return ordered

    if boxes_out:
        containment_th = resolve_containment_threshold(profile)
        boxes_out = filter_contained_boxes(boxes_out, threshold=containment_th)
        if not boxes_out:
            return []
        cfg = profile.get("config", {}) or {}
        spread_ratio = float(cfg.get("spread_aspect_ratio", 1.35))
        is_spread = img_h > 0 and (img_w / img_h) >= spread_ratio
        if is_spread:
            mid_x = img_w / 2.0
            right_boxes = [bx for bx in boxes_out if (bx["x"] + bx["width"] / 2.0) >= mid_x]
            left_boxes = [bx for bx in boxes_out if (bx["x"] + bx["width"] / 2.0) < mid_x]
            if right_boxes and left_boxes:
                boxes_out = sort_boxes_reading(right_boxes) + sort_boxes_reading(left_boxes)
            else:
                boxes_out = sort_boxes_reading(boxes_out)
        else:
            boxes_out = sort_boxes_reading(boxes_out)

    # --------------------------------------------------

    return boxes_out


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
    """
    Run detection for a single page.

    - Loads the page image from VOLUMES_ROOT.
    - Runs YOLO using the given profile.
    - Optionally filters detections by task (class name).
    - Writes detected boxes into the page store.
    - Returns the list of created box dicts.

    If `replace_existing` is True, any existing boxes on the page
    are discarded and replaced by the detected ones.
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

    normalized_task = _normalize_task(task) or "text"

    if _should_abort(is_canceled):
        return []

    # 1) Load the image
    img = _load_page_image(volume_id, filename)
    if _should_abort(is_canceled):
        return []

    # 2) Run YOLO
    allowed_classes = _resolve_allowed_classes(profile, normalized_task)
    detections = _run_yolo_on_image(img, profile, allowed_classes=allowed_classes)
    if _should_abort(is_canceled):
        return []

    model_path = _resolve_model_path(profile)
    model_hash = _get_model_hash(model_path)
    cfg = profile.get("config", {}) or {}
    conf_th, iou_th = resolve_detection_thresholds(profile)
    containment_th = resolve_containment_threshold(profile)
    model_version = cfg.get("model_version") or cfg.get("version")
    if _should_abort(is_canceled):
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
    if _should_abort(is_canceled):
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
    return detect_boxes_for_page(
        volume_id=volume_id,
        filename=filename,
        profile_id=profile_id,
        task="text",
        replace_existing=replace_existing,
        is_canceled=is_canceled,
    )
