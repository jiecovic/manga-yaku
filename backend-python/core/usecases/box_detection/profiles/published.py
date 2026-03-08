# backend-python/core/usecases/box_detection/profiles/published.py
"""Published model profile loading for box detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import MODELS_ROOT

from .availability import profile_payload_for_api
from .catalog import BoxDetectionProfile


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
        return json.loads(raw)
    except Exception:
        return {}


def build_published_profile(manifest_path: Path) -> BoxDetectionProfile | None:
    manifest = _read_json(manifest_path)
    if not manifest:
        return None
    profile_id = str(manifest.get("id") or manifest_path.parent.name).strip()
    if not profile_id:
        return None
    label = str(manifest.get("label") or profile_id)
    description = str(manifest.get("description") or "")
    provider = str(manifest.get("provider") or "yolo")
    enabled = bool(manifest.get("enabled", True))
    model_path = manifest.get("model_path")
    if not model_path:
        candidate = manifest_path.parent / "best.pt"
        if candidate.is_file():
            model_path = str(candidate)
    if not model_path:
        return None
    class_names = manifest.get("class_names")
    config = dict(manifest.get("config") or {})
    config["model_path"] = str(model_path)
    if isinstance(class_names, list):
        config.setdefault("class_names", class_names)
    return {
        "id": profile_id,
        "label": label,
        "description": description,
        "provider": provider,
        "enabled": enabled,
        "config": config,
    }


def iter_published_profiles() -> list[BoxDetectionProfile]:
    if not MODELS_ROOT.is_dir():
        return []
    profiles: list[BoxDetectionProfile] = []
    for entry in MODELS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file():
            continue
        profile = build_published_profile(manifest_path)
        if profile is not None:
            profiles.append(profile)
    return profiles


def get_published_profile(profile_id: str) -> BoxDetectionProfile | None:
    for profile in iter_published_profiles():
        if profile.get("id") == profile_id:
            return profile
    return None


def list_published_profiles_for_api() -> list[dict[str, object]]:
    profiles = [profile_payload_for_api(profile) for profile in iter_published_profiles()]
    profiles.sort(key=lambda item: str(item.get("label", "")))
    return profiles
