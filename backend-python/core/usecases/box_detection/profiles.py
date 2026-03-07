# backend-python/core/usecases/box_detection/profiles.py
"""Default profile definitions for box detection providers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

import yaml

from config import MODELS_ROOT, PROJECT_ROOT, TRAINING_RUNS_ROOT, safe_join


class BoxDetectionProfile(TypedDict, total=False):
    """
    Configuration for a box-detection backend (e.g. YOLO).
    Very similar in spirit to the OCR/translation profiles.
    """
    id: str
    label: str
    description: str
    provider: str  # e.g. "yolov8"
    enabled: bool
    config: dict[str, Any]


# Registry of available detection profiles.
#
# NOTE: model_path can be absolute or relative. Use the ultralytics
#       weights cache under training-data/ultralytics/weights.
BOX_DETECTION_PROFILES: dict[str, BoxDetectionProfile] = {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
        return json.loads(raw)
    except Exception:
        return {}


def _load_published_manifest(path: Path) -> dict[str, Any]:
    return _read_json(path)


def _build_published_profile(manifest_path: Path) -> BoxDetectionProfile | None:
    manifest = _load_published_manifest(manifest_path)
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
    profile: BoxDetectionProfile = {
        "id": profile_id,
        "label": label,
        "description": description,
        "provider": provider,
        "enabled": enabled,
        "config": config,
    }
    return profile


def _iter_published_profiles() -> list[BoxDetectionProfile]:
    if not MODELS_ROOT.is_dir():
        return []
    profiles: list[BoxDetectionProfile] = []
    for entry in MODELS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file():
            continue
        profile = _build_published_profile(manifest_path)
        if profile:
            profiles.append(profile)
    return profiles


def _list_published_profiles_for_api() -> list[dict[str, Any]]:
    profiles = []
    for profile in _iter_published_profiles():
        profiles.append(
            {
                "id": profile.get("id", ""),
                "label": profile.get("label", profile.get("id", "")),
                "description": profile.get("description", ""),
                "provider": profile.get("provider", ""),
                "enabled": _is_profile_available(profile),
                "classes": _get_profile_class_names(profile),
            }
        )
    profiles.sort(key=lambda item: str(item.get("label", "")))
    return profiles


def _get_published_profile_by_id(profile_id: str) -> BoxDetectionProfile | None:
    for profile in _iter_published_profiles():
        if profile.get("id") == profile_id:
            return profile
    return None


def get_box_detection_profile(profile_id: str) -> BoxDetectionProfile:
    """
    Look up a box-detection profile by id.
    Raises ValueError if it does not exist.
    """
    profile = _get_published_profile_by_id(profile_id)
    if profile is None:
        profile = BOX_DETECTION_PROFILES.get(profile_id)
    if profile is None:
        profile = _get_run_profile_by_id(profile_id)
    if profile is None:
        raise ValueError(f"Box detection profile '{profile_id}' not found")
    return profile


def list_box_detection_profiles_for_api() -> list[dict[str, Any]]:
    """
    Optional helper if you later want to expose detection profiles via an API.
    Mirrors the style of the OCR/translation list_*_profiles_for_api helpers.
    """
    profiles: list[dict[str, Any]] = []
    profiles.extend(_list_published_profiles_for_api())
    profiles.extend(
        [
            {
                "id": p.get("id", pid),
                "label": p.get("label", pid),
                "description": p.get("description", ""),
                "provider": p.get("provider", ""),
                "enabled": _is_profile_available(p),
                "classes": _get_profile_class_names(p),
            }
            for pid, p in BOX_DETECTION_PROFILES.items()
        ]
    )
    profiles.extend(_list_run_profiles_for_api())
    return profiles


def pick_default_box_detection_profile_id() -> str | None:
    profiles = list_box_detection_profiles_for_api()
    for profile in profiles:
        if profile.get("enabled", True):
            return str(profile.get("id", ""))
    return None


def _run_profile_id(run_dir: Path) -> str:
    rel = run_dir.relative_to(TRAINING_RUNS_ROOT).as_posix()
    return f"run:{rel}"


def _safe_run_dir_from_id(profile_id: str) -> Path | None:
    if not profile_id.startswith("run:"):
        return None
    rel = profile_id[4:]
    if not rel:
        return None
    parts = Path(rel).parts
    try:
        return safe_join(TRAINING_RUNS_ROOT, *parts)
    except ValueError:
        return None


def _read_dataset_names(data_yaml_path: Path) -> list[str]:
    if not data_yaml_path.is_file():
        return []
    try:
        raw = data_yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
    except Exception:
        return []
    names = data.get("names")
    if isinstance(names, dict):
        ordered_keys = sorted(
            names.keys(),
            key=lambda key: int(key) if str(key).isdigit() else str(key),
        )
        return [str(names[key]) for key in ordered_keys]
    if isinstance(names, list):
        return [str(name) for name in names]
    return []


def _get_profile_class_names(profile: BoxDetectionProfile) -> list[str]:
    cfg = profile.get("config", {}) or {}
    names = cfg.get("class_names")
    if isinstance(names, list):
        return [str(name) for name in names]
    return []


def _resolve_model_path(raw_path: str) -> Path:
    model_path = Path(raw_path)
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path
    return model_path


def _is_git_lfs_pointer(path: Path) -> bool:
    """
    Detect a Git LFS pointer file (text stub) instead of real model weights.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(256)
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def is_git_lfs_pointer_model(path: Path) -> bool:
    return _is_git_lfs_pointer(path)


def _is_profile_available(profile: BoxDetectionProfile) -> bool:
    if not profile.get("enabled", True):
        return False
    cfg = profile.get("config", {}) or {}
    raw_path = cfg.get("model_path")
    if not raw_path:
        return True
    try:
        model_path = _resolve_model_path(str(raw_path))
    except Exception:
        return True
    if not model_path.is_file():
        return False
    if _is_git_lfs_pointer(model_path):
        return False
    return True


def _parse_manifest_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _load_run_manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    return _read_json(manifest_path)


def _build_run_profile(run_dir: Path) -> BoxDetectionProfile | None:
    weights_dir = run_dir / "weights"
    best_path = weights_dir / "best.pt"
    if not best_path.is_file():
        return None

    manifest = _load_run_manifest(run_dir)
    dataset_id = str(manifest.get("dataset_id") or run_dir.parent.name)
    data_yaml = manifest.get("data_yaml_used") or manifest.get("data_yaml")
    names = _read_dataset_names(Path(data_yaml)) if data_yaml else []
    classes_label = ", ".join(names) if names else "unknown classes"
    label = f"{dataset_id} / {run_dir.name} ({classes_label})"
    description = str(manifest.get("model") or "trained model")

    profile: BoxDetectionProfile = {
        "id": _run_profile_id(run_dir),
        "label": label,
        "description": description,
        "provider": "yolo",
        "enabled": True,
        "config": {
            "model_path": str(best_path),
            "class_names": names,
        },
    }
    return profile


def _iter_run_dirs() -> list[Path]:
    if not TRAINING_RUNS_ROOT.is_dir():
        return []
    runs: list[Path] = []
    for dataset_dir in TRAINING_RUNS_ROOT.iterdir():
        if not dataset_dir.is_dir():
            continue
        for run_dir in dataset_dir.iterdir():
            if not run_dir.is_dir():
                continue
            if (run_dir / "manifest.json").is_file():
                runs.append(run_dir)
    return runs


def _list_run_profiles_for_api() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for run_dir in _iter_run_dirs():
        profile = _build_run_profile(run_dir)
        if profile is None:
            continue
        profiles.append(
            {
                "id": profile.get("id", _run_profile_id(run_dir)),
                "label": profile.get("label", run_dir.name),
                "description": profile.get("description", ""),
                "provider": profile.get("provider", ""),
                "enabled": _is_profile_available(profile),
                "classes": _get_profile_class_names(profile),
            }
        )

    def sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
        run_dir = _safe_run_dir_from_id(str(item.get("id", "")))
        if not run_dir:
            return (1, 0.0, str(item.get("label", "")))
        manifest = _load_run_manifest(run_dir)
        created = _parse_manifest_time(manifest.get("created_at"))
        if created is None:
            return (1, 0.0, str(item.get("label", "")))
        return (0, -created.timestamp(), str(item.get("label", "")))

    profiles.sort(key=sort_key)
    return profiles


def _get_run_profile_by_id(profile_id: str) -> BoxDetectionProfile | None:
    run_dir = _safe_run_dir_from_id(profile_id)
    if run_dir is None or not run_dir.is_dir():
        return None
    return _build_run_profile(run_dir)


def mark_box_detection_availability(*, has_yolo: bool) -> None:
    """
    Optional runtime toggle: call this from the detection engine if you want
    to disable profiles automatically when YOLO / weights are unavailable.
    """
    if "yolo_default" in BOX_DETECTION_PROFILES:
        BOX_DETECTION_PROFILES["yolo_default"]["enabled"] = has_yolo
