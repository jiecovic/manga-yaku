# backend-python/core/usecases/box_detection/profiles/catalog.py
"""Static box-detection profile catalog and runtime availability toggles."""

from __future__ import annotations

from typing import Any, TypedDict


class BoxDetectionProfile(TypedDict, total=False):
    """Configuration for a box-detection backend such as YOLO."""

    id: str
    label: str
    description: str
    provider: str
    enabled: bool
    config: dict[str, Any]


BOX_DETECTION_PROFILES: dict[str, BoxDetectionProfile] = {}


def mark_box_detection_availability(*, has_yolo: bool) -> None:
    """Update runtime availability flags for built-in detection profiles."""
    if "yolo_default" in BOX_DETECTION_PROFILES:
        BOX_DETECTION_PROFILES["yolo_default"]["enabled"] = has_yolo
