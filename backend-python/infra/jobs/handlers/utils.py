# backend-python/infra/jobs/handlers/utils.py
from __future__ import annotations

from typing import Any


def extract_model_metadata(config: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    model_id = config.get("model")
    max_tokens = config.get("max_tokens") or config.get("max_completion_tokens")
    reasoning_effort = None
    reasoning = config.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if effort:
            reasoning_effort = str(effort)
    return (str(model_id) if model_id else None, max_tokens, reasoning_effort)


def apply_model_metadata(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    model_id, max_tokens, reasoning_effort = extract_model_metadata(config)
    updated = dict(payload)
    if model_id:
        updated["modelId"] = model_id
    if max_tokens is not None:
        try:
            updated["maxOutputTokens"] = int(max_tokens)
        except (TypeError, ValueError):
            pass
    if reasoning_effort:
        updated["reasoningEffort"] = reasoning_effort
    return updated


def make_snippet(text: str, limit: int = 80) -> str:
    snippet = " ".join(text.split())
    if len(snippet) > limit:
        return f"{snippet[:limit]}..."
    return snippet


def list_text_boxes(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_boxes = page.get("boxes", []) if isinstance(page, dict) else []
    text_boxes = [box for box in raw_boxes if box.get("type") == "text"]
    text_boxes.sort(
        key=lambda box: (
            int(box.get("orderIndex") or 10**9),
            int(box.get("id") or 0),
        )
    )
    return text_boxes
