# backend-python/core/workflows/page_translation/helpers.py
"""Shared helper utilities for the page-translation workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.usecases.ocr.profiles.registry import get_ocr_profile
from core.usecases.ocr.profiles.settings import page_translation_enabled_ocr_profiles
from core.usecases.settings.service import (
    resolve_detection_settings,
    resolve_ocr_parallelism_settings,
)

from . import payloads as _payloads
from .types import (
    CancelCheck,
    PageTranslationWorkflowSnapshot,
    ProgressCallback,
    WorkflowState,
)

__all__ = [
    "apply_translation_payload",
    "build_ocr_profile_meta",
    "build_translation_boxes",
    "emit_progress",
    "is_canceled",
    "resolve_detection_profile_id",
    "resolve_ocr_profiles",
    "resolve_parallel_limits",
    "utc_now_iso",
]

build_ocr_profile_meta = _payloads.build_ocr_profile_meta
build_translation_boxes = _payloads.build_translation_boxes
apply_translation_payload = _payloads.apply_translation_payload


def utc_now_iso() -> str:
    """Handle utc now iso."""
    return datetime.now(timezone.utc).isoformat()


def resolve_detection_profile_id(preferred_profile_id: str | None) -> str | None:
    """Resolve detection profile id."""
    if preferred_profile_id:
        return preferred_profile_id
    stored_profile_id = resolve_detection_settings().page_translation_detection_profile_id
    if stored_profile_id:
        return stored_profile_id
    return None


def resolve_ocr_profiles(payload: dict[str, Any]) -> list[str]:
    """Resolve ocr profiles."""
    raw = payload.get("ocrProfiles")
    requested = [str(item).strip() for item in raw or [] if str(item).strip()]
    profile_ids = requested or page_translation_enabled_ocr_profiles()
    if not profile_ids:
        profile_ids = ["manga_ocr_default"]

    resolved: list[str] = []
    seen: set[str] = set()
    for profile_id in profile_ids:
        if profile_id in seen:
            continue
        seen.add(profile_id)
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        if not profile.get("enabled", True):
            continue
        resolved.append(profile_id)

    if not resolved:
        try:
            fallback = get_ocr_profile("manga_ocr_default")
            if fallback.get("enabled", True):
                resolved = ["manga_ocr_default"]
        except Exception:
            pass

    if not resolved:
        raise RuntimeError("No enabled OCR profiles configured")

    return resolved


def resolve_parallel_limits() -> tuple[int, int]:
    """Resolve parallel limits."""
    settings = resolve_ocr_parallelism_settings()
    return (settings.local, settings.remote)


def emit_progress(
    *,
    state: WorkflowState,
    stage: str,
    progress: int,
    message: str,
    detection_profile_id: str | None,
    detected_boxes: int,
    ocr_tasks_total: int,
    ocr_tasks_done: int,
    updated_boxes: int,
    workflow_run_id: str,
    on_progress: ProgressCallback | None,
) -> None:
    """Emit progress."""
    if on_progress is None:
        return
    on_progress(
        PageTranslationWorkflowSnapshot(
            state=state,
            stage=stage,
            progress=progress,
            message=message,
            detection_profile_id=detection_profile_id,
            detected_boxes=detected_boxes,
            ocr_tasks_total=ocr_tasks_total,
            ocr_tasks_done=ocr_tasks_done,
            updated_boxes=updated_boxes,
            workflow_run_id=workflow_run_id,
        )
    )


def is_canceled(check: CancelCheck | None) -> bool:
    """Return whether canceled."""
    return bool(check and check())
