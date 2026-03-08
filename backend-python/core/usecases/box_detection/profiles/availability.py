# backend-python/core/usecases/box_detection/profiles/availability.py
"""Availability and manifest helpers for detection profiles."""

from __future__ import annotations

from pathlib import Path

from config import PROJECT_ROOT

from .catalog import BoxDetectionProfile


def get_profile_class_names(profile: BoxDetectionProfile) -> list[str]:
    cfg = profile.get("config", {}) or {}
    names = cfg.get("class_names")
    if isinstance(names, list):
        return [str(name) for name in names]
    return []


def resolve_model_path(raw_path: str) -> Path:
    model_path = Path(raw_path)
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path
    return model_path


def is_git_lfs_pointer_model(path: Path) -> bool:
    """Detect a Git LFS pointer file instead of real model weights."""
    try:
        with path.open("rb") as handle:
            head = handle.read(256)
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def profile_is_available(profile: BoxDetectionProfile) -> bool:
    if not profile.get("enabled", True):
        return False
    cfg = profile.get("config", {}) or {}
    raw_path = cfg.get("model_path")
    if not raw_path:
        return True
    try:
        model_path = resolve_model_path(str(raw_path))
    except Exception:
        return True
    if not model_path.is_file():
        return False
    if is_git_lfs_pointer_model(model_path):
        return False
    return True


def profile_payload_for_api(
    profile: BoxDetectionProfile, *, fallback_id: str = ""
) -> dict[str, object]:
    return {
        "id": profile.get("id", fallback_id),
        "label": profile.get("label", profile.get("id", fallback_id)),
        "description": profile.get("description", ""),
        "provider": profile.get("provider", ""),
        "enabled": profile_is_available(profile),
        "classes": get_profile_class_names(profile),
    }
