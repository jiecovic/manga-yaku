# backend-python/api/services/volumes_helpers.py
"""Shared helper functions for volume/page file and ordering operations."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile
from infra.db.db_store import get_max_page_index, list_pages, volume_name_exists

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def sanitize_volume_id(name: str) -> str:
    """Create a filesystem-safe, URL-safe volume id from a display name."""

    cleaned = name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", cleaned)
    cleaned = cleaned.strip("-_")
    return cleaned


def calculate_next_index(volume_dir: Path) -> int:
    """Return the next numeric filename index (1-based) for a volume folder."""

    max_index = 0
    for entry in volume_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
            stem = entry.stem
            if stem.isdigit():
                max_index = max(max_index, int(stem))
    return max_index + 1


def unique_volume_name(base: str) -> str:
    """Return a display name that does not collide with existing volume names."""

    candidate = base
    suffix = 2
    while volume_name_exists(candidate):
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def page_exists(volume_dir: Path, index: int) -> bool:
    """Check whether a numeric page filename already exists for any supported extension."""

    stem = f"{index:04d}"
    return any((volume_dir / f"{stem}{ext}").exists() for ext in IMAGE_EXTENSIONS)


def resolve_image_extension(file: UploadFile) -> str:
    """Resolve output image extension from upload filename/content-type."""

    if file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            return suffix

    content_type = (file.content_type or "").lower()
    if content_type == "image/jpeg":
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"

    raise HTTPException(status_code=400, detail="Unsupported image type")


def resolve_insert_index(
    volume_id: str,
    *,
    insert_before: str | None,
    insert_after: str | None,
) -> float:
    """Compute fractional `page_index` for insertion before/after a target page."""

    pages = list_pages(volume_id)
    if not pages:
        return 1.0

    if insert_before:
        target_idx = next(
            (idx for idx, page in enumerate(pages) if page.filename == insert_before),
            None,
        )
        if target_idx is None:
            raise HTTPException(status_code=400, detail="insert_before not found")
        target_index = pages[target_idx].page_index or float(target_idx + 1)
        prev_index = pages[target_idx - 1].page_index if target_idx > 0 else None
        if prev_index is None:
            return target_index - 1.0
        return (prev_index + target_index) / 2.0

    if insert_after:
        target_idx = next(
            (idx for idx, page in enumerate(pages) if page.filename == insert_after),
            None,
        )
        if target_idx is None:
            raise HTTPException(status_code=400, detail="insert_after not found")
        target_index = pages[target_idx].page_index or float(target_idx + 1)
        next_index = (
            pages[target_idx + 1].page_index
            if target_idx + 1 < len(pages)
            else None
        )
        if next_index is None:
            return target_index + 1.0
        return (target_index + next_index) / 2.0

    max_index = get_max_page_index(volume_id)
    return (max_index or float(len(pages))) + 1.0

