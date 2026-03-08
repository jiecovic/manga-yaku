# backend-python/core/usecases/page_translation/runtime/diagnostics.py
"""Diagnostics helpers for page-translation runtime stages."""

from __future__ import annotations

from typing import Any


def build_translate_stage_warnings(
    *,
    stage1_debug: dict[str, Any],
    coverage: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    missing_box_ids = coverage["missing_box_ids"]
    if missing_box_ids:
        warning = (
            f"Translate stage output omitted {len(missing_box_ids)} input boxes: {missing_box_ids}."
        )
        if str(stage1_debug.get("finish_reason") or "").strip() == "incomplete:max_output_tokens":
            warning += (
                " The model output was truncated; consider increasing "
                "page-translation max_output_tokens."
            )
        warnings.append(warning)
    if coverage["duplicate_box_ids"]:
        warnings.append(
            "Translate stage output covered some boxes multiple times: "
            f"{coverage['duplicate_box_ids']}."
        )
    if coverage["unexpected_box_ids"]:
        warnings.append(
            "Translate stage output referenced unexpected box indices: "
            f"{coverage['unexpected_box_ids']}."
        )
    return warnings


def build_debug_payload(
    *,
    debug_id: str | None,
    volume_id: str,
    filename: str,
    image_debug: dict[str, Any],
    ocr_profiles: list[dict[str, Any]] | None,
    boxes: list[dict[str, Any]],
    system_prompt: str,
    user_content: str,
    stage1_debug: dict[str, Any],
    stage1_result: dict[str, Any],
    merge_system_prompt: str,
    merge_user_content: str,
    stage2_debug: dict[str, Any],
    stage2_result: dict[str, Any],
    stage2_error: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "job_id": debug_id,
        "volume_id": volume_id,
        "filename": filename,
        "correlation": {
            "component": "page_translation",
            "job_id": debug_id,
            "volume_id": volume_id,
            "filename": filename,
        },
        "image": image_debug,
        "ocr_profiles": ocr_profiles,
        "boxes": boxes,
        "calls": {
            "translate": {
                **stage1_debug,
                "system_prompt": system_prompt,
                "user_prompt": user_content,
                "result": stage1_result,
            },
            "merge": {
                **stage2_debug,
                "system_prompt": merge_system_prompt,
                "user_prompt": merge_user_content,
                "result": stage2_result,
                "error": stage2_error,
            },
        },
        "result": result,
    }
