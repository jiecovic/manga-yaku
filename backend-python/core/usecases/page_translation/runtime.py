# backend-python/core/usecases/page_translation/runtime.py
"""Use-case helpers for page-translation runtime operations."""

from __future__ import annotations

import logging
from threading import Event
from typing import Any

from config import TRANSLATION_SOURCE_LANGUAGE, TRANSLATION_TARGET_LANGUAGE
from infra.images.image_ops import encode_image_data_url, load_volume_image, resize_for_llm
from infra.llm import create_openai_client, has_openai_sdk
from infra.llm.model_capabilities import model_applies_reasoning_effort
from infra.logging.correlation import append_correlation

from .call import build_model_cfg, run_structured_call
from .prompts import (
    build_state_merge_prompt_payload,
    build_translate_stage_prompt_payload,
)
from .runtime_events import (
    StageEventCallback,
    build_stage_event_payload,
    emit_stage_event,
    write_debug_snapshot,
)
from .schema import (
    build_state_merge_text_format,
    build_translate_stage_text_format,
    coerce_positive_int,
    normalize_state_merge_result,
    normalize_translate_stage_result,
)
from .stage_outputs import apply_no_text_consensus_guard, summarize_translate_stage_coverage

logger = logging.getLogger(__name__)


def run_page_translation_stage(
    *,
    volume_id: str,
    filename: str,
    boxes: list[dict[str, Any]],
    ocr_profiles: list[dict[str, Any]] | None = None,
    prior_context_summary: str | None = None,
    prior_characters: list[dict[str, Any]] | None = None,
    prior_open_threads: list[str] | None = None,
    prior_glossary: list[dict[str, Any]] | None = None,
    source_language: str = TRANSLATION_SOURCE_LANGUAGE,
    target_language: str = TRANSLATION_TARGET_LANGUAGE,
    model_id: str | None = None,
    debug_id: str | None = None,
    max_output_tokens: int | None = None,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    merge_max_output_tokens: int | None = None,
    merge_reasoning_effort: str | None = None,
    on_stage_event: StageEventCallback | None = None,
    stop_event: Event | None = None,
) -> dict[str, Any]:
    if not has_openai_sdk():
        raise RuntimeError("OpenAI SDK is not available")

    system_prompt, user_content = build_translate_stage_prompt_payload(
        source_language=source_language,
        target_language=target_language,
        boxes=boxes,
        ocr_profiles=ocr_profiles,
        prior_context_summary=prior_context_summary,
        prior_characters=prior_characters,
        prior_open_threads=prior_open_threads,
        prior_glossary=prior_glossary,
    )

    user_content_blocks: list[dict[str, Any]] = [{"type": "input_text", "text": user_content}]
    original_image = load_volume_image(volume_id, filename)
    image = resize_for_llm(original_image)
    data_url = encode_image_data_url(image)
    user_content_blocks.append({"type": "input_image", "image_url": data_url})
    image_debug: dict[str, Any] = {
        "included": True,
        "original_size": list(original_image.size),
        "resized_size": list(image.size),
        "data_url_len": len(data_url),
    }

    translate_stage_input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": user_content_blocks,
        },
    ]

    client = create_openai_client({})
    base_cfg = build_model_cfg(
        model_id=model_id,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
    )

    stage1_log_context = {
        "volume_id": volume_id,
        "filename": filename,
        "job_id": debug_id or "",
        "include_image": True,
        "stage": "translate",
    }
    emit_stage_event(
        on_stage_event,
        stage="translate_page",
        status="started",
        payload=build_stage_event_payload(
            stage="translate_page",
            status="running",
            message="Translating page",
            cfg=base_cfg,
        ),
    )

    def _raise_if_stopped() -> None:
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("translate stage canceled")

    _raise_if_stopped()
    try:
        stage1_result, stage1_debug = run_structured_call(
            client=client,
            model_cfg=base_cfg,
            input_payload=translate_stage_input_payload,
            text_format=build_translate_stage_text_format(),
            parser=normalize_translate_stage_result,
            component="page_translation.translate",
            repair_component="page_translation.translate.repair",
            log_context=stage1_log_context,
            stop_event=stop_event,
        )
    except Exception as exc:
        stage1_error = str(exc).strip() or repr(exc)
        emit_stage_event(
            on_stage_event,
            stage="translate_page",
            status="failed",
            payload=build_stage_event_payload(
                stage="translate_page",
                status="failed",
                message="Translate stage failed",
                cfg=base_cfg,
                error=stage1_error,
            ),
        )
        raise
    _raise_if_stopped()
    stage1_result, forced_no_text_box_ids = apply_no_text_consensus_guard(
        stage1_result=stage1_result,
        input_boxes=boxes,
        ocr_profiles=ocr_profiles,
    )
    if forced_no_text_box_ids:
        stage1_debug["post_guard_no_text_boxes"] = forced_no_text_box_ids
    coverage = summarize_translate_stage_coverage(stage1_result=stage1_result, input_boxes=boxes)
    stage1_debug["coverage"] = coverage
    if not coverage["is_complete"]:
        warnings: list[str] = []
        missing_box_ids = coverage["missing_box_ids"]
        if missing_box_ids:
            warning = (
                f"Translate stage output omitted {len(missing_box_ids)} input boxes: "
                f"{missing_box_ids}."
            )
            if (
                str(stage1_debug.get("finish_reason") or "").strip()
                == "incomplete:max_output_tokens"
            ):
                warning += " The model output was truncated; consider increasing page-translation max_output_tokens."
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
        if warnings:
            stage1_debug["warnings"] = warnings
            for warning in warnings:
                logger.warning(
                    append_correlation(
                        warning,
                        stage1_log_context,
                        component_name="page_translation.translate",
                    )
                )
    stage1_event = build_stage_event_payload(
        stage="translate_page",
        status="completed",
        message="Translate stage complete",
        cfg=base_cfg,
        diagnostics=stage1_debug,
    )
    emit_stage_event(
        on_stage_event,
        stage="translate_page",
        status="succeeded",
        payload=stage1_event,
    )
    _raise_if_stopped()

    merge_system_prompt, merge_user_content = build_state_merge_prompt_payload(
        source_language=source_language,
        target_language=target_language,
        prior_context_summary=prior_context_summary,
        prior_characters=prior_characters,
        prior_open_threads=prior_open_threads,
        prior_glossary=prior_glossary,
        stage1_result=stage1_result,
    )
    merge_stage_input_payload = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": merge_system_prompt}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": merge_user_content}],
        },
    ]

    merge_cfg = dict(base_cfg)
    stage2_max_output = coerce_positive_int(merge_max_output_tokens)
    if stage2_max_output is None:
        stage2_max_output = coerce_positive_int(merge_cfg.get("max_output_tokens"))
    if stage2_max_output is None:
        stage2_max_output = 768
    merge_cfg["max_output_tokens"] = max(128, min(stage2_max_output, 4096))

    # Merge is bookkeeping; keep a dedicated setting so users can trade off speed/quality.
    if model_applies_reasoning_effort(merge_cfg.get("model")):
        requested_effort = (
            str(merge_reasoning_effort).strip().lower()
            if isinstance(merge_reasoning_effort, str)
            else ""
        )
        if requested_effort not in {"low", "medium", "high"}:
            requested_effort = "low"
        merge_cfg["reasoning"] = {"effort": requested_effort}

    stage2_log_context = {
        "volume_id": volume_id,
        "filename": filename,
        "job_id": debug_id or "",
        "stage": "merge",
    }

    stage2_error: str | None = None
    stage2_debug: dict[str, Any] = {}
    emit_stage_event(
        on_stage_event,
        stage="merge_state",
        status="started",
        payload=build_stage_event_payload(
            stage="merge_state",
            status="running",
            message="Merging continuity state",
            cfg=merge_cfg,
        ),
    )
    try:
        stage2_result, stage2_debug = run_structured_call(
            client=client,
            model_cfg=merge_cfg,
            input_payload=merge_stage_input_payload,
            text_format=build_state_merge_text_format(),
            parser=normalize_state_merge_result,
            component="page_translation.merge",
            repair_component="page_translation.merge.repair",
            log_context=stage2_log_context,
            stop_event=stop_event,
        )
        stage2_event = build_stage_event_payload(
            stage="merge_state",
            status="completed",
            message="Merge stage complete",
            cfg=merge_cfg,
            diagnostics=stage2_debug,
        )
        emit_stage_event(
            on_stage_event,
            stage="merge_state",
            status="succeeded",
            payload=stage2_event,
        )
    except Exception as exc:
        stage2_error = str(exc).strip() or repr(exc)
        logger.warning(
            append_correlation(
                f"State merge call failed, using fallback context: {stage2_error}",
                {
                    "component": "page_translation.merge",
                    "job_id": debug_id,
                    "volume_id": volume_id,
                    "filename": filename,
                },
            )
        )
        stage2_event = build_stage_event_payload(
            stage="merge_state",
            status="completed",
            message="Merge stage fallback applied",
            cfg=merge_cfg,
            diagnostics=stage2_debug,
        )
        stage2_event["merge_warning"] = stage2_error
        stage2_event["finish_reason"] = "fallback"
        emit_stage_event(
            on_stage_event,
            stage="merge_state",
            status="succeeded",
            payload=stage2_event,
        )
        stage2_result = {
            "characters": list(prior_characters) if isinstance(prior_characters, list) else [],
            "open_threads": list(prior_open_threads)
            if isinstance(prior_open_threads, list)
            else [],
            "glossary": list(prior_glossary) if isinstance(prior_glossary, list) else [],
            "story_summary": str(prior_context_summary or "").strip(),
        }
        if not stage2_result["story_summary"] and stage1_result["page_events"]:
            stage2_result["story_summary"] = " ".join(stage1_result["page_events"][:3]).strip()

    result = {
        "boxes": stage1_result["boxes"],
        "no_text_boxes": stage1_result["no_text_boxes"],
        "image_summary": stage1_result["image_summary"],
        "page_events": stage1_result["page_events"],
        "page_characters_detected": stage1_result["page_characters_detected"],
        "characters": stage2_result["characters"],
        "open_threads": stage2_result["open_threads"],
        "glossary": stage2_result["glossary"],
        "story_summary": stage2_result["story_summary"],
    }
    if stage2_error:
        result["merge_warning"] = stage2_error
    result["_stage_meta"] = {
        "translate_page": stage1_event,
        "merge_state": stage2_event,
    }

    debug_payload = {
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
    write_debug_snapshot(debug_id=debug_id, payload=debug_payload)
    return result
