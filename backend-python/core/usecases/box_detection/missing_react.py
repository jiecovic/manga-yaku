# backend-python/core/usecases/box_detection/missing_react.py
"""Experimental orchestration entrypoint for the missing-box ReAct prototype."""

from __future__ import annotations

from typing import Any

from infra.db.db_store import create_detection_run, load_page, replace_boxes_for_type
from infra.images.image_ops import encode_image_data_url, load_volume_image, resize_for_llm
from infra.llm import create_openai_client, has_openai_sdk

from . import missing_react_runtime as _runtime
from .missing_react_config import (
    RuntimeEventCallback,
    _emit_runtime_event,
    _normalize_cfg,
)
from .missing_react_geometry import (
    _box_iou,
    _encode_crop_data_url,
    _hint_looks_like_literal_text,
    _is_useful_observed_text,
    _list_existing_text_boxes,
    _normalize_candidate_bbox,
    _observed_matches_hint,
    _retry_candidate_box,
    _to_original_box,
    _to_resized_box,
)
from .missing_react_llm import (
    _adjust_candidate_box,
    _propose_missing_candidates,
    _verify_candidate_crop,
)


# Experimental: keep the prototype loop isolated here so the stable detection
# pipeline does not depend on the current ReAct heuristics.
def _bind_runtime_dependencies() -> None:
    # Experimental: runtime helpers are isolated in a separate module, but we
    # still bind through this module so tests can patch the historic symbols.
    _runtime._box_iou = _box_iou
    _runtime._encode_crop_data_url = _encode_crop_data_url
    _runtime._hint_looks_like_literal_text = _hint_looks_like_literal_text
    _runtime._is_useful_observed_text = _is_useful_observed_text
    _runtime._normalize_candidate_bbox = _normalize_candidate_bbox
    _runtime._observed_matches_hint = _observed_matches_hint
    _runtime._retry_candidate_box = _retry_candidate_box
    _runtime._to_original_box = _to_original_box
    _runtime._to_resized_box = _to_resized_box
    _runtime._adjust_candidate_box = _adjust_candidate_box
    _runtime._verify_candidate_crop = _verify_candidate_crop


def detect_missing_text_boxes_react(
    *,
    volume_id: str,
    filename: str,
    model_id: str | None = None,
    max_candidates: int = 8,
    max_attempts_per_candidate: int = 3,
    min_confidence: float = 0.75,
    overlap_iou_threshold: float = 0.45,
    max_image_side: int = 1536,
    crop_padding_px: int = 6,
    on_runtime_event: RuntimeEventCallback | None = None,
) -> dict[str, Any]:
    """
    Experimental multimodal propose/verify/adjust loop for missing text boxes.

    This code path is still being tuned, so the unstable helper logic lives in
    the dedicated experimental modules next to this entrypoint.
    """
    cfg = _normalize_cfg(
        model_id=model_id,
        max_candidates=max_candidates,
        max_attempts_per_candidate=max_attempts_per_candidate,
        min_confidence=min_confidence,
        overlap_iou_threshold=overlap_iou_threshold,
        max_image_side=max_image_side,
        crop_padding_px=crop_padding_px,
    )
    if not has_openai_sdk():
        raise RuntimeError("OpenAI SDK is not available for missing-box detection")
    _emit_runtime_event(
        on_runtime_event,
        {
            "phase": "propose",
            "status": "started",
            "progress": 8,
            "message": "Proposing missing text regions",
        },
    )

    page = load_page(volume_id, filename)
    existing_text_boxes = _list_existing_text_boxes(page)
    source_image = load_volume_image(volume_id, filename)
    resized_image = resize_for_llm(source_image, max_side=cfg.max_image_side)
    page_data_url = encode_image_data_url(resized_image, quality=82)

    scale_x = float(source_image.width) / float(max(1, resized_image.width))
    scale_y = float(source_image.height) / float(max(1, resized_image.height))

    existing_boxes_resized: list[dict[str, Any]] = []
    for box in existing_text_boxes:
        scaled = _to_resized_box(box, scale_x=scale_x, scale_y=scale_y)
        existing_boxes_resized.append(
            {
                "id": int(box.get("id") or 0),
                "x": round(float(scaled["x"]), 2),
                "y": round(float(scaled["y"]), 2),
                "width": round(float(scaled["width"]), 2),
                "height": round(float(scaled["height"]), 2),
                "text_preview": str(box.get("text") or "")[:40],
            }
        )

    client = create_openai_client({})
    try:
        proposed_raw = _propose_missing_candidates(
            client=client,
            cfg=cfg,
            volume_id=volume_id,
            filename=filename,
            page_data_url=page_data_url,
            resized_w=resized_image.width,
            resized_h=resized_image.height,
            existing_boxes_resized=existing_boxes_resized,
        )
    except ValueError as exc:
        proposed_raw = []
        _emit_runtime_event(
            on_runtime_event,
            {
                "phase": "propose",
                "status": "parse_error",
                "progress": 20,
                "message": (
                    "Missing-box proposal response was malformed; continuing with 0 candidates"
                ),
                "reason": str(exc).strip() or "proposal_parse_error",
            },
        )

    dedupe_anchor_boxes: list[dict[str, float]] = [
        {
            "x": float(box["x"]),
            "y": float(box["y"]),
            "width": float(box["width"]),
            "height": float(box["height"]),
        }
        for box in existing_text_boxes
    ]
    _bind_runtime_dependencies()
    normalized_candidates = _runtime._normalize_candidates(
        cfg=cfg,
        proposed_raw=proposed_raw,
        source_image_size=(source_image.width, source_image.height),
        resized_image_size=(resized_image.width, resized_image.height),
        scale_x=scale_x,
        scale_y=scale_y,
        dedupe_anchor_boxes=dedupe_anchor_boxes,
    )
    _emit_runtime_event(
        on_runtime_event,
        {
            "phase": "propose",
            "status": "completed",
            "progress": 20,
            "raw_proposed_count": len(proposed_raw),
            "proposed_count": len(normalized_candidates),
            "message": (
                f"Proposed {len(normalized_candidates)} candidate regions"
                if normalized_candidates
                else "No missing text candidates proposed"
            ),
        },
    )

    accepted_specs: list[dict[str, Any]] = []
    rejected_specs: list[dict[str, Any]] = []
    run_id: str | None = None
    created_boxes: list[dict[str, Any]] = []
    occupancy_boxes: list[dict[str, float]] = [
        {
            "x": float(box["x"]),
            "y": float(box["y"]),
            "width": float(box["width"]),
            "height": float(box["height"]),
        }
        for box in existing_text_boxes
    ]
    total_attempt_steps = max(1, len(normalized_candidates) * max(1, cfg.max_attempts_per_candidate))
    attempt_step_index = 0

    for candidate_index, candidate in enumerate(normalized_candidates, start=1):
        candidate_result = _runtime._evaluate_candidate(
            client=client,
            cfg=cfg,
            volume_id=volume_id,
            filename=filename,
            source_image=source_image,
            resized_image=resized_image,
            page_data_url=page_data_url,
            scale_x=scale_x,
            scale_y=scale_y,
            occupancy_boxes=occupancy_boxes,
            candidate=candidate,
            candidate_index=candidate_index,
            candidates_total=len(normalized_candidates),
            attempt_step_index=attempt_step_index,
            total_attempt_steps=total_attempt_steps,
            on_runtime_event=on_runtime_event,
        )
        attempt_step_index = candidate_result["attempt_step_index"]
        if candidate_result["accepted"]:
            accepted_spec = candidate_result["accepted_spec"]
            accepted_specs.append(accepted_spec)
            occupancy_boxes.append(dict(candidate_result["best_box"]))
            if run_id is None:
                run_id = create_detection_run(
                    volume_id,
                    filename,
                    task="text",
                    model_id=cfg.model_id,
                    model_label="LLM Missing Box ReAct",
                    model_version="v1",
                    model_path=None,
                    model_hash=None,
                    params={
                        "max_candidates": cfg.max_candidates,
                        "max_attempts_per_candidate": cfg.max_attempts_per_candidate,
                        "min_confidence": cfg.min_confidence,
                        "overlap_iou_threshold": cfg.overlap_iou_threshold,
                        "max_image_side": cfg.max_image_side,
                    },
                )
            persisted_now = replace_boxes_for_type(
                volume_id,
                filename,
                box_type="text",
                boxes=[
                    {
                        "x": float(candidate_result["best_box"]["x"]),
                        "y": float(candidate_result["best_box"]["y"]),
                        "width": float(candidate_result["best_box"]["width"]),
                        "height": float(candidate_result["best_box"]["height"]),
                    }
                ],
                run_id=run_id,
                source="detect",
                replace_existing=False,
            )
            created_boxes.extend(persisted_now)
            _emit_runtime_event(
                on_runtime_event,
                {
                    "phase": "persist",
                    "status": "running",
                    "progress": min(99, candidate_result["progress"] + 1),
                    "candidate_index": candidate_index,
                    "candidates_total": len(normalized_candidates),
                    "accepted_count": len(accepted_specs),
                    "created_count": len(created_boxes),
                    "message": f"Persisted accepted box {candidate_index}/{len(normalized_candidates)}",
                },
            )
            continue

        rejected_specs.append(candidate_result["rejected_spec"])

    _emit_runtime_event(
        on_runtime_event,
        {
            "phase": "persist",
            "status": "completed",
            "progress": 98,
            "accepted_count": len(accepted_specs),
            "rejected_count": len(rejected_specs),
            "created_count": len(created_boxes),
            "message": (
                f"Persisted {len(created_boxes)} accepted boxes"
                if created_boxes
                else "No accepted boxes to persist"
            ),
        },
    )
    _emit_runtime_event(
        on_runtime_event,
        {
            "phase": "completed",
            "status": "completed",
            "progress": 99,
            "proposed_count": len(normalized_candidates),
            "accepted_count": len(accepted_specs),
            "rejected_count": len(rejected_specs),
            "created_count": len(created_boxes),
            "message": (
                f"Created {len(created_boxes)} missing boxes"
                if created_boxes
                else "No missing boxes created"
            ),
        },
    )

    return {
        "status": "ok",
        "volume_id": volume_id,
        "filename": filename,
        "model_id": cfg.model_id,
        "existing_text_box_count": len(existing_text_boxes),
        "proposed_count": len(normalized_candidates),
        "accepted_count": len(accepted_specs),
        "rejected_count": len(rejected_specs),
        "created_count": len(created_boxes),
        "run_id": run_id,
        "accepted": accepted_specs,
        "rejected": rejected_specs,
    }
