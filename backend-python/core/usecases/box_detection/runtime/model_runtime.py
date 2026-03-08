# backend-python/core/usecases/box_detection/runtime/model_runtime.py
"""Model-loading helpers for YOLO-backed box detection."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT

from ..profiles.availability import is_git_lfs_pointer_model
from ..profiles.catalog import BoxDetectionProfile

try:
    from ultralytics import YOLO  # type: ignore

    _yolo_import_error: Exception | None = None
except Exception as exc:  # pragma: no cover
    YOLO = None  # type: ignore
    _yolo_import_error = exc

logger = logging.getLogger(__name__)

_YOLO_MODEL_CACHE: dict[Path, Any] = {}
_MODEL_HASH_CACHE: dict[Path, tuple[float, int, str]] = {}


def get_yolo_model(profile: BoxDetectionProfile) -> Any:
    """Lazily load and cache the YOLO model defined in the profile config."""
    if YOLO is None:
        raise RuntimeError(f"ultralytics.YOLO is not available: {_yolo_import_error!r}")

    cfg = profile.get("config", {}) or {}
    raw_path = cfg.get("model_path")
    if not raw_path:
        raise RuntimeError("Box detection profile config is missing 'model_path'")

    model_path = Path(raw_path)
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path

    if not model_path.is_file():
        raise FileNotFoundError(
            f"YOLO model file not found at '{model_path}'. "
            "Place your weights under training-data/ultralytics/weights and "
            "update the profile manifest if needed."
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


def resolve_model_path(profile: BoxDetectionProfile) -> Path | None:
    cfg = profile.get("config", {}) or {}
    raw_path = cfg.get("model_path")
    if not raw_path:
        return None
    model_path = Path(raw_path)
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path
    return model_path


def get_model_hash(model_path: Path | None) -> str | None:
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
