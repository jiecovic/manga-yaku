# backend-python/core/usecases/page_translation/stage_outputs.py
"""Post-processing helpers for page-translation stage outputs."""

from __future__ import annotations

from typing import Any


def _coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def summarize_translate_stage_coverage(
    *,
    stage1_result: dict[str, Any],
    input_boxes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize how fully stage-1 output covers the input box set.

    This is intentionally non-fatal. The workflow can continue with partial
    output, but callers can surface a warning when boxes were omitted or
    duplicated so operators know the generation may have been truncated.
    """

    expected_box_ids: set[int] = set()
    for box in input_boxes:
        if not isinstance(box, dict):
            continue
        box_index = _coerce_positive_int(box.get("box_index"))
        if box_index is not None:
            expected_box_ids.add(box_index)

    coverage_counts: dict[int, int] = {}

    raw_no_text = stage1_result.get("no_text_boxes")
    if isinstance(raw_no_text, list):
        for item in raw_no_text:
            box_id = _coerce_positive_int(item)
            if box_id is None:
                continue
            coverage_counts[box_id] = coverage_counts.get(box_id, 0) + 1

    raw_boxes = stage1_result.get("boxes")
    if isinstance(raw_boxes, list):
        for entry in raw_boxes:
            if not isinstance(entry, dict):
                continue
            raw_ids = entry.get("box_ids")
            if not isinstance(raw_ids, list):
                continue
            for item in raw_ids:
                box_id = _coerce_positive_int(item)
                if box_id is None:
                    continue
                coverage_counts[box_id] = coverage_counts.get(box_id, 0) + 1

    covered_box_ids = set(coverage_counts)
    duplicate_box_ids = sorted(box_id for box_id, count in coverage_counts.items() if count > 1)
    unexpected_box_ids = sorted(
        box_id for box_id in covered_box_ids if box_id not in expected_box_ids
    )
    missing_box_ids = sorted(box_id for box_id in expected_box_ids if box_id not in covered_box_ids)
    covered_expected_box_count = sum(1 for box_id in covered_box_ids if box_id in expected_box_ids)

    return {
        "expected_box_count": len(expected_box_ids),
        "covered_box_count": covered_expected_box_count,
        "missing_box_ids": missing_box_ids,
        "unexpected_box_ids": unexpected_box_ids,
        "duplicate_box_ids": duplicate_box_ids,
        "is_complete": not missing_box_ids and not unexpected_box_ids and not duplicate_box_ids,
    }


def apply_no_text_consensus_guard(
    *,
    stage1_result: dict[str, Any],
    input_boxes: list[dict[str, Any]],
    ocr_profiles: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], list[int]]:
    """Enforce deterministic no-text consensus for stage-1 box outputs.

    Policy:
    - Hard rule only on strong remote no-text consensus:
      `remote_no_text_count >= 2` and `remote_text_count == 0`.
    - Otherwise keep stage-1 output as-is (agent decides mixed/ambiguous cases).

    Returns:
    - Adjusted stage-1 result payload.
    - Box indices that were force-moved to `no_text_boxes`.
    """
    source_by_index: dict[int, dict[str, Any]] = {}
    for box in input_boxes:
        if not isinstance(box, dict):
            continue
        box_index = _coerce_positive_int(box.get("box_index"))
        if box_index is None:
            continue
        source_by_index[box_index] = box

    remote_profile_ids: set[str] = set()
    if isinstance(ocr_profiles, list):
        for profile in ocr_profiles:
            if not isinstance(profile, dict):
                continue
            profile_id = str(profile.get("id") or "").strip()
            if not profile_id:
                continue
            model_id = str(profile.get("model") or "").strip().lower()
            if profile_id.startswith("openai_") or "gpt" in model_id:
                remote_profile_ids.add(profile_id)

    def _is_remote_profile(profile_id: str) -> bool:
        return profile_id in remote_profile_ids or profile_id.startswith("openai_")

    no_text_box_ids: set[int] = set()
    raw_no_text = stage1_result.get("no_text_boxes")
    if isinstance(raw_no_text, list):
        for item in raw_no_text:
            parsed = _coerce_positive_int(item)
            if parsed is not None:
                no_text_box_ids.add(parsed)

    adjusted_no_text: list[int] = []
    filtered_boxes: list[dict[str, Any]] = []
    raw_boxes = stage1_result.get("boxes")
    if not isinstance(raw_boxes, list):
        return stage1_result, adjusted_no_text

    for entry in raw_boxes:
        if not isinstance(entry, dict):
            continue
        raw_ids = entry.get("box_ids")
        if not isinstance(raw_ids, list):
            filtered_boxes.append(entry)
            continue
        parsed_box_ids = [_coerce_positive_int(item) for item in raw_ids]
        box_ids = [item for item in parsed_box_ids if item is not None]
        if len(box_ids) != 1:
            filtered_boxes.append(entry)
            continue
        box_index = box_ids[0]
        if box_index in no_text_box_ids:
            continue
        source_box = source_by_index.get(box_index)
        if not isinstance(source_box, dict):
            filtered_boxes.append(entry)
            continue

        raw_no_text_profiles = source_box.get("ocr_no_text_profiles")
        no_text_profiles = raw_no_text_profiles if isinstance(raw_no_text_profiles, list) else []
        remote_no_text_count = 0
        for profile_id in no_text_profiles:
            pid = str(profile_id or "").strip()
            if pid and _is_remote_profile(pid):
                remote_no_text_count += 1

        remote_text_count = 0
        raw_candidates = source_box.get("ocr_candidates")
        if isinstance(raw_candidates, list):
            for candidate in raw_candidates:
                if not isinstance(candidate, dict):
                    continue
                pid = str(candidate.get("profile_id") or "").strip()
                text = str(candidate.get("text") or "").strip()
                if pid and text and _is_remote_profile(pid):
                    remote_text_count += 1

        # Strong consensus fallback: multiple remote no-text signals with no
        # remote positive text candidate override stage-1 text for this box.
        if remote_no_text_count >= 2 and remote_text_count == 0:
            no_text_box_ids.add(box_index)
            adjusted_no_text.append(box_index)
            continue

        filtered_boxes.append(entry)

    adjusted_result = dict(stage1_result)
    adjusted_result["boxes"] = filtered_boxes
    adjusted_result["no_text_boxes"] = sorted(no_text_box_ids)
    return adjusted_result, adjusted_no_text
