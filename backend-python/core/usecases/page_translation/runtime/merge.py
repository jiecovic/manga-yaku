# backend-python/core/usecases/page_translation/runtime/merge.py
"""Merge-stage helpers for the page-translation runtime."""

from __future__ import annotations

from typing import Any

from infra.llm.model_capabilities import model_applies_reasoning_effort

from ..schema.normalization import coerce_positive_int


def build_merge_model_cfg(
    *,
    base_cfg: dict[str, Any],
    merge_max_output_tokens: int | None,
    merge_reasoning_effort: str | None,
) -> dict[str, Any]:
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
    return merge_cfg


def build_merge_fallback_result(
    *,
    prior_context_summary: str | None,
    prior_characters: list[dict[str, Any]] | None,
    prior_open_threads: list[str] | None,
    prior_glossary: list[dict[str, Any]] | None,
    stage1_result: dict[str, Any],
) -> dict[str, Any]:
    result = {
        "characters": list(prior_characters) if isinstance(prior_characters, list) else [],
        "open_threads": list(prior_open_threads) if isinstance(prior_open_threads, list) else [],
        "glossary": list(prior_glossary) if isinstance(prior_glossary, list) else [],
        "story_summary": str(prior_context_summary or "").strip(),
    }
    if not result["story_summary"] and stage1_result["page_events"]:
        result["story_summary"] = " ".join(stage1_result["page_events"][:3]).strip()
    return result
