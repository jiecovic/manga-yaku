# backend-python/core/workflows/page_translation/persistence/payloads.py
"""Payload shaping and persistence helpers for the page-translation workflow."""

from __future__ import annotations

import logging
from typing import Any

from core.usecases.ocr.profiles.registry import get_ocr_profile
from infra.db.store_boxes import (
    delete_boxes_by_ids,
    set_box_ocr_text_by_id,
    set_box_order_for_type,
    set_box_translation_by_id,
)
from infra.logging.correlation import append_correlation

logger = logging.getLogger(__name__)


def build_ocr_profile_meta(profile_ids: list[str]) -> list[dict[str, Any]]:
    """Build compact OCR profile metadata for downstream prompts/logs."""
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
    """Build the stage-1 translation payload and box-index map."""
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
    """Apply the translated stage payload back onto persisted text boxes."""
    translations = translation_payload.get("boxes", [])
    no_text_raw = translation_payload.get("no_text_boxes")
    no_text_box_indices: set[int] = set()
    if isinstance(no_text_raw, list):
        for item in no_text_raw:
            try:
                no_text_box_indices.add(int(item))
            except (TypeError, ValueError):
                continue

    expected_indices = set(box_index_map.keys())
    seen_indices: set[int] = set()
    duplicate_indices: set[int] = set()
    unknown_indices: set[int] = set()

    for box_index in sorted(no_text_box_indices):
        if box_index in seen_indices:
            duplicate_indices.add(box_index)
        seen_indices.add(box_index)
        if box_index not in expected_indices:
            unknown_indices.add(box_index)

    if isinstance(translations, list):
        for entry in translations:
            if not isinstance(entry, dict):
                continue
            box_ids_raw = entry.get("box_ids")
            if not isinstance(box_ids_raw, list):
                single_id = entry.get("box_id")
                if single_id is None:
                    continue
                box_ids_raw = [single_id]

            normalized_box_indices: list[int] = []
            seen_in_entry: set[int] = set()
            for item in box_ids_raw:
                try:
                    box_index = int(item)
                except (TypeError, ValueError):
                    continue
                if box_index in seen_in_entry:
                    continue
                seen_in_entry.add(box_index)
                normalized_box_indices.append(box_index)

            for box_index in normalized_box_indices:
                if box_index in seen_indices:
                    duplicate_indices.add(box_index)
                seen_indices.add(box_index)
                if box_index not in expected_indices:
                    unknown_indices.add(box_index)

    missing_indices = expected_indices - seen_indices
    if duplicate_indices or unknown_indices:
        problems: list[str] = []
        if duplicate_indices:
            problems.append(f"duplicate indices {sorted(duplicate_indices)}")
        if unknown_indices:
            problems.append(f"unknown indices {sorted(unknown_indices)}")
        detail = ", ".join(problems) if problems else "invalid stage-1 coverage"
        raise RuntimeError(f"Stage-1 box coverage mismatch: {detail}")
    coverage_warning: str | None = None
    if missing_indices:
        coverage_warning = (
            f"Stage-1 omitted indices {sorted(missing_indices)}; preserving unmatched boxes"
        )
        logger.warning(
            append_correlation(
                coverage_warning,
                {
                    "component": "page_translation.coverage",
                    "volume_id": volume_id,
                    "filename": filename,
                },
            )
        )

    updated = 0
    merged_ids: list[int] = []
    no_text_ids: list[int] = []
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

    for box_index in sorted(no_text_box_indices):
        mapped = box_index_map.get(box_index)
        if isinstance(mapped, int):
            no_text_ids.append(mapped)

    applied_order = False
    if no_text_ids:
        delete_boxes_by_ids(volume_id, filename, no_text_ids)
    if merged_ids:
        delete_boxes_by_ids(volume_id, filename, merged_ids)

    if ordered_primary_ids:
        removed_ids = set(no_text_ids) | set(merged_ids)
        preserved_ids: list[int] = []
        for box in text_boxes:
            try:
                box_id = int(box.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if box_id <= 0 or box_id in removed_ids:
                continue
            if box_id not in ordered_primary_ids:
                preserved_ids.append(box_id)
        # Keep explicit translated reading order first, then append untouched boxes
        # in their existing order so persisted ordering remains total and stable.
        final_ordered_ids = ordered_primary_ids + preserved_ids
        applied_order = set_box_order_for_type(
            volume_id,
            filename,
            box_type="text",
            ordered_ids=final_ordered_ids,
        )

    result = {
        "updated": updated,
        "orderApplied": applied_order,
        "processed": len(text_boxes),
        "total": len(text_boxes),
    }
    if coverage_warning:
        result["coverageWarning"] = coverage_warning
    return result
