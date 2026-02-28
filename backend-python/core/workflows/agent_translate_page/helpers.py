"""Shared helper utilities for the agent translate page workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.usecases.ocr.profile_settings import agent_enabled_ocr_profiles
from core.usecases.ocr.profiles import get_ocr_profile
from core.usecases.settings.service import (
    resolve_detection_settings,
    resolve_ocr_parallelism_settings,
)
from infra.db.db_store import (
    delete_boxes_by_ids,
    set_box_ocr_text_by_id,
    set_box_order_for_type,
    set_box_translation_by_id,
)

from .types import (
    AgentTranslateWorkflowSnapshot,
    CancelCheck,
    ProgressCallback,
    WorkflowState,
)

__all__ = [
    "apply_translation_payload",
    "build_ocr_profile_meta",
    "build_translation_boxes",
    "emit_progress",
    "is_canceled",
    "list_text_boxes",
    "resolve_detection_profile_id",
    "resolve_ocr_profiles",
    "resolve_parallel_limits",
    "utc_now_iso",
]


def utc_now_iso() -> str:
    """Handle utc now iso."""
    return datetime.now(timezone.utc).isoformat()


def resolve_detection_profile_id(preferred_profile_id: str | None) -> str | None:
    """Resolve detection profile id."""
    if preferred_profile_id:
        return preferred_profile_id
    stored_profile_id = resolve_detection_settings().agent_detection_profile_id
    if stored_profile_id:
        return stored_profile_id
    return None


def resolve_ocr_profiles(payload: dict[str, Any]) -> list[str]:
    """Resolve ocr profiles."""
    raw = payload.get("ocrProfiles")
    requested = [str(item).strip() for item in raw or [] if str(item).strip()]
    profile_ids = requested or agent_enabled_ocr_profiles()
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


def list_text_boxes(page: dict[str, Any]) -> list[dict[str, Any]]:
    """List text boxes."""
    raw_boxes = page.get("boxes", []) if isinstance(page, dict) else []
    text_boxes = [box for box in raw_boxes if box.get("type") == "text"]
    text_boxes.sort(
        key=lambda box: (
            int(box.get("orderIndex") or 10**9),
            int(box.get("id") or 0),
        )
    )
    return text_boxes


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
        AgentTranslateWorkflowSnapshot(
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


def build_ocr_profile_meta(profile_ids: list[str]) -> list[dict[str, Any]]:
    """Handle build ocr profile meta."""
    meta: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        cfg = profile.get("config", {}) or {}
        model = cfg.get("model") or cfg.get("model_path") or profile.get("provider")
        meta.append(
            {
                "id": profile_id,
                "model": str(model) if model is not None else "",
                "hint": profile.get("llm_hint", ""),
            }
        )
    return meta


def build_translation_boxes(
    *,
    text_boxes: list[dict[str, Any]],
    candidates: dict[int, dict[str, str]],
    no_text_candidates: dict[int, set[str]],
    error_candidates: dict[int, set[str]],
    invalid_candidates: dict[int, set[str]],
    llm_profiles: set[str],
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    """Handle build translation boxes."""
    payload_boxes: list[dict[str, Any]] = []
    box_index_map: dict[int, int] = {}
    next_box_index = 1

    for box in text_boxes:
        box_id = int(box.get("id") or 0)
        ocr_list = [
            {"profile_id": pid, "text": text}
            for pid, text in candidates.get(box_id, {}).items()
            if isinstance(text, str) and text.strip()
        ]
        raw_index = int(box.get("orderIndex") or 0)
        box_index = raw_index if raw_index > 0 else 0
        if box_index <= 0 or box_index in box_index_map:
            box_index = next_box_index
            while box_index in box_index_map:
                box_index += 1
        box_index_map[box_index] = box_id
        next_box_index = max(next_box_index, box_index + 1)
        no_text_profiles = sorted(pid for pid in no_text_candidates.get(box_id, set()))
        error_profiles = sorted(
            pid for pid in error_candidates.get(box_id, set()) if pid not in llm_profiles
        )
        invalid_profiles = sorted(
            pid for pid in invalid_candidates.get(box_id, set()) if pid not in llm_profiles
        )
        payload_box: dict[str, Any] = {
            "box_index": box_index,
            "ocr_candidates": ocr_list,
        }
        if no_text_profiles:
            payload_box["ocr_no_text_profiles"] = no_text_profiles
        if error_profiles:
            payload_box["ocr_error_profiles"] = error_profiles
        if invalid_profiles:
            payload_box["ocr_invalid_profiles"] = invalid_profiles
        payload_boxes.append(payload_box)

    return payload_boxes, box_index_map


def apply_translation_payload(
    *,
    volume_id: str,
    filename: str,
    text_boxes: list[dict[str, Any]],
    box_index_map: dict[int, int],
    translation_payload: dict[str, Any],
) -> dict[str, Any]:
    """Handle apply translation payload."""
    translations = translation_payload.get("boxes", [])
    no_text_raw = translation_payload.get("no_text_boxes")
    no_text_box_indices: set[int] = set()
    if isinstance(no_text_raw, list):
        for item in no_text_raw:
            try:
                no_text_box_indices.add(int(item))
            except (TypeError, ValueError):
                continue

    updated = 0
    merged_ids: list[int] = []
    ordered_primary_ids: list[int] = []

    for entry in translations:
        box_ids_raw = entry.get("box_ids")
        if not isinstance(box_ids_raw, list):
            single_id = entry.get("box_id")
            if single_id is None:
                continue
            box_ids_raw = [single_id]

        box_indices: list[int] = []
        for item in box_ids_raw:
            try:
                box_indices.append(int(item))
            except (TypeError, ValueError):
                continue
        if not box_indices:
            continue
        if any(box_index in no_text_box_indices for box_index in box_indices):
            continue

        mapped_ids = [box_index_map.get(box_index) for box_index in box_indices]
        box_ids = [box_id for box_id in mapped_ids if isinstance(box_id, int)]
        if not box_ids:
            continue

        primary_id = box_ids[0]
        ordered_primary_ids.append(primary_id)
        if len(box_ids) > 1:
            merged_ids.extend(box_ids[1:])

        ocr_text = entry.get("ocr_text")
        if isinstance(ocr_text, str):
            set_box_ocr_text_by_id(
                volume_id,
                filename,
                box_id=primary_id,
                ocr_text=ocr_text,
            )

        translation = entry.get("translation")
        if isinstance(translation, str):
            set_box_translation_by_id(
                volume_id,
                filename,
                box_id=primary_id,
                translation=translation,
            )
            updated += 1

    applied_order = False
    current_ids = {int(box.get("id") or 0) for box in text_boxes}
    mentioned_ids = set(ordered_primary_ids) | set(merged_ids)
    orphaned = list(current_ids - mentioned_ids)
    if orphaned:
        delete_boxes_by_ids(volume_id, filename, orphaned)
    if merged_ids:
        delete_boxes_by_ids(volume_id, filename, merged_ids)

    if ordered_primary_ids:
        applied_order = set_box_order_for_type(
            volume_id,
            filename,
            box_type="text",
            ordered_ids=ordered_primary_ids,
        )

    return {
        "updated": updated,
        "orderApplied": applied_order,
        "processed": len(text_boxes),
        "total": len(text_boxes),
    }
