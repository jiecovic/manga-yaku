# backend-python/core/usecases/box_detection/profiles/registry.py
"""Effective detection profile lookups and API views."""

from __future__ import annotations

from .availability import profile_payload_for_api
from .catalog import BOX_DETECTION_PROFILES, BoxDetectionProfile
from .published import get_published_profile, list_published_profiles_for_api
from .trained import get_run_profile, list_run_profiles_for_api


def get_box_detection_profile(profile_id: str) -> BoxDetectionProfile:
    """Look up a box-detection profile by id."""
    profile = get_published_profile(profile_id)
    if profile is None:
        profile = BOX_DETECTION_PROFILES.get(profile_id)
    if profile is None:
        profile = get_run_profile(profile_id)
    if profile is None:
        raise ValueError(f"Box detection profile '{profile_id}' not found")
    return profile


def list_box_detection_profiles_for_api() -> list[dict[str, object]]:
    """Return detection profiles with availability and class metadata for the API."""
    profiles: list[dict[str, object]] = []
    profiles.extend(list_published_profiles_for_api())
    profiles.extend(
        [profile_payload_for_api(p, fallback_id=pid) for pid, p in BOX_DETECTION_PROFILES.items()]
    )
    profiles.extend(list_run_profiles_for_api())
    return profiles


def pick_default_box_detection_profile_id() -> str | None:
    profiles = list_box_detection_profiles_for_api()
    for profile in profiles:
        if profile.get("enabled", True):
            return str(profile.get("id", ""))
    return None
