# backend-python/infra/training/catalog.py
from __future__ import annotations

import json
from pathlib import Path

from config import TRAINING_PREPARED_ROOT, TRAINING_SOURCES_ROOT, safe_join
from packaging.version import InvalidVersion, Version

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def load_source_manifest(source_dir: Path) -> dict | None:
    manifest_path = source_dir / "source.json"
    if not manifest_path.is_file():
        return None

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def load_prepared_manifest(dataset_dir: Path) -> dict | None:
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.is_file():
        return None

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def detect_source_type(source_dir: Path, manifest: dict | None) -> str:
    if manifest and isinstance(manifest.get("type"), str):
        return str(manifest["type"])

    images_dir = source_dir / "images"
    annotations_dir = source_dir / "annotations"
    labels_dir = source_dir / "labels"

    if images_dir.is_dir() and annotations_dir.is_dir():
        if any(annotations_dir.glob("*.xml")):
            return "manga109s"
        return "manga109s"

    if images_dir.is_dir() and labels_dir.is_dir():
        return "yolo"

    return "unknown"


def _count_volume_dirs(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.iterdir() if p.is_dir())


def _count_images(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(
        1
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def _stats_for_source(source_type: str, source_dir: Path) -> dict | None:
    if source_type == "manga109s":
        images_root = source_dir / "images"
        volumes = _count_volume_dirs(images_root)
        images = _count_images(images_root)
        annotations: list[str] = []

        if (source_dir / "annotations").is_dir():
            annotations.extend(["frame", "text", "face", "body", "character"])
        if (source_dir / "annotations_Manga109Dialog").is_dir():
            annotations.append("dialog")
        if (source_dir / "annotations_COO").is_dir():
            annotations.append("onomatopoeia")

        return {
            "volumes": volumes,
            "images": images,
            "annotations": annotations,
        }

    if source_type == "yolo":
        images = _count_images(source_dir / "images")
        return {
            "volumes": None,
            "images": images,
            "annotations": ["yolo"],
        }

    return None


def _build_source_public(source_dir: Path) -> dict | None:
    if not source_dir.is_dir():
        return None

    manifest = load_source_manifest(source_dir)
    source_type = detect_source_type(source_dir, manifest)
    label = source_dir.name
    if manifest:
        label = (
            manifest.get("label")
            or manifest.get("name")
            or manifest.get("id")
            or label
        )

    description = None
    if manifest and isinstance(manifest.get("description"), str):
        description = manifest["description"]

    stats = _stats_for_source(source_type, source_dir)

    return {
        "id": source_dir.name,
        "label": str(label),
        "type": source_type,
        "path": str(source_dir),
        "available": True,
        "description": description,
        "stats": stats,
    }


def _iter_source_dirs() -> list[Path]:
    if not TRAINING_SOURCES_ROOT.is_dir():
        return []
    return sorted(TRAINING_SOURCES_ROOT.iterdir(), key=lambda p: p.name)


def list_training_sources() -> list[dict]:
    sources: list[dict] = []
    for item in _iter_source_dirs():
        source = _build_source_public(item)
        if source:
            sources.append(source)

    return sources


def _build_prepared_dataset(dataset_dir: Path) -> dict:
    manifest = load_prepared_manifest(dataset_dir)
    dataset_id = dataset_dir.name
    created_at = None
    targets: list[str] = []
    val_split = None
    test_split = None
    image_mode = None
    seed = None
    stats: dict | None = None

    if manifest:
        dataset_id = str(manifest.get("dataset_id") or dataset_id)
        created_at = (
            str(manifest["created_at"])
            if isinstance(manifest.get("created_at"), str)
            else None
        )
        raw_targets = manifest.get("targets")
        if isinstance(raw_targets, list):
            targets = [str(item) for item in raw_targets]
        val_split = (
            float(manifest["val_split"])
            if isinstance(manifest.get("val_split"), (int, float))
            else None
        )
        test_split = (
            float(manifest["test_split"])
            if isinstance(manifest.get("test_split"), (int, float))
            else None
        )
        image_mode = (
            str(manifest["image_mode"])
            if isinstance(manifest.get("image_mode"), str)
            else None
        )
        seed = (
            int(manifest["seed"])
            if isinstance(manifest.get("seed"), int)
            else None
        )
        stats_data = manifest.get("stats")
        if isinstance(stats_data, dict):
            stats = {
                "train_images": int(stats_data.get("train_images", 0)),
                "val_images": int(stats_data.get("val_images", 0)),
                "test_images": int(stats_data.get("test_images", 0)),
                "train_labels": int(stats_data.get("train_labels", 0)),
                "val_labels": int(stats_data.get("val_labels", 0)),
                "test_labels": int(stats_data.get("test_labels", 0)),
            }

    return {
        "id": dataset_id,
        "path": str(dataset_dir),
        "created_at": created_at,
        "targets": targets,
        "val_split": val_split,
        "test_split": test_split,
        "image_mode": image_mode,
        "seed": seed,
        "stats": stats,
    }


def _iter_prepared_dirs() -> list[Path]:
    if not TRAINING_PREPARED_ROOT.is_dir():
        return []
    return sorted(TRAINING_PREPARED_ROOT.iterdir(), key=lambda p: p.name)


def list_prepared_datasets() -> list[dict]:
    datasets: list[dict] = []
    for item in _iter_prepared_dirs():
        if not item.is_dir():
            continue
        datasets.append(_build_prepared_dataset(item))

    return datasets


def detect_model_families() -> tuple[str, list[str]]:
    version = "unknown"
    families: list[str] = []
    allowed = {"yolo11", "yolo12", "yolo26"}

    try:
        import ultralytics

        version = str(getattr(ultralytics, "__version__", "unknown"))
        root = Path(ultralytics.__file__).resolve().parent
        models_dir = root / "cfg" / "models"
        found: set[str] = set()
        if models_dir.is_dir():
            for entry in models_dir.iterdir():
                if not entry.is_dir() or not entry.name.isdigit():
                    continue
                prefix = f"yolo{entry.name}"
                if any(
                    p.suffix == ".yaml" and p.name.startswith(prefix)
                    for p in entry.glob("*.yaml")
                ):
                    name = f"yolo{entry.name}"
                    if name in allowed:
                        found.add(name)
        families = sorted(found, key=lambda item: int(item.replace("yolo", "")))
    except Exception:
        families = []

    if not families:
        fallback = ["yolo11", "yolo12"]
        try:
            if version != "unknown" and Version(version) >= Version("8.4.0"):
                fallback.append("yolo26")
        except InvalidVersion:
            pass
        families = fallback

    return version, families


def resolve_training_sources(
    source_ids: list[str],
    *,
    allowed_types: set[str] | None = None,
) -> list[Path]:
    source_dirs: list[Path] = []
    for source_id in source_ids:
        try:
            source_dir = safe_join(TRAINING_SOURCES_ROOT, source_id)
        except ValueError as exc:
            raise ValueError("Invalid source path") from exc
        if not source_dir.is_dir():
            raise ValueError(f"Source not found: {source_id}")

        source_type = detect_source_type(source_dir, load_source_manifest(source_dir))
        if allowed_types and source_type not in allowed_types:
            raise ValueError(f"Unsupported source type for now: {source_type}")

        source_dirs.append(source_dir)

    return source_dirs


def resolve_prepared_dataset(dataset_id: str) -> Path:
    if not dataset_id:
        raise ValueError("Missing dataset_id")
    dataset_dir = safe_join(TRAINING_PREPARED_ROOT, dataset_id)
    if not dataset_dir.is_dir():
        raise ValueError(f"Prepared dataset not found: {dataset_id}")
    data_yaml = dataset_dir / "data.yaml"
    if not data_yaml.is_file():
        raise ValueError(f"Missing data.yaml for dataset: {dataset_id}")
    return dataset_dir
