# backend-python/core/usecases/ocr/selection.py
"""Shared OCR candidate selection helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def choose_preferred_ocr_text(
    candidates_by_profile: Mapping[str, str],
    *,
    preferred_profile_ids: Iterable[str],
) -> str:
    """Return the best available OCR text for one box.

    Preferred profiles are checked first, then the remaining non-empty candidates
    are used as a stable fallback in insertion order.
    """
    for profile_id in preferred_profile_ids:
        candidate = str(candidates_by_profile.get(profile_id) or "").strip()
        if candidate:
            return candidate

    for candidate in candidates_by_profile.values():
        resolved = str(candidate or "").strip()
        if resolved:
            return resolved
    return ""


def select_box_ocr_texts(
    candidates_by_box: Mapping[int, Mapping[str, str]],
    *,
    box_ids: Iterable[int],
    preferred_profile_ids: Iterable[str],
) -> dict[int, str]:
    """Select the best OCR text per box from per-profile candidates."""
    selected: dict[int, str] = {}
    seen_box_ids: set[int] = set()
    for raw_box_id in box_ids:
        box_id = int(raw_box_id)
        if box_id <= 0 or box_id in seen_box_ids:
            continue
        seen_box_ids.add(box_id)
        chosen = choose_preferred_ocr_text(
            candidates_by_box.get(box_id, {}),
            preferred_profile_ids=preferred_profile_ids,
        )
        if chosen:
            selected[box_id] = chosen
    return selected
