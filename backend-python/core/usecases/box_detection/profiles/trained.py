# backend-python/core/usecases/box_detection/profiles/trained.py
"""Training-run derived profile loading for box detection."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from config import TRAINING_RUNS_ROOT, safe_join

from .availability import profile_payload_for_api
from .catalog import BoxDetectionProfile


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
        return json.loads(raw)
    except Exception:
        return {}


def _run_profile_id(run_dir: Path) -> str:
    rel = run_dir.relative_to(TRAINING_RUNS_ROOT).as_posix()
    return f"run:{rel}"


def _safe_run_dir_from_id(profile_id: str) -> Path | None:
    if not profile_id.startswith("run:"):
        return None
    rel = profile_id[4:]
    if not rel:
        return None
    try:
        return safe_join(TRAINING_RUNS_ROOT, *Path(rel).parts)
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


def build_run_profile(run_dir: Path) -> BoxDetectionProfile | None:
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
    return {
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


def iter_run_dirs() -> list[Path]:
    if not TRAINING_RUNS_ROOT.is_dir():
        return []
    runs: list[Path] = []
    for dataset_dir in TRAINING_RUNS_ROOT.iterdir():
        if not dataset_dir.is_dir():
            continue
        for run_dir in dataset_dir.iterdir():
            if run_dir.is_dir() and (run_dir / "manifest.json").is_file():
                runs.append(run_dir)
    return runs


def get_run_profile(profile_id: str) -> BoxDetectionProfile | None:
    run_dir = _safe_run_dir_from_id(profile_id)
    if run_dir is None or not run_dir.is_dir():
        return None
    return build_run_profile(run_dir)


def list_run_profiles_for_api() -> list[dict[str, object]]:
    profiles: list[dict[str, object]] = []
    for run_dir in iter_run_dirs():
        profile = build_run_profile(run_dir)
        if profile is None:
            continue
        profiles.append(
            profile_payload_for_api(
                profile,
                fallback_id=str(profile.get("id", _run_profile_id(run_dir))),
            )
        )

    def sort_key(item: dict[str, object]) -> tuple[int, float, str]:
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
