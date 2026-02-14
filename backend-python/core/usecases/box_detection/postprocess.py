# backend-python/core/usecases/box_detection/postprocess.py
from __future__ import annotations

from core.usecases.settings.service import get_setting_value

from .profiles import BoxDetectionProfile


def resolve_containment_threshold(profile: BoxDetectionProfile) -> float:
    """Return the effective containment threshold (profile override + global override)."""
    cfg = profile.get("config", {}) or {}
    threshold = float(cfg.get("containment_threshold", 0.9))
    global_threshold = get_setting_value("detection.containment_threshold")
    if global_threshold is not None:
        threshold = float(global_threshold)
    return threshold


def _intersection_area(a: dict[str, float], b: dict[str, float]) -> float:
    """Compute intersection area for two axis-aligned boxes."""
    ax2 = a["x"] + a["width"]
    ay2 = a["y"] + a["height"]
    bx2 = b["x"] + b["width"]
    by2 = b["y"] + b["height"]
    ix1 = max(a["x"], b["x"])
    iy1 = max(a["y"], b["y"])
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    return iw * ih


def filter_contained_boxes(
    boxes: list[dict[str, float]],
    *,
    threshold: float,
) -> list[dict[str, float]]:
    """Drop boxes mostly contained in larger boxes (intersection / smaller area >= threshold)."""
    if threshold <= 0:
        return boxes
    sorted_boxes = sorted(
        boxes,
        key=lambda box: (
            -float(box.get("score", 0.0)),
            float(box.get("width", 0.0)) * float(box.get("height", 0.0)),
        ),
    )
    filtered: list[dict[str, float]] = []
    for candidate in sorted_boxes:
        cand_area = float(candidate.get("width", 0.0)) * float(
            candidate.get("height", 0.0)
        )
        if cand_area <= 0.0:
            continue
        drop = False
        for kept in filtered:
            kept_area = float(kept.get("width", 0.0)) * float(
                kept.get("height", 0.0)
            )
            if kept_area <= 0.0:
                continue
            inter = _intersection_area(candidate, kept)
            if inter <= 0.0:
                continue
            smaller_area = cand_area if cand_area <= kept_area else kept_area
            if smaller_area <= 0.0:
                continue
            if inter / smaller_area >= threshold:
                drop = True
                break
        if not drop:
            filtered.append(candidate)
    return filtered
