# backend-python/core/usecases/box_detection/__init__.py
"""Public exports for the box detection use case package."""

from .engine import detect_boxes_for_page, detect_text_boxes_for_page
from .profiles import (
    BOX_DETECTION_PROFILES,
    BoxDetectionProfile,
    get_box_detection_profile,
    list_box_detection_profiles_for_api,
    mark_box_detection_availability,
    pick_default_box_detection_profile_id,
)

__all__ = [
    "BOX_DETECTION_PROFILES",
    "BoxDetectionProfile",
    "detect_boxes_for_page",
    "detect_text_boxes_for_page",
    "get_box_detection_profile",
    "list_box_detection_profiles_for_api",
    "mark_box_detection_availability",
    "pick_default_box_detection_profile_id",
]
