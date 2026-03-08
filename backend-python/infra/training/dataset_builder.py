# backend-python/infra/training/dataset_builder.py
"""Dataset preparation helpers for model training jobs."""

from __future__ import annotations

import json
import os
import random
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import TRAINING_PREPARED_ROOT
from infra.jobs.exceptions import JobCanceled
from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_TARGETS = {"panel", "text", "face", "body"}
ALLOWED_LINK_MODES = {"copy", "hardlink"}
ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]


@dataclass
class BuildStats:
    train_images: int = 0
    val_images: int = 0
    test_images: int = 0
    train_labels: int = 0
    val_labels: int = 0
    test_labels: int = 0


class DatasetBuildError(RuntimeError):
    pass


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _sanitize_dataset_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
    safe = safe.strip("-")
    return safe or "dataset"


def _default_dataset_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"dataset-{stamp}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_target_names(targets: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in targets or ["text"]:
        normalized = str(raw or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out or ["text"]


def _canonical_source_annotation_tag(tag: str) -> str:
    """Map source-dataset annotation names onto our canonical training targets."""
    normalized = str(tag or "").strip().lower()
    if normalized == "frame":
        return "panel"
    return normalized


def _write_yaml(path: Path, names: list[str], *, has_test: bool) -> None:
    dataset_root = path.parent
    content = [
        f"path: {dataset_root.as_posix()}",
        "train: images/train",
        "val: images/val",
    ]
    if has_test:
        content.append("test: images/test")
    content.extend(
        [
            "",
            "names:",
        ]
    )
    for idx, name in enumerate(names):
        content.append(f"  {idx}: {name}")
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def _xyminmax_to_yolo(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    img_w: int,
    img_h: int,
) -> tuple[float, float, float, float]:
    w = xmax - xmin
    h = ymax - ymin
    xc = (xmin + xmax) / 2.0 / img_w
    yc = (ymin + ymax) / 2.0 / img_h
    bw = w / img_w
    bh = h / img_h
    return xc, yc, bw, bh


def _write_image(
    src: Path,
    dst: Path,
    *,
    link_mode: str,
) -> None:
    if dst.exists():
        dst.unlink()

    if link_mode == "copy":
        shutil.copy2(src, dst)
        return

    if link_mode == "hardlink":
        try:
            os.link(src, dst)
        except OSError as exc:
            raise DatasetBuildError(f"Hardlink failed for {src.name}: {exc}") from exc
        return

    raise DatasetBuildError(f"Unsupported link mode: {link_mode}")


def _choose_split(rng: random.Random, val_split: float, test_split: float) -> str:
    roll = rng.random()
    if roll < val_split:
        return "val"
    if roll < val_split + test_split:
        return "test"
    return "train"


def _iter_xml_files(annotations_dir: Path) -> Iterable[Path]:
    return sorted(annotations_dir.glob("*.xml"))


def _manga109s_image_path(images_dir: Path, book: str, index: int) -> Path:
    return images_dir / book / f"{index:03d}.jpg"


def _count_manga109s_volumes(source_dir: Path) -> int:
    images_dir = source_dir / "images"
    annotations_dir = source_dir / "annotations"
    if not images_dir.is_dir() or not annotations_dir.is_dir():
        return 0

    total = 0
    for xml_file in _iter_xml_files(annotations_dir):
        tree = ET.parse(xml_file)
        root = tree.getroot()
        book_title = root.attrib.get("title", xml_file.stem)
        pages_el = root.find("pages")
        if pages_el is None:
            continue
        has_page = False
        for page in pages_el.findall("page"):
            idx = int(page.attrib["index"])
            img_path = _manga109s_image_path(images_dir, book_title, idx)
            if img_path.is_file():
                has_page = True
                break
        if has_page:
            total += 1
    return total


def _prepare_manga109s(
    source_dir: Path,
    out_dir: Path,
    targets: list[str],
    val_split: float,
    test_split: float,
    link_mode: str,
    seed: int,
    *,
    progress_cb: ProgressCallback | None,
    is_canceled: CancelCallback | None,
    progress_state: dict[str, int],
    total_volumes: int,
) -> BuildStats:
    images_dir = source_dir / "images"
    annotations_dir = source_dir / "annotations"

    if not images_dir.is_dir():
        raise DatasetBuildError(f"Missing images dir: {images_dir}")
    if not annotations_dir.is_dir():
        raise DatasetBuildError(f"Missing annotations dir: {annotations_dir}")

    rng = random.Random(seed)
    class_map = {tag: idx for idx, tag in enumerate(targets)}

    stats = BuildStats()

    for xml_file in _iter_xml_files(annotations_dir):
        _raise_if_canceled(is_canceled)
        tree = ET.parse(xml_file)
        root = tree.getroot()
        book_title = root.attrib.get("title", xml_file.stem)
        pages_el = root.find("pages")
        if pages_el is None:
            continue

        split = _choose_split(rng, val_split, test_split)
        pages_processed = 0
        for page in pages_el.findall("page"):
            _raise_if_canceled(is_canceled)
            idx = int(page.attrib["index"])
            img_path = _manga109s_image_path(images_dir, book_title, idx)
            if not img_path.is_file():
                continue

            label_lines: list[str] = []
            with Image.open(img_path) as im:
                img_w, img_h = im.size

            for elem in page:
                tag = _canonical_source_annotation_tag(elem.tag)
                if tag not in class_map:
                    continue
                try:
                    xmin = float(elem.attrib["xmin"])
                    ymin = float(elem.attrib["ymin"])
                    xmax = float(elem.attrib["xmax"])
                    ymax = float(elem.attrib["ymax"])
                except KeyError:
                    continue

                xc, yc, bw, bh = _xyminmax_to_yolo(xmin, ymin, xmax, ymax, img_w, img_h)
                label_lines.append(f"{class_map[tag]} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")

            out_name = f"m109_{book_title}_{idx:03d}.jpg"
            out_img = out_dir / "images" / split / out_name
            out_lbl = out_dir / "labels" / split / out_name.replace(".jpg", ".txt")

            _ensure_dir(out_img.parent)
            _ensure_dir(out_lbl.parent)

            _write_image(img_path, out_img, link_mode=link_mode)
            out_lbl.write_text("\n".join(label_lines), encoding="utf-8")

            pages_processed += 1

            if split == "train":
                stats.train_images += 1
                stats.train_labels += len(label_lines)
            elif split == "val":
                stats.val_images += 1
                stats.val_labels += len(label_lines)
            else:
                stats.test_images += 1
                stats.test_labels += len(label_lines)

        if pages_processed:
            progress_state["processed"] += 1
            if progress_cb:
                progress_cb(
                    progress_state["processed"],
                    total_volumes,
                    f"{book_title} ({pages_processed} pages)",
                )

    return stats


def _raise_if_canceled(is_canceled: CancelCallback | None) -> None:
    if is_canceled is None:
        return
    try:
        canceled = bool(is_canceled())
    except Exception:
        canceled = False
    if canceled:
        raise JobCanceled("Canceled")


def prepare_dataset(
    *,
    dataset_id: str | None,
    source_dirs: list[Path],
    targets: list[str] | None = None,
    val_split: float = 0.15,
    test_split: float = 0.0,
    link_mode: str = "copy",
    seed: int = 1337,
    overwrite: bool = False,
    progress_cb: ProgressCallback | None = None,
    is_canceled: CancelCallback | None = None,
) -> tuple[str, Path, BuildStats]:
    selected_targets = _canonical_target_names(targets)
    invalid_targets = [tag for tag in selected_targets if tag not in ALLOWED_TARGETS]
    if invalid_targets:
        raise DatasetBuildError("Unsupported targets: " + ", ".join(sorted(invalid_targets)))

    if val_split <= 0 or val_split >= 1:
        raise DatasetBuildError("valSplit must be between 0 and 1")
    if test_split < 0 or test_split >= 1:
        raise DatasetBuildError("testSplit must be between 0 and 1")
    if val_split + test_split >= 1:
        raise DatasetBuildError("valSplit + testSplit must be less than 1")
    if link_mode not in ALLOWED_LINK_MODES:
        raise DatasetBuildError("linkMode must be one of: " + ", ".join(sorted(ALLOWED_LINK_MODES)))

    dataset_id = _sanitize_dataset_id(dataset_id or _default_dataset_id())
    out_dir = TRAINING_PREPARED_ROOT / dataset_id

    if out_dir.exists() and not overwrite:
        raise DatasetBuildError(f"Dataset '{dataset_id}' already exists")

    if out_dir.exists() and overwrite:
        if out_dir.is_dir():
            shutil.rmtree(out_dir)
        else:
            out_dir.unlink()

    _ensure_dir(out_dir)

    try:
        _raise_if_canceled(is_canceled)
        stats = BuildStats()
        total_volumes = sum(_count_manga109s_volumes(source_dir) for source_dir in source_dirs)
        if total_volumes == 0:
            raise DatasetBuildError("No volumes found for selected sources")

        progress_state = {"processed": 0}

        for source_dir in source_dirs:
            _raise_if_canceled(is_canceled)
            stats_for_source = _prepare_manga109s(
                source_dir=source_dir,
                out_dir=out_dir,
                targets=selected_targets,
                val_split=val_split,
                test_split=test_split,
                link_mode=link_mode,
                seed=seed,
                progress_cb=progress_cb,
                is_canceled=is_canceled,
                progress_state=progress_state,
                total_volumes=total_volumes,
            )
            stats.train_images += stats_for_source.train_images
            stats.val_images += stats_for_source.val_images
            stats.test_images += stats_for_source.test_images
            stats.train_labels += stats_for_source.train_labels
            stats.val_labels += stats_for_source.val_labels
            stats.test_labels += stats_for_source.test_labels

        _raise_if_canceled(is_canceled)
        _write_yaml(out_dir / "data.yaml", selected_targets, has_test=test_split > 0)

        manifest = {
            "dataset_id": dataset_id,
            "created_at": _utc_now_iso(),
            "targets": selected_targets,
            "val_split": val_split,
            "test_split": test_split,
            "image_mode": link_mode,
            "seed": seed,
            "sources": [str(p) for p in source_dirs],
            "stats": {
                "train_images": stats.train_images,
                "val_images": stats.val_images,
                "test_images": stats.test_images,
                "train_labels": stats.train_labels,
                "val_labels": stats.val_labels,
                "test_labels": stats.test_labels,
            },
        }
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        return dataset_id, out_dir, stats
    except JobCanceled:
        if out_dir.exists():
            if out_dir.is_dir():
                shutil.rmtree(out_dir, ignore_errors=True)
            else:
                out_dir.unlink(missing_ok=True)
        raise
